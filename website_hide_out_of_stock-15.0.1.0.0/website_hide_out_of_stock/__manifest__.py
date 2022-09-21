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
  "name"                 :  "Website Hide Out Of Stock Products",
  "summary"              :  """The module hides the products that are out of stock from the shop page on Odoo website.""",
  "category"             :  "Website",
  "version"              :  "1.0.0",
  "sequence"             :  1,
  "author"               :  "Webkul Software Pvt. Ltd.",
  "license"              :  "Other proprietary",
  "website"              :  "https://store.webkul.com/Odoo-Website-Auto-Hide-Out-Of-Stock-Products.html",
  "description"          :  """Website Hide Out Of Stock Products
Remove stock out products
Restrict out of stock orders
Auto hide out of stock products""",
  "live_test_url"        :  "http://odoodemo.webkul.com/?module=website_hide_out_of_stock",
  "depends"              :  ['website_stock'],
  "data"                 :  [
                             'views/product_template.xml',
                             'views/cron.xml',
                             'views/res_config_settings.xml',
                            ],
  "images"               :  ['static/description/Banner.png'],
  "application"          :  True,
  "installable"          :  True,
  "auto_install"         :  False,
  "price"                :  21,
  "currency"             :  "USD",
  "pre_init_hook"        :  "pre_init_check",
}