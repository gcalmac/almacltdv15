"""
Emipro Technologies Private Limited
Author : Ravi Kotadiya | ravik@emiprotechnologies.com
Date : Oct-26-2021
"""
from odoo import fields, models, api


class ProductPackaging(models.Model):
    """
    inheriting product.packaging for shipstation implementation.
    """
    _inherit = 'product.packaging'

    package_carrier_type = fields.Selection([('none', 'No carrier integration'), ('shipstation_ept', 'Shipstation')],
                                            default='none')
    shipstation_carrier_id = fields.Many2one('shipstation.carrier.ept',
                                             string='Shipstation Carrier')
    shipstation_instance_id = fields.Many2one('shipstation.instance.ept',
                                              string='Shipstation Instance')
    height = fields.Integer('Height (in)')
    width = fields.Integer('Width (in)')
    packaging_length = fields.Integer('Length (in)')
    max_weight = fields.Float('Max Weight', help='Maximum weight shippable in this packaging')
    shipper_package_code = fields.Char('Package Code')

    @api.model
    def create(self, vals):
        """
        Method created by: Hardik Joshi on 08-06-2022
        Add: override create method
        Task No. and Description: 192229 - Pass package dimension to ShipStation
        """
        if vals.get('shipstation_carrier_id', False):
            current_carrier_id = self.env["shipstation.carrier.ept"].browse(vals.get('shipstation_carrier_id'))
            vals.update({
                "shipstation_instance_id": current_carrier_id.shipstation_instance_id.id,
                "company_id": current_carrier_id.company_id.id,
                "package_carrier_type": 'shipstation_ept'
            })
        return super(ProductPackaging, self).create(vals)
