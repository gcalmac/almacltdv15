# Copyright 2019-20 Sodexis
# License OPL-1 (See LICENSE file for full copyright and licensing details).

{
    "name": "Purchase Order Down Payments",
    "summary": """ This module extends the functionality of Odoo 14 to add down payments for the purchase order.
        """,
    "version": "14.0.1.0.1",
    "category": "Purchase",
    "website": "https://www.sodexis.com/",
    "author": "Sodexis",
    "license": "OPL-1",
    "installable": True,
    "depends": ["purchase",],
    "data": [
        "security/ir.model.access.csv",
        "wizard/purchase_make_invoice_advance_views.xml",
        "views/purchase_management_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "price": 49.00,
    "currency": "USD",
}
