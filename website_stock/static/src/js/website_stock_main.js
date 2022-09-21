odoo.define('website_stock.stock_main', function (require) {
    "use strict";
    
    var publicWidget = require('web.public.widget');
    var wSaleUtils = require('website_sale.utils');
    var VariantMixin = require('sale.VariantMixin');
    
    publicWidget.registry.WebsiteStockMain = publicWidget.Widget.extend(VariantMixin, {
        selector: '.oe_website_sale',
        events: {
            'change input.product_id': '_onChangeVariant',
        },
        _onChangeVariant: function (ev) {
            var product = $(ev.target).val();
            var value = $('#' + product).attr('value');
            var allow = $('#' + product).attr('allow');
            $('.stock_info_div').hide();
            $('#' + product + '.stock_info_div').show();
            if (value <= 0 && allow === 'deny') {
                $('#add_to_cart').hide().addClass('disabled');
                $('.css_quantity').removeClass('d-inline-flex').addClass('d-none');
            } else {
                $('#add_to_cart').show().removeClass('disabled');
                $('.css_quantity').addClass('d-inline-flex').removeClass('d-none');
            }
        },
    });
});

/* Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* Responsible Developer:- Sunny Kumar Yadav */