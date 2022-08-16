# Copyright 2019 Sodexis
# License OPL-1 (See LICENSE file for full copyright and licensing details)

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    @api.depends("qty_invoiced", "qty_received", "product_uom", "order_id.state")
    def _get_to_invoice_qty(self):
        """
        Compute the quantity to invoice. If the invoice policy is order, the quantity to invoice is
        calculated from the ordered quantity. Otherwise, the quantity received is used.
        """
        for line in self:
            if line.order_id.state in ["purchase", "done"]:
                if line.product_id.purchase_method == "purchase":
                    line.qty_to_invoice = line.product_qty - line.qty_invoiced
                else:
                    line.qty_to_invoice = line.qty_received - line.qty_invoiced
            else:
                line.qty_to_invoice = 0

    is_downpayment = fields.Boolean(
        string="Is a down payment",
        help="Down payments are made when creating invoices from a purchase order."
        " They are not copied when duplicating a purchase order.",
    )
    qty_to_invoice = fields.Float(
        compute="_get_to_invoice_qty",
        string="To Invoice Quantity",
        store=True,
        readonly=True,
        digits="account",
    )

    def unlink(self):
        if self.filtered(
            lambda line: line.state in ("purchase", "done")
            and (line.invoice_lines or not line.is_downpayment)
        ):
            raise UserError(
                _(
                    "You can not remove an order line once the Purchase order is confirmed.\nYou should rather set the quantity to 0."
                )
            )
        return super(PurchaseOrderLine, self).unlink()

    @api.depends("invoice_lines.move_id.state", "invoice_lines.quantity")
    def _compute_qty_invoiced(self):
        for line in self:
            qty = 0.0
            for inv_line in line.invoice_lines:
                if inv_line.move_id.state not in ["cancel"]:
                    if inv_line.move_id.move_type == "in_invoice":
                        qty += inv_line.product_uom_id._compute_quantity(
                            inv_line.quantity, line.product_uom
                        )
                    elif inv_line.move_id.move_type == "in_refund":
                        qty -= inv_line.product_uom_id._compute_quantity(
                            inv_line.quantity, line.product_uom
                        )
            line.qty_invoiced = qty

    @api.depends("product_qty", "price_unit", "taxes_id")
    def _compute_amount(self):
        super()._compute_amount()
        for line in self.filtered(lambda x: x.is_downpayment):
            line.update({"price_subtotal": 0.0})

    def _prepare_account_move_line(self, move=False):
        self.ensure_one()
        if self._context.get("final_payment") and self.is_downpayment:
            if self.product_id.purchase_method == "purchase":
                qty = self.qty_invoiced
            else:
                qty = self.qty_received - self.qty_invoiced

            if self.currency_id == move.company_id.currency_id:
                currency = False
            else:
                currency = move.currency_id

            return {
                "name": "{}: {}".format(self.order_id.name, self.name),
                "move_id": move.id,
                "currency_id": currency and currency.id or False,
                "purchase_line_id": self.id,
                "date_maturity": move.invoice_date_due,
                "product_uom_id": self.product_uom.id,
                "product_id": self.product_id.id,
                "price_unit": self.price_unit,
                "quantity": qty,
                "partner_id": move.partner_id.id,
                "analytic_account_id": self.account_analytic_id.id,
                "analytic_tag_ids": [(6, 0, self.analytic_tag_ids.ids)],
                "tax_ids": [(6, 0, self.taxes_id.ids)],
                "display_type": self.display_type,
            }
        elif self.is_downpayment:
            if self.product_id.purchase_method == "purchase":
                qty = self.product_qty - self.qty_invoiced
            else:
                qty = self.qty_received - self.qty_invoiced

            if self.currency_id == move.company_id.currency_id:
                currency = False
            else:
                currency = move.currency_id

            return {
                "name": "{}: {}".format(self.order_id.name, self.name),
                "move_id": move.id,
                "currency_id": currency and currency.id or False,
                "purchase_line_id": self.id,
                "date_maturity": move.invoice_date_due,
                "product_uom_id": self.product_uom.id,
                "product_id": self.product_id.id,
                "price_unit": self.price_unit,
                "quantity": qty,
                "partner_id": move.partner_id.id,
                "analytic_account_id": self.account_analytic_id.id,
                "analytic_tag_ids": [(6, 0, self.analytic_tag_ids.ids)],
                "tax_ids": [(6, 0, self.taxes_id.ids)],
                "display_type": self.display_type,
            }
        else:
            return super()._prepare_account_move_line(move)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.onchange('partner_id')
    def _set_partner_supplier_currency_id(self):
        self.currency_id = self.partner_id.property_purchase_currency_id or self.partner_id.currency_id


    def copy_data(self, default=None):
        if default is None:
            default = {}
        if "order_line" not in default:
            default["order_line"] = [
                (0, 0, line.copy_data()[0])
                for line in self.order_line.filtered(lambda l: not l.is_downpayment)
            ]
        return super(PurchaseOrder, self).copy_data(default)

    def action_view_invoice(self, invoices=False):
        res = super(PurchaseOrder, self).action_view_invoice()
        invoices = self.mapped("invoice_ids")
        if self._context.get("purchase_bill"):
            if 'downpayment_line' in res['context']:
                res["context"]["downpayment_line"] = True
            if len(invoices) > 1:
                action = self.env.ref("account.action_move_in_invoice_type").sudo().read()[0]
                action["domain"] = [("id", "in", invoices.ids)]
                return action
            elif len(invoices) == 1:
                res["views"] = [(self.env.ref("account.view_move_form").id, "form")]
                res["res_id"] = invoices.ids[0]
        elif self._context.get("final"):
            if len(invoices) > 1:
                action = self.env.ref("account.action_move_in_invoice_type").sudo().read()[0]
                action["domain"] = [("id", "in", invoices.ids)]
                return action
            elif len(invoices) == 1:
                res["views"] = [(self.env.ref("account.view_move_form").id, "form")]
                res["res_id"] = invoices.ids[0]
            res["context"]["final_payment"] = True
        elif self._context.get("without_downpayment"):
            if not invoices:
                raise UserError(
                    _(
                        "There is no invoiceable line. If a product has a Received quantities control policy, please make sure that a quantity has been received."
                    )
                )
            res["views"] = [(self.env.ref("account.view_move_form").id, "form")]
            res["res_id"] = invoices.ids[0]
        return res
