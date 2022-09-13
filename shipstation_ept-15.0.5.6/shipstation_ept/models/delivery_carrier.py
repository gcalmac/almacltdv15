"""
Emipro Technologies Private Limited
Ravi Kotadiya | ravik@emiprotechnologies.com
Date : Oct-26-2021
"""
import json
import logging
from datetime import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class DeliveryCarrier(models.Model):
    """
    inheriting delivery carrier for shipstation implementation.
    """
    _inherit = 'delivery.carrier'
    _description = 'Delivery Carrier'

    shipstation_instance_id = fields.Many2one("shipstation.instance.ept",  ondelete='restrict')
    shipstation_carrier_id = fields.Many2one('shipstation.carrier.ept',
                                             string="Shipstation Carrier")
    shipstation_weight_uom = fields.Selection([('grams', 'Grams'),
                                               ('pounds', 'Pounds'),
                                               ('ounces', 'Ounces')], default='grams',
                                              string="Supported Weight UoM",
                                              help="Supported Weight UoM by ShipStation")
    delivery_type = fields.Selection(selection_add=[("shipstation_ept", "Shipstation")],
                                     ondelete={'shipstation_ept': 'cascade'})
    shipstation_default_product_packaging_id = fields.Many2one('product.packaging',
                                                               string="Default Package Type")
    package_unit_default = fields.Selection([('inches', 'Inches'),
                                             ('centimeters', 'Centimeters')],
                                            string="Package Unit", default='inches')

    shipstation_service_id = fields.Many2one('shipstation.services.ept', string='Shipstation Service',
                                             help="Shipstation service to use for the order from this carrier.")
    confirmation = fields.Selection([('none', 'None'),
                                     ('delivery', 'Delivery'),
                                     ('signature', 'Signature'),
                                     ('adult_signature', 'Adult Signature'),
                                     ('direct_signature', 'Direct Signature')],
                                    default="none", copy=False,
                                    help="Shipstation order confirmation level for order using this carrier.")
    shipstation_package_id = fields.Many2one('product.packaging',
                                             string='Shipstation Package',
                                             copy=False,
                                             help="Shipstation package to use for this carrier.")
    get_cheapest_rates = fields.Boolean("Cheapest Carrier Selection ?",
                                        help="True: User need to manually get rates and select the service and package "
                                             "in Delivery order when using this carrier.\n "
                                             "False: Service and package will be required and will automatically "
                                             "set in Delivery Order.", default=False)

    shipstation_weight_uom_id = fields.Many2one('uom.uom',
                                                domain=lambda self: [('category_id.id', '=',
                                                                      self.env.ref('uom.product_uom_categ_kgm').id)],
                                                string='Shipstaion UoM',
                                                help="Set equivalent unit of"
                                                     " measurement according to "
                                                     "provider unit of measurement."
                                                     " For Example, if the provider unit of "
                                                     "measurement is KG then you have to select KG "
                                                     "unit of measurement in the Shipstation Unit of"
                                                     " Measurement field.")
    shipstation_user_id = fields.Many2one('res.users',
                                          string='Shipstation Batch Responsible',
                                          help='Responsible person to process the batch')

    shipstation_auto_create_batch = fields.Boolean(string="Shipstation Auto Create Batch",
                                                   default=False,
                                                   copy=False,
                                                   help="If Auto Create Batch Is True Then Automatically "
                                                        "Create The Batch.")
    shipstation_batch_limit = fields.Integer('Shipstation Delivery Order Limit In Batch', default=100)
    shipstation_auto_done_pickings = fields.Boolean(string="Shipstation Auto Validate Delivery Orders",
                                                    default=False,
                                                    copy=False,
                                                    help="True: Validate All Delivery Orders in Batch. "
                                                         "False: User has to validate the batch manually.")
    shipstation_use_existing_batch_cronjob = fields.Boolean(string="Shipstation Use Existing Batch",
                                                            default=False,
                                                            copy=False,
                                                            help="""True: Delivery orders will be added to existing batch in 
                                                draft state for carrier. 
                                                False: New batch will be created every time and all the 
                                                delivery order will be added to new Batch.""")
    shipstation_carrier_code = fields.Char(string="Shipstation Requested Shipping Service Name")

    # Added by [ES] | Task: 183892 | Dated on 10, Jan 2022
    shipstation_carrier_ids = fields.Many2many('shipstation.carrier.ept',
                                             string="Shipstation Carriers")
    shipstation_service_ids = fields.Many2many('shipstation.services.ept', string='Shipstation Services',
                                            help="Shipstation service to use for the order from this carrier.")

    def shipstation_ept_send_shipping(self, pickings):
        """
        This method is created to fetch shipstaion labels for the pickings
        if Delivery Order is fulfilled from odoo.
        """
        result = []
        for picking in pickings.filtered(lambda x: not x.export_order):
            result = picking.get_shipstation_label()
        if not result:
            result += [{}]
        return result

    def shipstation_ept_rate_shipment(self, orders):
        """
        This method is to fetch rates from shipstation, when requesting from website or sale order.
        :param orders: record of sale.order
        :return: it will return the price for cheapest carrier service and set
        the service,store and instance in the sale.order

		Method modified by: Hardik Joshi on 08-06-2022
        Modification: add dimension field to API request parameter
        Task No. and Description: 192229 - Pass package dimension to ShipStation
        """
        price = 0.0
        for order in orders:
            if (not self.shipstation_service_id or not self.shipstation_package_id) and self.get_cheapest_rates is False:
                msg = "There are multiple rates available on the Shipstation therefore rate will be available on the Delivery Order."
                return {'success': False, 'price': float(price), 'error_message': msg, 'warning_message': False}
            shipstation_warehouse = self.env['shipstation.warehouse.ept'].search(
                ['|', ('odoo_warehouse_id', '=', order.warehouse_id.id),
                 ('is_default', '=', True),
                 ('shipstation_instance_id', '=', self.shipstation_instance_id.id)], limit=1)
            if shipstation_warehouse:
                shipstation_service_obj = self.env['shipstation.services.ept']
                shipstation_services = self.shipstation_service_id
                shipstation_carriers = shipstation_services.shipstation_carrier_id
                data = {"serviceCode": shipstation_services.service_code,
                        "packageCode": self.shipstation_package_id.shipper_package_code or 'package'}
                instance = self.shipstation_instance_id
                shipping_partner_id = order.partner_shipping_id
                total_weight = sum([(line.product_id.weight * line.product_uom_qty) for line in
                                    order.order_line]) or 0.0
                try:
                    total_weight = self.convert_weight_for_shipstation(
                        order.company_id and order.company_id.get_weight_uom_id(),
                        self.shipstation_weight_uom_id, total_weight)
                except Exception as e:
                    return {'success': False, 'price': float(price),
                            'error_message': "Something went wrong while converting weight",
                            'warning_message': False}
                # check cheapest rate is enabled
                if self.get_cheapest_rates is True:
                    shipstation_carriers = self.shipstation_carrier_ids
                    data = {"packageCode": self.shipstation_package_id.shipper_package_code or 'package'}
                cheapest_carriers = []

                for carrier in shipstation_carriers:
                    querystring = {'carrierCode': carrier.code}
                    data.update({
                        "carrierCode": carrier.code,
                        "fromPostalCode": shipstation_warehouse.origin_address_id.zip,
                        "toState": shipping_partner_id.state_id.code,
                        "toCountry": shipping_partner_id.country_id.code,
                        "toPostalCode": shipping_partner_id.zip,
                        "toCity": shipping_partner_id.city,
                        "weight": {
                            "value": total_weight,
                            "units": self.shipstation_weight_uom
                        },
                        "confirmation": self.confirmation,
                        "residential": False
                    })

                    if self.shipstation_package_id.packaging_length > 0 and self.shipstation_package_id.width > 0 and self.shipstation_package_id.height > 0:
                        data.update({"dimensions": {
                            "length": self.shipstation_package_id.packaging_length,
                            "width": self.shipstation_package_id.width,
                            "height": self.shipstation_package_id.height,
                            "units": "inches"
                        }})

                    response, code = instance.get_connection(url='/shipments/getrates', data=data, params=querystring,
                                                             method="POST")
                    if not response or code.status_code != 200:
                        if self.get_cheapest_rates is True:
                            continue
                        else:
                            msg = "100 : Something went wrong while Getting Rates from" \
                                  "ShipStation.\n\n %s" % (code.content.decode('utf-8'))
                            order.unlink_old_message_and_post_new_message(body=msg)
                            _logger.exception(msg)
                            return {
                                'success': False,
                                'price': float(price),
                                'error_message': "No rates available",
                                'warning_message': False
                            }

                    # Filter the cheapest rate based on selected services
                    selected_services = self.shipstation_service_ids.filtered(
                        lambda x: x.shipstation_carrier_id.id == carrier.id).mapped('service_code')
                    for result in response:
                        # If response service not exist in selected service then Skip
                        if self.get_cheapest_rates and selected_services:
                            if result.get('serviceCode', False) not in selected_services:
                                continue
                        # If price not available then Skip
                        price = result.get('shipmentCost', False)
                        service_id = shipstation_service_obj.search(
                            [('service_code', '=', result.get('serviceCode', False)),
                             ('shipstation_carrier_id', '=', carrier.id)])
                        # If price not available or service not available then Skip
                        if not service_id or not price:
                            continue

                        cheapest_carriers.append({
                            'price': price,
                            'servicecode': service_id.service_code,
                            'carrier': carrier
                        })

                if cheapest_carriers:
                    finalised_carrier = sorted(cheapest_carriers, key=lambda x: x['price'])
                    price = finalised_carrier[0]['price']
                    service_id = self.env['shipstation.services.ept'].search([
                        ('service_code', '=', finalised_carrier[0]['servicecode']),
                        ('shipstation_carrier_id', '=', finalised_carrier[0]['carrier'].id)])
                    carrier = finalised_carrier[0]['carrier']
                    order.cheapest_service_id = service_id
                    price = self.convert_shipping_rate(price, carrier.carrier_rate_currency_id, order)
                    return {'success': True, 'price': float(price), 'error_message': False, 'warning_message': False}
                else:
                    msg = "115 : Something went wrong while Getting Rates from" \
                          "ShipStation.\n\n %s" % (code.content.decode('utf-8'))
                    order.unlink_old_message_and_post_new_message(body=msg)
                    _logger.exception(msg)
                    return {
                        'success': False,
                        'price': float(price),
                        'error_message': "No rates available",
                        'warning_message': False
                    }
            else:
                msg = "116 : Warehouse configuration not found while Getting Rates from ShipStation."
                order.unlink_old_message_and_post_new_message(body=msg)
                _logger.exception(msg)
                return {
                    'success': False,
                    'price': float(price),
                    'error_message': "No rates available",
                    'warning_message': False
                }

    def shipstation_ept_cancel_shipment(self, picking_ids):
        for picking in picking_ids:
            if picking.shipstation_shipment_id:
                data = {"shipmentId": picking.shipstation_shipment_id}
                instance = picking.shipstation_instance_id
                response, code = instance.get_connection(url='/shipments/voidlabel', data=data, method="POST")
                if code.status_code != 200:
                    try:
                        res = json.loads(code.content.decode('utf-8')).get('ExceptionMessage')
                    except:
                        res = code.content.decode('utf-8')
                    msg = "101 : Something went wrong while Canceling label on " \
                          "ShipStation.\n\n %s" % res
                    picking.unlink_old_message_and_post_new_message(body=msg)
                    _logger.exception(msg)
                    raise UserError(msg)
                if response.get('approved'):
                    picking.unlink_old_message_and_post_new_message(body="Shipment Cancelled on ShipStation.")
                    picking.write({'canceled_on_shipstation': True})

        return True

    def shipstation_ept_get_tracking_link(self, picking):
        if self.shipstation_carrier_id.tracking_url:
            if '{TRACKING_NUMBER}' in self.shipstation_carrier_id.tracking_url:
                url = self.shipstation_carrier_id.tracking_url.replace('{TRACKING_NUMBER}',
                                                                       str(picking.carrier_tracking_ref))
            else:
                url = str(self.shipstation_carrier_id.tracking_url) + str(picking.carrier_tracking_ref)
            return url
        elif self.shipstation_instance_id.tracking_link:
            return str(self.shipstation_instance_id.tracking_link) + str(picking.carrier_tracking_ref)
        return False

    def convert_weight_for_shipstation(self, from_uom_unit, to_uom_unit, weight):
        return from_uom_unit._compute_quantity(weight, to_uom_unit)

    @api.onchange('shipstation_weight_uom')
    def onchange_shipstation_weight_uom(self):
        for rec in self:
            if rec.shipstation_weight_uom:
                mapping_rec = self.env["shipstation.weight.mapping"].search(
                    [('shipstation_weight_uom', '=', rec.shipstation_weight_uom)], limit=1)
            if not mapping_rec:
                raise UserError(
                    "No weight mapping found for {}, Please define first!!!".format(rec.shipstation_weight_uom))
            rec.shipstation_weight_uom_id = mapping_rec.shipstation_weight_uom_id.id

    def convert_shipping_rate(self, amount, from_currency, order):
        """
        Convert shipping rate from carrier currency to order or company currency
        """
        if amount:
            if not from_currency:
                from_currency = order.company_id.currency_id
            rate = self.env['res.currency']._get_conversion_rate(from_currency, order.currency_id,
                                                                 order.company_id, datetime.now())
            return order.currency_id.round(amount * rate)
        return amount
