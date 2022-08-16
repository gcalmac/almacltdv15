from odoo import models


class ResCompany(models.Model):
    """
    Inherit the res.company class for add new method
    """
    _inherit = "res.company"

    def get_weight_uom_id(self):
        """
        Get the weight UOM id
        """
        product_weight_in_lbs_param = self.env['ir.config_parameter'].sudo().get_param('product.weight_in_lbs')
        if product_weight_in_lbs_param == '1':
            return self.env.ref('uom.product_uom_lb', raise_if_not_found=False)
        else:
            return self.env.ref('uom.product_uom_kgm', raise_if_not_found=False)
