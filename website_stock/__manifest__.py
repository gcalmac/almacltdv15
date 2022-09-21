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
{
  "name"                 :  "Website Product Stock",
  "summary"              :  """Display Product stock on website product page.""",
  "category"             :  "Website",
  "version"              :  "1.0.8",
  "sequence"             :  1,
  "author"               :  "Webkul Software Pvt. Ltd.",
  "license"              :  "Other proprietary",
  "website"              :  "https://store.webkul.com/Odoo-Website-Product-Stock.html",
  "description"          :  """http://webkul.com/blog/website-product-stock/""",
  "live_test_url"        :  "http://odoodemo.webkul.com/?module=website_stock",
  "depends"              :  [
                             'website_sale_stock',
                             'website_webkul_addons',
                            ],
  "data"                 :  [
                             'security/ir.model.access.csv',
                             'views/res_config_view.xml',
                             'views/webkul_addons_config_inherit_view.xml',
                             'data/stock_config_demo.xml',
                             'views/website_stock_extension.xml',
                             'views/templates.xml',
                            ],
  'assets': {
        'web.assets_frontend': [
            'website_stock/static/src/js/website_stock_main.js',
            'website_stock/static/src/js/stock_quntity_vaildation.js',
            'website_stock/static/src/js/stock_checkout_validation.js',
            'website_stock/static/src/css/website_stock.css',
        ],
    },
  "images"               :  ['static/description/Banner.png'],
  "application"          :  True,
  "installable"          :  True,
  "auto_install"         :  False,
  "price"                :  39,
  "currency"             :  "USD",
  "pre_init_hook"        :  "pre_init_check",
}