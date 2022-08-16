# Copyright 2019 Sodexis
# License OPL-1 (See LICENSE file for full copyright and licensing details).

import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PurchaseAdvancePaymentInv(models.TransientModel):
    _name = "purchase.advance.payment.inv"
    _description = "Purchase Advance Payment"

    @api.model
    def _count(self):
        return len(self._context.get("active_ids", []))

    @api.model
    def _default_product_id(self):
        product_id = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("purchase.default_deposit_product_id")
        )
        return self.env["product.product"].browse(int(product_id))

    @api.model
    def _get_advance_payment_method(self):
        if self._count() == 1:
            purchase_obj = self.env["purchase.order"]
            order = purchase_obj.browse(self._context.get("active_ids"))[0]
            if (
                order.order_line.filtered(lambda dp: dp.is_downpayment)
                and order.invoice_ids.filtered(
                    lambda invoice: invoice.state != "cancel"
                )
                or order.order_line.filtered(lambda l: l.qty_to_invoice < 0)
            ):
                return "all"
            elif order.invoice_status == "invoiced":
                return "percentage"
            else:
                return "delivered"
        return "all"

    advance_payment_method = fields.Selection(
        [
            ("delivered", "Invoiceable lines"),
            ("all", "Invoiceable lines (deduct down payments)"),
            ("percentage", "Down payment (percentage)"),
            ("fixed", "Down payment (fixed amount)"),
        ],
        string="What do you want to bill?",
        default=_get_advance_payment_method,
    )
    amount = fields.Float(
        "Down Payment Amount",
        digits="Account",
        help="The amount to be invoiced in advance, taxes excluded.",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Down Payment Product",
        domain=[("type", "=", "service")],
        default=_default_product_id,
    )
    count = fields.Integer(default=_count, string="Order Count")

    def _create_invoice(self, order, po_line, amount):
        inv_obj = self.env["account.move"]
        ir_property_obj = self.env["ir.property"]

        account_id = False
        if self.product_id.id:
            account_id = order.fiscal_position_id.map_account(
                self.product_id.property_account_expense_id
                or self.product_id.categ_id.property_account_expense_categ_id
            ).id
        if not account_id:
            inc_acc = ir_property_obj._get(
                "property_account_expense_categ_id", "product.category"
            )
            account_id = (
                order.fiscal_position_id.map_account(inc_acc).id if inc_acc else False
            )
        if not account_id:
            raise UserError(
                _(
                    'There is no Expense account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.'
                )
                % (self.product_id.name,)
            )

        if self.amount <= 0.00:
            raise UserError(_("The value of the down payment amount must be positive."))
        context = {"lang": order.partner_id.lang}
        if self.advance_payment_method == "percentage":
            amount = order.amount_untaxed * self.amount / 100
            name = _("Down payment of %s%%") % (self.amount,)
        else:
            amount = self.amount
            name = _("Down Payment")
        del context
        taxes = self.product_id.taxes_id.filtered(
            lambda r: not order.company_id or r.company_id == order.company_id
        )
        if order.fiscal_position_id and taxes:
            tax_ids = order.fiscal_position_id.map_tax(
                taxes, self.product_id, order.partner_id
            ).ids
        else:
            tax_ids = taxes.ids
        invoice = inv_obj.create(
            {
                "partner_id": order.partner_id.id,
                "currency_id":order.partner_id.property_purchase_currency_id or order.partner_id.currency_id,
                "move_type": "in_invoice",
                "invoice_origin": order.name,
                "ref": False,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": name,
                            "account_id": account_id,
                            "price_unit": amount,
                            "quantity": 1.0,
                            "product_uom_id": self.product_id.uom_id.id,
                            "product_id": self.product_id.id,
                            "purchase_line_id": po_line.id,
                            "tax_ids": [(6, 0, tax_ids)],
                            "analytic_tag_ids": [(6, 0, po_line.analytic_tag_ids.ids)],
                        },
                    )
                ],
                "fiscal_position_id": order.fiscal_position_id.id
                or order.partner_id.property_account_position_id.id,
                "purchase_id": order.id,
            }
        )
        invoice.message_post_with_view(
            "mail.message_origin_link",
            values={"self": invoice, "origin": order},
            subtype_id=self.env.ref("mail.mt_note").id,
        )

        return invoice

    def _prepare_order_line(self, amount, tax_ids, analytic_tag_ids, order):
        res = {
            "name": _("Advance: %s") % (time.strftime("%m %Y"),),
            "price_unit": amount,
            "product_qty": 0.0,
            "order_id": order.id,
            "product_uom": self.product_id.uom_id.id,
            "product_id": self.product_id.id,
            "analytic_tag_ids": analytic_tag_ids,
            "taxes_id": [(6, 0, tax_ids)],
            "is_downpayment": True,
            "date_planned": order.date_order,
        }
        return res

    def create_vendor_bills(self):
        purchase_orders = self.env["purchase.order"].browse(
            self._context.get("active_ids", [])
        )
        company_id = purchase_orders.mapped('company_id')
        if company_id:
            self = self.with_company(company_id).with_context(default_company_id=company_id.id)
        if self.advance_payment_method == "delivered":
            self.check_invoice_status(purchase_orders)
            self.env.context = dict(self.env.context)
            self.env.context.update({"without_downpayment": True})
            journal_id = self.env["account.journal"].search(
                [("type", "in", ["purchase"]), ("company_id", "=", company_id.id)], limit=1
            )
            inv = self.env["account.move"].create({"move_type": "in_invoice", "journal_id":journal_id.id})
            inv.update({"purchase_id": purchase_orders.id})
            inv._onchange_purchase_auto_complete()
            if all(
                line.purchase_line_id.is_downpayment for line in inv.invoice_line_ids
            ):
                for line in inv.invoice_line_ids:
                    line.quantity = 1
                inv.move_type = "in_refund"
        elif self.advance_payment_method == "all":
            if not any(line.is_downpayment for line in purchase_orders.order_line):
                self.check_invoice_status(purchase_orders)
            self.env.context = dict(self.env.context)
            self.env.context.update({"final": True, "final_payment": True})
            journal_id = self.env["account.journal"].search(
                [("type", "in", ["purchase"]), ("company_id", "=", company_id.id)], limit=1
            )
            inv = self.env["account.move"].create({"move_type": "in_invoice", "journal_id":journal_id.id})
            inv.update({"purchase_id": purchase_orders.id})
            inv._onchange_purchase_auto_complete()
            if all(
                line.purchase_line_id.is_downpayment for line in inv.invoice_line_ids
            ):
                for line in inv.invoice_line_ids:
                    line.quantity = 1
                inv.move_type = "in_refund"
        else:
            purchase_line_obj = self.env["purchase.order.line"]
            for order in purchase_orders:
                if self.advance_payment_method == "percentage":
                    amount = order.amount_untaxed * self.amount / 100
                else:
                    amount = self.amount
                if self.product_id.purchase_method != "purchase":
                    raise UserError(
                        _(
                            'The down payment product should have a control policy set to "Ordered quantities". Please update your down payment product.'
                        )
                    )
                if self.product_id.type != "service":
                    raise UserError(
                        _(
                            "The down payment product should be of type 'Service'. Please use another product or update this product."
                        )
                    )
                taxes = self.product_id.taxes_id.filtered(
                    lambda r: not order.company_id or r.company_id == order.company_id
                )
                if order.fiscal_position_id and taxes:
                    tax_ids = order.fiscal_position_id.map_tax(
                        taxes, self.product_id, order.partner_id
                    ).ids
                else:
                    tax_ids = taxes.ids
                context = {"lang": order.partner_id.lang}
                analytic_tag_ids = []
                for line in order.order_line:
                    analytic_tag_ids = [
                        (4, analytic_tag.id, None)
                        for analytic_tag in line.analytic_tag_ids
                    ]
                po_line = purchase_line_obj.create(
                    self._prepare_order_line(amount, tax_ids, analytic_tag_ids, order)
                    )
                del context
                self._create_invoice(order, po_line, amount)
        ctx =  dict(self.env.context)
        ctx['purchase_bill'] = True
        purchase_orders = purchase_orders.with_context(ctx)
        if self._context.get("create_bill", False):
            return purchase_orders.action_view_invoice()
        return {"type": "ir.actions.act_window_close"}

    def check_invoice_status(self, purchase_order):
        if purchase_order and purchase_order.invoice_status in ["invoiced", "no"]:
            raise UserError(_("There is nothing to invoice."))
