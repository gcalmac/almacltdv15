# Copyright 2019 Sodexis
# License OPL-1 (See LICENSE file for full copyright and licensing details)


from odoo import _, api, fields, models
from odoo.tools.float_utils import float_compare
from odoo.addons.account.models.account_move import AccountMove as OriginalAccountMove


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.onchange("purchase_vendor_bill_id", "purchase_id")
    def _onchange_purchase_auto_complete(self):
        if not self.purchase_id and not self.purchase_vendor_bill_id:
            return
        company_id = self.purchase_id.company_id.id
        if self._context.get("final"):
            if self.purchase_vendor_bill_id.vendor_bill_id:
                self.invoice_vendor_bill_id = (
                    self.purchase_vendor_bill_id.vendor_bill_id
                )
                self._onchange_invoice_vendor_bill()
            elif self.purchase_vendor_bill_id.purchase_order_id:
                self.purchase_id = self.purchase_vendor_bill_id.purchase_order_id
            self.purchase_vendor_bill_id = False

            if not self.purchase_id:
                return

            # Copy partner.
            self.partner_id = self.purchase_id.partner_id
            self.fiscal_position_id = self.purchase_id.fiscal_position_id
            self.invoice_payment_term_id = self.purchase_id.payment_term_id
            self.currency_id = self.purchase_id.currency_id

            new_lines = self.env["account.move.line"]
            precision = self.env["decimal.precision"].precision_get(
                "Product Unit of Measure"
            )
            for line in self.purchase_id.order_line - self.invoice_line_ids.mapped(
                "purchase_line_id"
            ):
                if (
                    float_compare(
                        line.qty_invoiced,
                        line.product_qty
                        if line.product_id.purchase_method == "purchase"
                        else line.qty_received,
                        precision_digits=precision,
                    )
                    == -1
                    or line.is_downpayment
                    and line.qty_invoiced == 1
                ):
                    data = line._prepare_account_move_line(self)
                    new_line = new_lines.new(data)
                    new_line.account_id = new_line._get_computed_account()
                    new_line._onchange_price_subtotal()
                    new_lines += new_line
            new_lines._onchange_mark_recompute_taxes()
            # Compute invoice_origin.
            origins = set(new_lines.mapped("purchase_line_id.order_id.name"))
            self.invoice_origin = ",".join(list(origins))
            if any(line.purchase_line_id.is_downpayment for line in new_lines):
                downpayment_amount = 0.0
                other_line_amount = 0.0
                for line in new_lines:
                    if line.purchase_line_id.is_downpayment:
                        downpayment_amount += line.price_subtotal
                        line.quantity = -1
                    else:
                        other_line_amount += line.price_subtotal
                if downpayment_amount > other_line_amount:
                    for line in new_lines:
                        if line.purchase_line_id.is_downpayment:
                            line.quantity = 1
                        else:
                            line.update({"quantity": -(line.quantity)})
                    self.env.context = dict(self.env.context)
                    self.env.context.update({"is_refund": True})
                    self.move_type = "in_refund"
            self.invoice_line_ids += new_lines
            # Compute ref.
            refs = set(self.line_ids.mapped("purchase_line_id.order_id.partner_ref"))
            refs = [ref for ref in refs if ref]
            self.ref = ",".join(refs)
            self.purchase_id = False
