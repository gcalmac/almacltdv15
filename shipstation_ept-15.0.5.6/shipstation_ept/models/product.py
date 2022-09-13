import logging

from odoo import models

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    """
    Inheriting product.product to implementation og Shipstation integration.
    """
    _inherit = 'product.product'

    def create_shipstation_product(self):
        """
        to create product records in the shipstation layer
        @return:
        """
        shipstation_product_obj = self.env['shipstation.product.ept']

        model_id = self.env['ir.model'].sudo().search([('model', '=', self._name)]).id
        log_book = self.env['common.log.book.ept'].create_shipstation_log('export', model_id)

        instance = self.env['shipstation.instance.ept'].search([('company_id', '=', self.env.company.id)], limit=1)
        if not instance:
            log_book.create_log_book_line_for_shipstation(
                "Shipstation instance not found for company {}..".format(self.env.company.name), model_id)
            return True
        _logger.info('Shipstation product create for instance %s', instance.name)

        for product in self:
            _logger.info('creating shipstation product for product: %s', product.id)
            try:
                existing_shipstation_product = shipstation_product_obj.search(
                    [('shipstation_sku', '=', product.default_code), ('shipstation_instance_id', '=', instance.id)])
                if existing_shipstation_product:
                    log_book.create_log_book_line_for_shipstation(("Shipstation product already exist! "
                                                                   "Product : %s" % product.id), model_id)
                    continue
                shipstation_product_obj.create({
                    'name': product.name,
                    'product_id': product.id,
                    'shipstation_identification': "",
                    'shipstation_sku': product.default_code,
                    'shipstation_instance_id': instance.id,
                    'height': 0,
                    'width': 0,
                    'length': 0,
                    'weight': self.env.company.get_weight_uom_id()._compute_quantity(
                        product.weight,
                        self.env.ref(
                            "uom.product_uom_oz"))
                })
                log_book.create_log_book_line_for_shipstation("Shipstation product created in odoo.", model_id)
            except Exception as exception:
                msg = "Error while creating shipstation product for {}. error: {}".format(product.id, exception)
                _logger.info(msg)
                log_book.create_log_book_line_for_shipstation(msg, model_id)
                continue
        log_book.unlink_log_book_without_log_lines()
