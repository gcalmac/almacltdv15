"""
Emipro Technologies Private Limited
Author : Ravi Kotadiya | ravik@emiprotechnologies.com
Date : Oct-26-2021
"""
import binascii
import json
import logging
from datetime import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tests import Form

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    """
    inheriting stock.picking for implementation of ShipStation.
    """
    _inherit = 'stock.picking'
    _description = 'Stock Picking'

    shipstation_instance_id = fields.Many2one('shipstation.instance.ept', string='Instance')
    shipstation_store_id = fields.Many2one('shipstation.store.ept', string='Shipstation Store')
    shipstation_order_id = fields.Integer(string='Shipstation Order Reference', copy=False)
    shipstation_shipment_id = fields.Integer("Shipment ID", help="Shipstation Shipment ID", copy=False)
    shipstation_carrier_id = fields.Many2one('shipstation.carrier.ept',
                                             related="carrier_id.shipstation_carrier_id")
    shipstation_service_id = fields.Many2one('shipstation.services.ept', string='Shipstation Service')
    shipstation_package_id = fields.Many2one('product.packaging', string='Shipstation Package')
    delivery_rate_ids = fields.One2many('delivery.rate.ept', 'picking_id', string='Delivery Rates', copy=False)
    shipping_rates = fields.Float(string='Shipping Rate', copy=False)
    is_exported_to_shipstation = fields.Boolean("Exported to shipstation?", copy=False, default=False)
    is_get_shipping_label = fields.Boolean('Is Shipping Label Available?', copy=False, default=False)
    marked_as_shipped_to_shipstation = fields.Boolean("Marked as Shipped", copy=False, default=False)
    canceled_on_shipstation = fields.Boolean(string="Cancelled on shipstation?", copy=False, default=False)
    export_order = fields.Boolean(string='Export order to Shipstation?', default=False)
    confirmation = fields.Selection(
        [('none', 'None'),
         ('delivery', 'Delivery'),
         ('signature', 'Signature'),
         ('adult_signature', 'Adult Signature'),
         ('direct_signature', 'Direct Signature')],
        default="none", copy=False)
    shipstation_send_to_shipper_process_done = fields.Boolean('Shipstation Send To Shipper (Done).', copy=False,
                                                              readonly=True,
                                                              help="This field indicates that send to shipper "
                                                                   "for picking is done.")
    shipstaion_actual_shipping_cost = fields.Float(string="Shipstation Actual Shipping cost")
    related_outgoing_picking = fields.Many2one("stock.picking", string="Related Outgoing Picking")

    def get_default_uom_ept(self):
        """ Add default weight uom to the Stock Picking
            @return: return default weight uom id
        """

        company_id = self.company_id or self.env.user.company_id
        if company_id and company_id.get_weight_uom_id():
            return company_id.get_weight_uom_id()

        weight_uom_id = self.env.ref('uom.product_uom_kgm', raise_if_not_found=False)
        if not weight_uom_id:
            uom_categ_id = self.env.ref('uom.product_uom_categ_kgm').id
            weight_uom_id = self.env['uom.uom'].search(
                [('category_id', '=', uom_categ_id), ('factor', '=', 1)],
                limit=1)
        return weight_uom_id

    shipstation_weight_uom_id = fields.Many2one('uom.uom', string='Shipstation Unit of Measure', required=True,
                                                readonly="1",
                                                domain=lambda self: [('category_id.id', '=',
                                                                      self.env.ref('uom.product_uom_categ_kgm').id)],
                                                help="Unit of measurement for Weight", default=get_default_uom_ept)

    @api.onchange('shipstation_instance_id')
    def onchange_shipstation_instance_id(self):
        """
        Onchange method for shipstation_instance_id
        """
        if self.shipstation_store_id.shipstation_instance_id.id != self.shipstation_instance_id.id:
            self.shipstation_store_id = False
        self.shipstation_service_id = self.carrier_id.shipstation_service_id.id or False

    @api.onchange('carrier_id')
    def onchange_shipstation_carrier_id(self):
        """
        OnChange method for carrier_id
        """
        self.shipstation_instance_id = self.carrier_id.shipstation_instance_id.id or False
        self.shipstation_service_id = self.carrier_id.shipstation_service_id.id or False
        self.shipstation_package_id = self.carrier_id.shipstation_package_id.id or False
        self.confirmation = self.carrier_id.confirmation

    def button_validate(self):
        """
            Inheriting button_validate to check for tracking if order is exported or originally
            from shipstation.
            or else send the tracking back to shipstation if the order is fulfilled in odoo.
        """
        for picking in self:
            # In case of validate internal picking:
            # If order already exported to ShipStation and Shipped then create backorder
            if picking.picking_type_id.code == 'internal' and picking.sale_id.shipstation_instance_id and picking.is_order_pick_ship():
                outgoing_pickings = self.find_outgoing_picking()
                for out_picking in outgoing_pickings:
                    result = out_picking.check_is_order_shipped_and_create_back_order()
                    if not result:
                        msg = "Some Thing Went Wrong While Validating : " \
                              "<a href=# data-oe-model=stock.picking data-oe-id={}>{}</a>"\
                            .format(out_picking.id, out_picking.name)
                        picking.message_post(body=msg)
                        self -= picking

            # in case when order is to be exported to ShipStation but it is still not
            # exported to Shipstation then it will post a message and will skip that picking.
            if picking.shipstation_instance_id and picking.export_order and not picking.is_exported_to_shipstation:
                msg = "Cannot Validate {}, as it is pending to be exported to ShipStation".format(picking.name)
                picking.unlink_old_message_and_post_new_message(body=msg)
                if picking.batch_id:
                    picking.batch_id.unlink_old_message_and_post_new_message(body=msg)
                self -= picking
                continue

            # if order is originally from shipstation check for status and fetch tracking number:
            if picking.shipstation_order_id and picking.shipstation_instance_id:
                result, response = picking.find_if_shipped_and_fetch_tracking_number()
                if not result:
                    self -= picking
                    continue

        res = super(StockPicking, self).button_validate()

        for picking in self.filtered(lambda x: x.state == "done" and x.picking_type_id.code == "internal"):
            picking.find_related_outgoing_picking_and_export()

        self.sudo().delivery_rate_ids.unlink()
        return res

    def find_if_shipped_and_fetch_tracking_number(self):
        """
        Call API for checked order is shipped in ShipStation if Yes then get Tracking details.
        """
        instance = self.shipstation_instance_id
        url = '/orders/%s' % self.shipstation_order_id
        response, code = instance.get_connection(url=url, data=None, params=None, method="GET")
        if code.status_code != 200:
            try:
                res = json.loads(code.content.decode('utf-8')).get('ExceptionMessage')
            except:
                res = code.content.decode('utf-8')
            msg = 'While requesting for order status of %s on shipstation. \n%s', self.name, res
            self.unlink_old_message_and_post_new_message(body=msg)
            if self.batch_id:
                self.batch_id.unlink_old_message_and_post_new_message(
                    body="While requesting for order status of {} on shipstation <br/> {}".format(self.name, res))
            _logger.info(msg)
            return False, response
        _logger.info("shipstation Response {} for picking: {}, Url: {}".format(response, self.name, url))
        if not response.get('orderStatus') == 'shipped':
            if response.get('orderStatus') == 'cancelled':
                self.action_cancel()
                return False, response
            self.unlink_old_message_and_post_new_message(body="Label has not been generated on the shipstation.")
            if self.batch_id:
                self.batch_id.unlink_old_message_and_post_new_message(
                    body="Label has not been generated for {} on the shipstation.".format(self.name))
            _logger.info("Label has not been generated on the shipstation for picking:"
                         " %s", self.name)
            return False, response

        self.is_get_shipping_label = True
        url = '/shipments?orderId=%s' % self.shipstation_order_id
        response, code = instance.get_connection(url=url, data=None, params=None, method="GET")
        if code.status_code != 200:
            try:
                res = json.loads(code.content.decode('utf-8')).get('ExceptionMessage')
            except:
                res = code.content.decode('utf-8')
            msg = 'While requesting for Tracking number of %s on Shipstation' \
                  '\n%s' % (self.name, res)
            self.unlink_old_message_and_post_new_message(body=msg)
            if self.batch_id:
                self.batch_id.unlink_old_message_and_post_new_message(body=msg)
            _logger.exception(msg)
            return False, response

        if self.sale_id.team_id.shipstation_update_carrier:
            self.set_carrier_based_on_response(response)

        tracking_number = ''
        shipping_cost = 0
        for shipment in response.get('shipments'):
            if str(shipment.get('voided', '')).lower() == 'true':
                continue
            tracking_number += ', {}'.format(shipment.get('trackingNumber', '')) if tracking_number else shipment.get(
                'trackingNumber', '')
            shipping_cost += shipment.get('shipmentCost', 0)
        shipping_cost = self.convert_company_currency_amount_to_order_currency(shipping_cost)
        self.write({'carrier_tracking_ref': tracking_number, 'shipstaion_actual_shipping_cost': shipping_cost})
        return True, response

    def get_package_dimension(self):
        if self.shipstation_package_id:
            package_dimension_data = self.shipstation_package_id
        else:
            package_dimension_data = self.carrier_id.shipstation_package_id
        return package_dimension_data.packaging_length, package_dimension_data.width, package_dimension_data.height

    def get_rates(self):
        """
        This method is to get the rates of shipment for Delivery Order

        Modified By: Hardik Joshi on 14-06-2022
        Modification: Add package_code in rate_vals
        Task No.: 192764 - Prevent updating wrong package in Delivery Order
        """
        if not self.carrier_id:
            raise UserError('Please set delivery method in Delivery Order!')

        if not self.shipstation_instance_id:
            raise UserError('Please set delivery method in Delivery order!')

        shipstation_warehouse = self.env['shipstation.warehouse.ept'].search(
            ['|', ('odoo_warehouse_id', '=', self.picking_type_id.warehouse_id.id),
             ('is_default', '=', True),
             ('shipstation_instance_id', '=', self.shipstation_instance_id.id)], limit=1)
        if not shipstation_warehouse:
            msg = 'Ship-station warehouse must be selected in the current Ship-station store.'
            raise UserError(msg)

        try:
            total_weight = self.get_converted_weight_for_shipstation()
        except Exception as e:
            raise UserError(e)

        instance = self.shipstation_instance_id
        shipstation_service_obj = self.env['shipstation.services.ept']
        delivery_rate_obj = self.env['delivery.rate.ept']
        shipping_partner_id = self.partner_id
        data = {}
        rate_for_service_not_found = []
        package_code = self.shipstation_package_id.shipper_package_code or self.carrier_id.shipstation_package_id.shipper_package_code or 'package'

        shipstation_carriers = self.carrier_id.shipstation_carrier_id
        if self.carrier_id.get_cheapest_rates:
            shipstation_carriers = self.carrier_id.shipstation_carrier_ids
        else:
            if self.shipstation_service_id:
                data.update({"serviceCode": self.shipstation_service_id.service_code})
            else:
                data.update({"serviceCode": self.carrier_id.shipstation_service_id.service_code})

        if not shipstation_carriers:
            msg = 'No ShipStation Carrier Found on Delivery Carrier %s' % self.carrier_id.name
            raise UserError(msg)

        length, width, height = self.get_package_dimension()

        self.delivery_rate_ids.unlink()
        for carrier in shipstation_carriers:
            data.update({
                "carrierCode": carrier.code,
                "packageCode": package_code,
                "fromPostalCode": shipstation_warehouse.origin_address_id.zip,
                "toState": shipping_partner_id.state_id.code,
                "toCountry": shipping_partner_id.country_id.code,
                "toPostalCode": shipping_partner_id.zip,
                "toCity": shipping_partner_id.city,
                "weight": {
                    "value": total_weight,
                    "units": self.carrier_id.shipstation_weight_uom or self.shipstation_instance_id.shipstation_weight_uom
                },
                "confirmation": self.confirmation,
                "residential": False
            })

            if length > 0 and width > 0 and height > 0:
                data.update({"dimensions": {
                    "length": length,
                    "width": width,
                    "height": height,
                    "units": "inches"
                }})

            response, code = instance.get_connection(url='/shipments/getrates', data=data, method="POST")
            if code.status_code != 200:
                try:
                    res = json.loads(code.content.decode('utf-8')).get('ExceptionMessage')
                except:
                    res = code.content.decode('utf-8')
                # Error Code 104
                self.unlink_old_message_and_post_new_message(body='104: %s' % res)
                _logger.exception('104: %s While get rates for Picking %s and Carrier %s', res, self.name, carrier.name)
                raise UserError("104: %s" % res)
            if not response:
                rate_for_service_not_found.append(carrier)
            selected_services = self.carrier_id.shipstation_service_ids.filtered(
                lambda x: x.shipstation_carrier_id.id == carrier.id).mapped('service_code')
            for res in response:
                if self.carrier_id.get_cheapest_rates and selected_services:
                    if res.get('serviceCode', False) not in selected_services:
                        continue
                shipping_cost = self.convert_company_currency_amount_to_order_currency(res.get('shipmentCost', 0))
                other_cost = self.convert_company_currency_amount_to_order_currency(res.get('otherCost', 0))
                service_name = res.get('serviceName', False)
                service_id = shipstation_service_obj.search([('service_code', '=', res.get('serviceCode', False)),
                                                             ('shipstation_carrier_id', '=', carrier.id)])
                if not service_id:
                    continue

                delivery_rate = delivery_rate_obj.search([('picking_id', '=', self.id),
                                                          ('shipstation_carrier_id', '=', carrier.id),
                                                          ('service_id', '=', service_id.id),
                                                          ('shipment_cost', '=', shipping_cost),
                                                          ('other_cost', '=', other_cost),
                                                          ('service_name', '=', service_name)])
                if delivery_rate:
                    continue
                rate_vals = {
                    'picking_id': self.id,
                    'shipstation_carrier_id': carrier.id or False,
                    'service_id': service_id.id or False,
                    'shipment_cost': shipping_cost or False,
                    'other_cost': other_cost or False,
                    'service_name': service_name or False,
                    'package_code': package_code or False
                }
                delivery_rate_obj.create(rate_vals)

        if not self.delivery_rate_ids:
            raise UserError('105: No rates are available for Picking {}'.format(self.name))
        return True

    def export_order_to_shipstation(self, log_book=False):
        """
            This method is used to create orders on shipstation.
        """
        if self.state != 'assigned':
            raise UserError("Picking {} must be in ready state for export order to shipstation.".format(self.name))
        if not self.carrier_id:
            raise UserError("Need to select Carrier in Picking for export order to shipstation.")
        self.is_picking_contains_store()

        model_id = self.env['ir.model'].sudo().search([('model', '=', self._name)]).id
        is_log_exist = True
        if not log_book:
            log_book = self.env['common.log.book.ept'].create_shipstation_log('export', model_id)
            is_log_exist = False

        total_amount, tax_amount, shipping_amount, shipping_tax = 0, 0, 0, 0
        shipstation_instance = self.shipstation_store_id.shipstation_instance_id
        shipping_line = self.sale_id.order_line.filtered(lambda x: x.is_delivery)
        order_data = self.prepare_order_export_data()
        exported_picking = self.get_exported_pickings()
        if not exported_picking:
            shipping_amount = self.convert_amount_to_company_currency(sum(shipping_line.mapped('price_subtotal')))
            shipping_tax = self.convert_amount_to_company_currency(sum(shipping_line.mapped('price_tax')))
        process_lines = []
        line_list = []
        for line in self.move_lines.filtered(lambda move: move.reserved_availability > 0):
            sale_line = line.sale_line_id
            line_data, sale_total_data = self.prepare_line_export_data(sale_line, move_id=line,
                                                                       process_lines=process_lines)
            if not line_data:
                return False
            process_lines.append(sale_line.id)
            line_list += line_data
            line.write({'shipstation_exported_qty': line.reserved_availability})
            total_amount += sale_total_data.get('total', 0)
            tax_amount += sale_total_data.get('tax', 0)
        order_data.update({
            "orderStatus": "awaiting_shipment",
            "amountPaid": total_amount + shipping_tax + shipping_amount + tax_amount,
            "taxAmount": tax_amount + shipping_tax,
            "shippingAmount": shipping_amount,
            'items': line_list,
            'requestedShippingService': self.carrier_id.shipstation_carrier_code or self.carrier_id.name
        })
        response, code = shipstation_instance.get_connection(url='/orders/createorder', data=order_data, method="POST")
        if code.status_code != 200:
            try:
                res = json.loads(code.content.decode('utf-8')).get('ExceptionMessage')
            except:
                res = code.content.decode('utf-8')
            msg = "106: Something went wrong while exporting order to ShipStation.\n\n %s", res
            _logger.exception(msg)
            raise UserError(msg)

        msg = "Order exported to ShipStation:<br/> ShipStation order id : %s" % (response.get('orderId'))
        self.unlink_old_message_and_post_new_message(body=msg)
        self.write({'shipstation_order_id': response.get('orderId'), 'is_exported_to_shipstation': True})

        # Update related outgoing picking in case of Multi-Step Routes
        is_multi_step = True if self.picking_type_id.warehouse_id.delivery_steps in ('pick_ship', 'pick_pack_ship') else False
        if is_multi_step:
            int_picks = self.get_internal_pickings()
            int_picks.write({'related_outgoing_picking': self.id})
        log_book.create_log_book_line_for_shipstation("Order Exported successfully", model_id, self)
        if not is_log_exist:
            log_book.unlink_log_book_without_log_lines()
        return True

    def get_shipstation_label(self):
        carrier_id = self.shipstation_service_id.shipstation_carrier_id
        instance = self.shipstation_instance_id
        ship_date = self.date_done.strftime("%Y-%m-%d")
        warehouse = self.picking_type_id.warehouse_id
        self.is_picking_contains_service_and_package()
        ship_from_partner = warehouse.partner_id
        ship_to_partner = self.partner_id
        try:
            total_weight = self.get_converted_weight_for_shipstation()
        except Exception as e:
            raise UserError(e)

        length, width, height = self.get_package_dimension()

        data = {
            "carrierCode": carrier_id.code,
            "serviceCode": self.shipstation_service_id.service_code,
            "packageCode": self.shipstation_package_id.shipper_package_code or 'package',
            "confirmation": self.confirmation,
            "shipDate": ship_date,
            "weight": {
                "value": total_weight,
                "units": self.carrier_id.shipstation_weight_uom or self.shipstation_instance_id.shipstation_weight_uom
            },
            "shipFrom": {
                "name": warehouse.display_name or '',  # Warehouse name
                "company": warehouse.company_id.display_name,  # warehouse company name
                "street1": ship_from_partner.street or '',
                "street2": ship_from_partner.street2 or '',
                "city": ship_from_partner.city or '',
                "state": ship_from_partner.state_id.code or '',
                "postalCode": ship_from_partner.zip or '',
                "country": ship_from_partner.country_id.code or '',
                "phone": ship_from_partner.phone or '',
                "residential": ''
            },
            "shipTo": {
                "name": ship_to_partner.name or '',
                "company": ship_to_partner.company_name or (
                        ship_to_partner.parent_id and ship_to_partner.parent_id.name) or '',
                "street1": ship_to_partner.street or '',
                "street2": ship_to_partner.street2 or '',
                "city": ship_to_partner.city or '',
                "state": ship_to_partner.state_id.code or '',
                "postalCode": ship_to_partner.zip or '',
                "country": ship_to_partner.country_id.code or '',
                "phone": ship_to_partner.phone or '',
                "residential": ''
            },
            "testLabel": not self.carrier_id.prod_environment
        }

        if length > 0 and width > 0 and height > 0:
            data.update({"dimensions": {
                "length": length,
                "width": width,
                "height": height,
                "units": "inches"
            }})

        response, code = instance.get_connection(url='/shipments/createlabel', data=data, method="POST")
        if code.status_code != 200:
            try:
                res = json.loads(code.content.decode('utf-8')).get('ExceptionMessage')
            except:
                res = code.content.decode('utf-8')
            msg = "107: Something went wrong while Getting label from \
                                            ShipStation.\n\n %s" % (
                res)
            self.unlink_old_message_and_post_new_message(body=msg)
            _logger.exception(msg)
            raise UserError(msg)

        binary_data = response.get('labelData', False)
        reference_code = response.get('trackingNumber')
        shipment_id = response.get('shipmentId')
        binary_data = binascii.a2b_base64(str(binary_data))
        message = ("Label created!<br/> <b>Label Tracking Number : </b>%s" % reference_code)
        self.write({'is_get_shipping_label': True,
                    'carrier_tracking_ref': reference_code,
                    'shipstation_shipment_id': shipment_id})
        self.unlink_old_message_and_post_new_message(body=message, attachments=[
            ('Label-%s.%s' % (reference_code, "pdf"), binary_data)])
        shipping_cost = self.convert_company_currency_amount_to_order_currency(response.get('shipmentCost', 0))
        shipping_data = [{
            'exact_price': shipping_cost,
            'tracking_number': reference_code}]
        return shipping_data

    def shipstation_ept_cancel_order(self):
        if not self.shipstation_order_id:
            raise UserError("Order is not having shipstation order number.")
        shipstation_store_id = self.shipstation_store_id
        if shipstation_store_id:
            if not self.weight:
                raise UserError("Weight of Picking not found..!")
            instance = shipstation_store_id.shipstation_instance_id
            data = self.prepare_order_export_data(is_cancel_order=True)
            data.update({"orderStatus": "cancelled"})
            response, code = instance.get_connection(url='/orders/createorder', data=data, method="POST")
            if code.status_code != 200:
                try:
                    res = json.loads(code.content.decode('utf-8')).get('ExceptionMessage')
                except:
                    res = code.content.decode('utf-8')
                msg = "108: Something went wrong while Cancelling order on ShipStation.\n\n %s" % res

                self.unlink_old_message_and_post_new_message(body=msg)
                _logger.exception(msg)
                return False
            if response.get('orderStatus') == "shipped":
                msg = "Order Cannot be Cancelled because it is 'Shipped' by ShipStation."
                self.unlink_old_message_and_post_new_message(body=msg)
                _logger.exception(msg)
                return False

            self.unlink_old_message_and_post_new_message(body="Order cancelled on ShipStation")
            self.write({
                'canceled_on_shipstation': True
            })
        return True

    def cancel_shipment_action(self):
        pickings = self.filtered(
            lambda x: x.shipstation_instance_id and x.carrier_tracking_ref and x.shipstation_shipment_id)
        for carrier in pickings.mapped('carrier_id'):
            carrier.shipstation_ept_cancel_shipment(pickings.filtered(lambda x: x.carrier_id == carrier))

    def is_picking_contains_service_and_package(self):
        if not self.shipstation_service_id or not self.shipstation_package_id:
            msg = "Need to select shipstation service and package in stock.picking to " \
                  "Export order to shipstation."
            self.unlink_old_message_and_post_new_message(body=msg)
            raise UserError(msg)
        return True

    def is_picking_contains_store(self):
        if not self.shipstation_store_id:
            msg = "Need to select shipstation Store in Picking for export order to shipstation."
            self.unlink_old_message_and_post_new_message(body=msg)
            raise UserError(msg)
        return True

    def prepare_order_export_data(self, is_cancel_order=False):
        order_id = self.sale_id
        order_date = (order_id.date_order.strftime("%Y-%m-%dT%H:%M:%S.0000000"))
        scheduled_date = (self.scheduled_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"))
        shipstation_warehouse = self.env['shipstation.warehouse.ept'].search(
            ['|', ('odoo_warehouse_id', '=', self.picking_type_id.warehouse_id.id),
             ('is_default', '=', True), ('shipstation_instance_id', '=', self.shipstation_instance_id.id)], limit=1)
        if not shipstation_warehouse:
            raise UserError('No ShipStation Warehouse Mapping available in Odoo.')
        try:
            total_weight = self.get_converted_weight_for_shipstation()
        except Exception as e:
            raise UserError(e)

        if self.carrier_id.get_cheapest_rates and self.shipstation_service_id:
            carrier_code = self.shipstation_service_id.shipstation_carrier_id.code or ''
            service_code = self.shipstation_service_id.service_code or ''
        elif not self.carrier_id.get_cheapest_rates and self.carrier_id.delivery_type == 'shipstation_ept':
            carrier_code = self.carrier_id.shipstation_carrier_id.code or ''
            service_code = self.carrier_id.shipstation_service_id.service_code or ''
        else:
            carrier_code = ''
            service_code = ''

        partner_shipping_id = order_id.partner_shipping_id
        partner_invoice_id = order_id.partner_invoice_id
        name = self.prepare_export_order_name(is_cancel_order)
        customer_email = self.get_email_address()

        length, width, height = self.get_package_dimension()

        data = {
            "orderNumber": name,
            "orderKey": name,
            "orderDate": order_date,
            "shipByDate": scheduled_date,
            "customerUsername": self.partner_id.name,
            "customerEmail": customer_email,
            "shippingAmount": self.shipping_rates,
            "packageCode": self.shipstation_package_id.shipper_package_code or '',
            "carrierCode": carrier_code,
            "serviceCode": service_code,
            "customerNotes": order_id.note,
            "weight": {
                "value": total_weight,
                "units": self.carrier_id.shipstation_weight_uom or self.shipstation_instance_id.shipstation_weight_uom
            },
            "billTo": {
                "name": partner_invoice_id.name or '',
                "company": partner_invoice_id.company_id.name or '',
                "street1": partner_invoice_id.street or '',
                "street2": partner_invoice_id.street2 or '',
                "city": partner_invoice_id.city or '',
                "state": partner_invoice_id.state_id.code or '',
                "postalCode": partner_invoice_id.zip or '',
                "country": partner_invoice_id.country_id.code or '',
                "phone": partner_invoice_id.phone or '',
            },
            "shipTo": {
                "name": partner_shipping_id.name or '',
                "company": partner_shipping_id.company_name or partner_shipping_id.parent_id.name or '',
                "street1": partner_shipping_id.street or '',
                "street2": partner_shipping_id.street2 or '',
                "city": partner_shipping_id.city or '',
                "state": partner_shipping_id.state_id.code or '',
                "postalCode": partner_shipping_id.zip or '',
                "country": partner_shipping_id.country_id.code or '',
                "phone": partner_shipping_id.phone or '',
            },
            "advancedOptions": {
                "warehouseId": shipstation_warehouse.shipstation_identification,
                "storeId": self.shipstation_store_id.shipstation_identification,
                "customField1": order_id and order_id.name or self.origin or '',
                "customField2": order_id and order_id.client_order_ref or ''
            }
        }

        if length > 0 and width > 0 and height > 0:
            data.update({"dimensions": {
                "length": length,
                "width": width,
                "height": height,
                "units": "inches"
            }})

        return data

    def _action_done(self):
        """
        Done pickings and make visible download button and send to shipper button based on
        condition.
        @return: return  response for done process
       """
        res = False
        for picking in self:
            try:
                with self._cr.savepoint():
                    res = super(StockPicking, picking)._action_done()
            except Exception as e:
                message = "Delivery Order : %s Description : %s" % (picking.name, e)
                picking.unlink_old_message_and_post_new_message(body=message)
                if picking.batch_id:
                    picking.batch_id.unlink_old_message_and_post_new_message(body=message)
                _logger.exception("Shipstation Error while processing for send to Shipper - Picking : %s \n %s",
                                  picking.name, e)
                continue
            if picking.carrier_tracking_ref and picking.batch_id and picking.shipstation_instance_id:
                picking.shipstation_send_to_shipper_process_done = True

        pickings_ready_for_download = self.filtered(lambda x: x.shipstation_send_to_shipper_process_done)
        if pickings_ready_for_download:
            pickings_ready_for_download.mapped('batch_id').shipstation_ready_for_download = True
        return res

    def is_order_shipped(self):
        url = '/orders/%s' % self.shipstation_order_id
        response, code = self.shipstation_instance_id.get_connection(url=url, data=None, params=None, method="GET")
        if code.status_code != 200:
            _logger.error("error when fetching the shipping status.")
            return False
        return response.get('orderStatus', '') == 'shipped'

    def get_exported_pickings(self):
        return self.sale_id.picking_ids.filtered(
            lambda pick: pick.shipstation_order_id and pick.id != self.id and pick.state != 'cancel')

    def prepare_line_export_data(self, line, move_id, process_lines):
        total_dict = {}
        product_data_list = []
        amount, tax = 0, 0
        ship_product_id = self.find_ship_station_product_id(line.product_id,
                                                            self.shipstation_instance_id)
        qty = move_id.reserved_availability if move_id.product_id == line.product_id else line.product_uom_qty
        if line and line.id not in process_lines and qty > 0:
            amount, tax = self.compute_tax_for_move_lines(line, qty)
            try:
                product_weight = self.get_converted_weight_for_shipstation(line.product_id.weight)
            except Exception as e:
                raise UserError(e)
            line_dict = {
                "lineItemKey": line.product_id.id,
                "sku": line.product_id.default_code or '',
                "upc": line.product_id.barcode or '',
                "name": line.product_id.name or '',
                "weight": {
                    "value": product_weight,
                    "units": self.carrier_id.shipstation_weight_uom or self.shipstation_instance_id.shipstation_weight_uom
                },
                "quantity": int(qty),
                "unitPrice": self.convert_amount_to_company_currency(
                    line.currency_id.round((line.price_subtotal / line.product_uom_qty))),
                "taxAmount": tax,
                "options": [
                    {
                        "name": "",
                        "value": ""
                    }
                ],
            }
            if ship_product_id:
                line_dict.update({"productId": ship_product_id.shipstation_identification})
            product_data_list.append(line_dict)
        if move_id and line and line.product_id != move_id.product_id:
            kit_data = self.prepare_line_export_data_for_kit_products(move_id)
            if not kit_data:
                return False, total_dict
            product_data_list.append(kit_data)
        total_dict.update({'total': amount, 'tax': tax})
        return product_data_list, total_dict

    def prepare_line_export_data_for_kit_products(self, move_id):
        ship_product_id = self.find_ship_station_product_id(move_id.product_id,
                                                            self.shipstation_instance_id)
        try:
            product_weight = self.get_converted_weight_for_shipstation(move_id.product_id.weight)
        except Exception as e:
            raise UserError(e)
        product_dict = {
            "lineItemKey": move_id.product_id.id,
            "sku": move_id.product_id.default_code or '',
            "upc": move_id.product_id.barcode or '',
            "name": move_id.product_id.name or '',
            "weight": {
                "value": product_weight
            },
            "quantity": int(move_id.reserved_availability),
            "unitPrice": 0.0,
            "taxAmount": 0.0,
            "options": [
                {
                    "name": "",
                    "value": ""
                }
            ],
        }
        if ship_product_id:
            product_dict.update({"productId": ship_product_id.shipstation_identification})
        return product_dict

    def find_ship_station_product_id(self, product_id, shipstation_instance_id):
        ship_product_id = self.env['shipstation.product.ept'].search(
            [('product_id', '=', product_id.id),
             ('shipstation_instance_id', '=', shipstation_instance_id.id)], limit=1)
        return ship_product_id

    def get_converted_weight_for_shipstation(self, weight=0):
        return self.carrier_id.convert_weight_for_shipstation(
            self.company_id.get_weight_uom_id(),
            self.carrier_id.shipstation_weight_uom_id or self.shipstation_instance_id.weight_uom_id,
            weight or self.weight)

    def compute_tax_for_move_lines(self, line, qty):
        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
        taxes = line.tax_id.compute_all(price, line.order_id.currency_id, qty, product=line.product_id,
                                        partner=line.order_id.partner_shipping_id)
        tax = self.convert_amount_to_company_currency(sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])))
        amount = self.convert_amount_to_company_currency(
            line.currency_id.round((line.price_subtotal / line.product_uom_qty) * qty))
        return amount, tax

    def prepare_export_order_name(self, is_cancel_order=False):
        order_id = self.sale_id
        is_multi_step = True if self.picking_type_id.warehouse_id.delivery_steps in ('pick_ship', 'pick_pack_ship') else False
        is_internal_name = self.env['ir.config_parameter'].sudo().get_param('shipstation.internal_picking_name')
        if is_multi_step and is_internal_name == 'True':
            if not is_cancel_order:
                int_pick = self.get_internal_pickings() if not self.shipstation_order_id else self.get_exported_internal_pickings()
            else:
                int_pick = self.get_exported_internal_pickings()
            # We are not passing sale order reference in case of multistep delivery,
            # And keep sale order reference in single step delivery
            # because current customers not face any name related changes
            name = '{}'.format(int_pick and int_pick[0].name or '')
        else:
            name = '{}-{}'.format(order_id.name, self.name)
        return name

    def get_internal_pickings(self):
        return self.sale_id.picking_ids.filtered(
            lambda pick: pick.picking_type_id.code == 'internal'
                         and not pick.related_outgoing_picking
                         and pick.location_dest_id.id == self.location_id.id
                         and pick.state == 'done').sorted(key=lambda r: r.id)

    def get_exported_internal_pickings(self):
        return self.sale_id.picking_ids.filtered(lambda pick: pick.picking_type_id.code == 'internal'
                                                              and pick.state == 'done'
                                                              and pick.related_outgoing_picking.id == self.id).sorted(
            key=lambda r: r.id)

    def raise_warning_if_shipstation_carrier_not_found(self):
        if not self.carrier_id:
            raise UserError("Carrier is missing!!!")
        if self.carrier_id.delivery_type != 'shipstation_ept':
            raise UserError("No shipstation carrier found into picking {}".format(self.name))

    def unlink_old_message_and_post_new_message(self, body, attachments=[]):
        message_ids = self.env["mail.message"].sudo().search(
            [('model', '=', 'stock.picking'), ('res_id', '=', self.id), ('body', '=ilike', body)])
        message_ids.unlink()
        self.message_post(body=body, attachments=attachments)

    def find_outgoing_pickings_of_sale_order_and_export_to_shipstation(self):
        pending_outgoing_pickings = self.sale_id.picking_ids.filtered(
            lambda pick: pick.state != "done"
                         and pick.picking_type_id.code == "outgoing"
                         and not pick.shipstation_order_id and pick.shipstation_instance_id)
        if pending_outgoing_pickings:
            for picking in pending_outgoing_pickings:
                if picking.state in ('waiting', 'assigned'):
                    picking.action_assign()
                    if picking.state == 'assigned':
                        picking.export_order_to_shipstation()

    def action_cancel(self):
        for picking in self:
            if picking.shipstation_instance_id:
                result = False
                if not picking.is_exported_to_shipstation or not picking.shipstation_order_id:
                    _logger.info("Cannot cancel on ShipStation : {}, "
                                 "as it is pending to be exported to ShipStation".format(picking.id))
                    continue
                if not picking.shipstation_store_id:
                    _logger.info("Cannot cancel on ShipStation : {}, "
                                 "as ShipStation store not available in picking".format(picking.id))
                    continue
                if not picking.weight:
                    _logger.info("Cannot cancel on ShipStation : {}, "
                                 "as Weight of Picking not found".format(picking.id))
                    continue
                try:
                    result = picking.shipstation_ept_cancel_order()
                except Exception as e:
                    _logger.info("Error {} comes at the time of cancel order on ShipStation {}".format(e, picking.name))
                    self -= picking
                    continue
                if not result:
                    self -= picking
        res = super(StockPicking, self).action_cancel()
        return res

    def convert_amount_to_company_currency(self, amount):
        """
        Convert amount to company currency
        """
        if self.sale_id and amount:
            rate = self.env['res.currency']._get_conversion_rate(self.sale_id.currency_id, self.company_id.currency_id,
                                                                 self.company_id, datetime.now())
            return self.company_id.currency_id.round(amount * rate)
        return amount

    def convert_company_currency_amount_to_order_currency(self, amount):
        """
        Convert amount from USD currency to order or company currency
        """
        if amount:
            from_currency = self.carrier_id.shipstation_carrier_id.carrier_rate_currency_id \
                            or self.company_id.currency_id
            to_currency = self.sale_id.currency_id or self.company_id.currency_id
            rate = self.env['res.currency']._get_conversion_rate(from_currency, to_currency,
                                                                 self.company_id, datetime.now())
            if self.sale_id:
                return self.sale_id.currency_id.round(amount * rate)
            else:
                return self.company_id.currency_id.round(amount * rate)
        return amount

    def set_carrier_based_on_response(self, response):
        """
        Update the Carrier, Shipstation service and Package based on shipstation shipment response
        """
        if len(response.get('shipments')):
            vals = {}
            rec = response.get('shipments')[0]
            instance = self.shipstation_instance_id
            carrier = self.env['delivery.carrier']
            service = self.env["shipstation.services.ept"]
            ship_station_carrier = self.env["shipstation.carrier.ept"]
            if rec.get('carrierCode', ''):
                ship_station_carrier = ship_station_carrier.search(
                    [('shipstation_instance_id', '=', instance.id), ('code', '=', rec.get('carrierCode', ''))], limit=1)
            if rec.get('serviceCode', '') and self.shipstation_service_id.service_code != rec.get('serviceCode'):
                service = service.search([('service_code', '=', rec.get('serviceCode')),
                                          ('shipstation_carrier_id', '=', ship_station_carrier.id)], limit=1)
                service and vals.update({'shipstation_service_id': service.id})
            if self.shipstation_package_id.shipper_package_code != rec.get('packageCode'):
                package_id = self.env['product.packaging'].search(
                    [('package_carrier_type', '=', instance.provider),
                     ('shipstation_carrier_id', '=', ship_station_carrier.id),
                     ('shipper_package_code', '=', rec.get('packageCode'))], limit=1)
                package_id and vals.update({'shipstation_package_id': package_id.id})
            if ship_station_carrier:
                carrier = carrier.search(
                    [('shipstation_carrier_id', '=', ship_station_carrier.id),
                     ('delivery_type', '=', 'shipstation_ept'),
                     ('shipstation_instance_id', '=', instance.id),
                     ('shipstation_service_id', '=', service.id)], limit=1)
                carrier and vals.update({'carrier_id': carrier.id})
            vals and self.write(vals)
        return True

    def is_order_pick_ship(self):
        return True if self.picking_type_id.warehouse_id.delivery_steps in ('pick_ship', 'pick_pack_ship') else False

    def find_outgoing_picking(self):
        return self.sale_id.picking_ids.filtered(lambda pick: pick.state == "assigned"
                                                              and pick.picking_type_id.code == "outgoing"
                                                              and pick.export_order).mapped(
            'move_lines').filtered(lambda line: line.reserved_availability).mapped('picking_id')

    def check_is_order_shipped_and_create_back_order(self):
        order_shipped = self.is_order_shipped()
        if order_shipped:
            ship_order_ref = self.shipstation_order_id
            _logger.info(
                "Picking {}:{}, Order Id: {} already shipped".format(self.id, self.name, ship_order_ref))
            for move in self.move_lines:
                move.write({'quantity_done': move.shipstation_exported_qty})
            wiz = self.button_validate()
            if wiz and isinstance(wiz, dict):
                try:
                    wiz = Form(self.env['stock.backorder.confirmation'].with_context(wiz['context'])).save()
                    wiz.with_context(button_validate_picking_ids=[self.id]).process()
                except Exception as e:
                    _logger.info("Error {} comes at the time of validating picking {}".format(e, self.name))
                    return False
            if wiz and not self.state == 'done':
                return False
        return True

    def find_related_outgoing_picking_and_export(self):
        outgoing_pickings = self.find_outgoing_picking()
        if outgoing_pickings:
            _logger.info("Start Process for Internal Picking: {}, Sale Order: {}".format(self.id, self.sale_id.name))
        for picking in outgoing_pickings:
            _logger.info("Pickings {}:{}, Shipstation Order Id: {}".format(picking.id, picking.name,
                                                                           picking.shipstation_order_id))
            picking.export_order_to_shipstation()
        return True

    def get_email_address(self):
        """
        Use : Get the customer email address in below flow for export order to ShipStation
                1. Email address of the shipping address.
                2. Email address of the parent partner of the shipping partner
                3. Email address of the sales order’s customer
                4. Email address of the billing address
        Added By : Rajnik Vaishnav @ Emipro Technologies
        Task : 187777
        """
        if self.partner_id.email:
            return self.partner_id.email
        else:
            if self.partner_id.parent_id and self.partner_id.parent_id.email:
                return self.partner_id.parent_id.email
            else:
                if self.sale_id:
                    if self.sale_id.partner_id.email:
                        return self.sale_id.partner_id.email
                    elif self.sale_id.partner_invoice_id.email:
                        return self.sale_id.partner_invoice_id.email
        return ''
