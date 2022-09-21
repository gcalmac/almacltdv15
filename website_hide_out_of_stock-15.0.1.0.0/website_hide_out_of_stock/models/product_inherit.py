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
    _inherit = 'product.template'

    def get_available(self,is_dynamic=True):
        website = self.env['website']
        config_setting = self.env['website.stock.config.settings'].sudo().search([])
        copy_context = self._context.copy()
        config_vals = website.get_config_settings_values()

        if config_vals.get('wk_warehouse_type') == 'specific':
            stock_location_id = config_vals.get('wk_stock_location')
            copy_context.update({'location': int(stock_location_id)})

        for rec in self.with_context(copy_context):
            quantity = website.get_product_stock_qty(rec, config_vals.get('wk_stock_type'))
            if config_setting.wk_cron == 'dynamic' and is_dynamic:
                rec.product_available_dynamic = True if quantity > 0 else False
            else:
                rec.product_available = True if quantity > 0 else False

    @api.model
    def set_availability_cron(self):
        products = self.env['product.template'].search([])
        for product in products:
            product.get_available(is_dynamic=False)
    
    def update_product_availability(self):
        self.get_available(is_dynamic=False)

    def _product_available_search(self, operator, value):
        product_ids = []
        for obj in self.sudo().search([]):
            if obj.product_available_dynamic:
                product_ids.append(obj.id)
        return [('id', 'in', product_ids)]


    product_available = fields.Boolean(string="Product Available")
    product_available_dynamic = fields.Boolean(compute='get_available', string="Product Available", search='_product_available_search')


class Website(models.Model):
    _inherit = 'website'


    def sale_product_domain(self):
        vals = super(Website, self).sale_product_domain()
        config_setting = self.env['website.stock.config.settings'].sudo().search([])
        if config_setting.wk_cron == 'dynamic':
            vals += [('product_available_dynamic', '=', True)]
        elif config_setting.wk_cron == 'run_cron':
            vals += [('product_available', '=', True)]
        return vals
