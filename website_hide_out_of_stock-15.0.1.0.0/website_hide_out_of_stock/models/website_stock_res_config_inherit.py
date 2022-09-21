# -*- coding: utf-8 -*-
#################################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
#################################################################################

from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'website.stock.config.settings'

    wk_cron = fields.Selection([('run_cron', 'Update throug cron'), ('dynamic', 'Update dynamically'), (
        'off', 'Show out of stock')], string='Select Method', required="1", default="off")

    @api.onchange("wk_cron")
    def activate_cron_template(self):
        cron_obj = self.env.ref('website_hide_out_of_stock.ir_cron_scheduler_avalability')

        cron = self.env["ir.cron"].browse(int(cron_obj))

        if self.wk_cron == 'run_cron':
            cron.write({"active":True})
        else:
            cron.write({"active":False})

    
    def open_cron(self):
        cron_id = self.env.ref('website_hide_out_of_stock.ir_cron_scheduler_avalability')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Configure Product Availability Cron',
            'view_mode': 'form',
            'res_model': 'ir.cron',
            'res_id': cron_id,
            'target': 'current',
            'domain': '[]',
        }

    def set_availability_manually(self):
        products = self.env['product.template'].search([])
        for product in products:
            product.get_available(is_dynamic=False)
