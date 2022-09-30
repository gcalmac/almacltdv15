# -*- coding: utf-8 -*-
{
    'name': 'Website Language Flag with Image & Name',
    'summary': 'Shows Language Flag with image and Name on website',
    'description': 'Shows Language Flag with image and Name on website',

    'author': 'iPredict IT Solutions Pvt. Ltd.',
    'website': 'http://ipredictitsolutions.com',
    "support": "ipredictitsolutions@gmail.com",

    'category': 'Website',
    'version': '15.0.0.1.0',
    'depends': ['website'],

    'data': [
        'views/website_templates.xml',
    ],

    'license': "OPL-1",
    'price': 5,
    'currency': 'EUR',

    'installable': True,

    'images': ['static/description/banner.png'],
    'pre_init_hook': 'pre_init_check',
}