#             self._onchange_currency()
            # Compute payment_reference. invoice_payment_ref
            if len(refs) == 1:
                self.payment_reference = refs[0]
            return {}
        elif self._context.get("without_downpayment"):
            if self.purchase_vendor_bill_id.vendor_bill_id:
                self.invoice_vendor_bill_id = (
                    self.purchase_vendor_bill_id.vendor_bill_id
                )
                self._onchange_invoice_vendor_bill()
            elif self.purchase_vendor_bill_id.purchase_order_id:
                self.purchase_id = self.purchase_vendor_bill_id.purchase_order_id
            self.purchase_vendor_bill_id = False

            if not self.purchase_id:
                return

            # Copy partner.
            self.partner_id = self.purchase_id.partner_id
            self.fiscal_position_id = self.purchase_id.fiscal_position_id
            self.invoice_payment_term_id = self.purchase_id.payment_term_id
            self.currency_id = self.purchase_id.currency_id

            new_lines = self.env["account.move.line"]
            precision = self.env["decimal.precision"].precision_get(
                "Product Unit of Measure"
            )
            for line in (
                self.purchase_id.order_line
                - self.purchase_id.order_line.filtered(lambda x: x.is_downpayment)
            ):
                if (
                    float_compare(
                        line.qty_invoiced,
                        line.product_qty
                        if line.product_id.purchase_method == "purchase"
                        else line.qty_received,
                        precision_digits=precision,
                    )
                    == -1
                    or line.is_downpayment
                    and line.qty_invoiced == 1
                ):
                    data = line._prepare_account_move_line(self)
                    new_line = new_lines.new(data)
                    new_line.account_id = new_line._get_computed_account()
                    new_line._onchange_price_subtotal()
                    new_lines += new_line
            new_lines._onchange_mark_recompute_taxes()
            origins = set(new_lines.mapped("purchase_line_id.order_id.name"))
            self.invoice_origin = ",".join(list(origins))
            self.invoice_line_ids += new_lines
            # Compute ref.
            refs = set(self.line_ids.mapped("purchase_line_id.order_id.partner_ref"))
            refs = [ref for ref in refs if ref]
            self.ref = ",".join(refs)

            self.purchase_id = False
#             self._onchange_currency()

            # Compute payment_reference.
            if len(refs) == 1:
                self.payment_reference = refs[0]
            return {}
        else:
            rec = super()._onchange_purchase_auto_complete()
            if not self.journal_id:
                self.update({'journal_id': self.env["account.journal"].search(
                [("type", "in", ["purchase"]), ("company_id", "=", company_id)], limit=1
                )})
            if not self.invoice_origin:
                self.invoice_origin = self.purchase_id.name
            return rec

    def unlink(self):
        downpayment_lines = self.mapped("invoice_line_ids.purchase_line_id").filtered(
            lambda line: line.is_downpayment
        )
        res = super(AccountMove, self).unlink()
        if downpayment_lines:
            downpayment_lines.unlink()
        return res

# Monkey Patched Method to return Super instead of {} as it is breaking the overridden loop
def _onchange_purchase_auto_complete(self):
    if not self.purchase_id and not self.purchase_vendor_bill_id:
        return
    company_id = self.purchase_id.company_id.id
    if self._context.get("final"):
        if self.purchase_vendor_bill_id.vendor_bill_id:
            self.invoice_vendor_bill_id = (
                self.purchase_vendor_bill_id.vendor_bill_id
            )
            self._onchange_invoice_vendor_bill()
        elif self.purchase_vendor_bill_id.purchase_order_id:
            self.purchase_id = self.purchase_vendor_bill_id.purchase_order_id
        self.purchase_vendor_bill_id = False

        if not self.purchase_id:
            return

        # Copy partner.
        self.partner_id = self.purchase_id.partner_id
        self.fiscal_position_id = self.purchase_id.fiscal_position_id
        self.invoice_payment_term_id = self.purchase_id.payment_term_id
        self.currency_id = self.purchase_id.currency_id

        new_lines = self.env["account.move.line"]
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for line in self.purchase_id.order_line - self.invoice_line_ids.mapped(
            "purchase_line_id"
        ):
            if (
                float_compare(
                    line.qty_invoiced,
                    line.product_qty
                    if line.product_id.purchase_method == "purchase"
                    else line.qty_received,
                    precision_digits=precision,
                )
                == -1
                or line.is_downpayment
                and line.qty_invoiced == 1
            ):
                data = line._prepare_account_move_line(self)
                new_line = new_lines.new(data)
                new_line.account_id = new_line._get_computed_account()
                new_line._onchange_price_subtotal()
                new_lines += new_line
        new_lines._onchange_mark_recompute_taxes()
        # Compute invoice_origin.
        origins = set(new_lines.mapped("purchase_line_id.order_id.name"))
        self.invoice_origin = ",".join(list(origins))
        if any(line.purchase_line_id.is_downpayment for line in new_lines):
            downpayment_amount = 0.0
            other_line_amount = 0.0
            for line in new_lines:
                if line.purchase_line_id.is_downpayment:
                    downpayment_amount += line.price_subtotal
                    line.quantity = -1
                else:
                    other_line_amount += line.price_subtotal
            if downpayment_amount > other_line_amount:
                for line in new_lines:
                    if line.purchase_line_id.is_downpayment:
                        line.quantity = 1
                    else:
                        line.update({"quantity": -(line.quantity)})
                self.env.context = dict(self.env.context)
                self.env.context.update({"is_refund": True})
                self.move_type = "in_refund"
        self.invoice_line_ids += new_lines
        # Compute ref.
        refs = set(self.line_ids.mapped("purchase_line_id.order_id.partner_ref"))
        refs = [ref for ref in refs if ref]
        self.ref = ",".join(refs)
        self.purchase_id = False
