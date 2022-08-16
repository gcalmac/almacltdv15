# Copyright 2019 Sodexis
# License OPL-1 (See LICENSE file for full copyright and licensing details)

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    deposit_default_purchase_product_id = fields.Many2one(
        "product.product",
        "Purchase Deposit Product",
        domain="[('type', '=', 'service')]",
        config_parameter="purchase.default_deposit_product_id",
        help="Default product used for purchase payment advances",
    )