#             self._onchange_currency()
        # Compute payment_reference. invoice_payment_ref
        if len(refs) == 1:
            self.payment_reference = refs[0]
        rec = super(OriginalAccountMove, self)._onchange_purchase_auto_complete()
    elif self._context.get("without_downpayment"):
        if self.purchase_vendor_bill_id.vendor_bill_id:
            self.invoice_vendor_bill_id = (
                self.purchase_vendor_bill_id.vendor_bill_id
            )
            self._onchange_invoice_vendor_bill()
        elif self.purchase_vendor_bill_id.purchase_order_id:
            self.purchase_id = self.purchase_vendor_bill_id.purchase_order_id
        self.purchase_vendor_bill_id = False

        if not self.purchase_id:
            return

        # Copy partner.
        self.partner_id = self.purchase_id.partner_id
        self.fiscal_position_id = self.purchase_id.fiscal_position_id
        self.invoice_payment_term_id = self.purchase_id.payment_term_id
        self.currency_id = self.purchase_id.currency_id

        new_lines = self.env["account.move.line"]
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for line in (
            self.purchase_id.order_line
            - self.purchase_id.order_line.filtered(lambda x: x.is_downpayment)
        ):
            if (
                float_compare(
                    line.qty_invoiced,
                    line.product_qty
                    if line.product_id.purchase_method == "purchase"
                    else line.qty_received,
                    precision_digits=precision,
                )
                == -1
                or line.is_downpayment
                and line.qty_invoiced == 1
            ):
                data = line._prepare_account_move_line(self)
                new_line = new_lines.new(data)
                new_line.account_id = new_line._get_computed_account()
                new_line._onchange_price_subtotal()
                new_lines += new_line
        new_lines._onchange_mark_recompute_taxes()
        origins = set(new_lines.mapped("purchase_line_id.order_id.name"))
        self.invoice_origin = ",".join(list(origins))
        self.invoice_line_ids += new_lines
        # Compute ref.
        refs = set(self.line_ids.mapped("purchase_line_id.order_id.partner_ref"))
        refs = [ref for ref in refs if ref]
        self.ref = ",".join(refs)

        self.purchase_id = False
#             self._onchange_currency()

        # Compute payment_reference.
        if len(refs) == 1:
            self.payment_reference = refs[0]
        rec = super(OriginalAccountMove, self)._onchange_purchase_auto_complete()
    else:
        rec = super(OriginalAccountMove, self)._onchange_purchase_auto_complete()
        if not self.journal_id:
            self.update({'journal_id': self.env["account.journal"].search(
            [("type", "in", ["purchase"]), ("company_id", "=", company_id)], limit=1
            )})
        if not self.invoice_origin:
            self.invoice_origin = self.purchase_id.name
        return rec

OriginalAccountMove._onchange_purchase_auto_complete = _onchange_purchase_auto_complete

