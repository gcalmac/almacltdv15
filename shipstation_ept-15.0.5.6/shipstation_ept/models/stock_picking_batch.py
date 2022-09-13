"""
Emipro Technologies Private Limited
Author : Ravi Kotadiya | ravik@emiprotechnologies.com
Date : Oct-26-2021
"""
# -*- coding: utf-8 -*-
# Copyright (c) 2019 Emipro Technologies Pvt Ltd (www.emiprotechnologies.com). All rights reserved.
import base64
import logging
import os

from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPickingBatch(models.Model):
    """
    Inheriting stock.picking.batch
    """
    _inherit = "stock.picking.batch"

    carrier_id = fields.Many2one('delivery.carrier',
                                 string="Delivery Method",
                                 copy=False,
                                 help="""According to the selected shipping provider, Visible the delivery method.""")
    batch_processed_via_shipstation_cron = fields.Boolean('Batch Processed via Shipstation CronJob',
                                                          default=False,
                                                          copy=False,
                                                          help="""If Batch Process Completed Using The
                                                     CronJob Than Values Is TRUE.""")
    shipstation_ready_for_download = fields.Boolean('Shipstation ReadyForDownload',
                                                    default=False,
                                                    copy=False,
                                                    help="Mark as True when it's have tracking ref number.")
    shipstation_integration_level = fields.Selection(related="carrier_id.integration_level",
                                                     string="Integration Level(Shipstation)")
    shipstation_instance_id = fields.Many2one("shipstation.instance.ept", string="Shipstation Instance")

    def shipstation_send_to_shipper_ept(self):
        """ Execute these method when clicking on send_to_shipper button.
            @return: Pass all request to provider.
        """
        self.ensure_one()
        pickings = self.picking_ids.filtered(
            lambda x: x.picking_type_code in ('outgoing') and x.state in ('done') and x.carrier_id and x.shipstation_send_to_shipper_process_done == False and not x.carrier_tracking_ref)
        if not pickings:
            raise UserError("No picking left for label generation.")

        for picking in pickings:
            try:
                if picking.carrier_id and picking.carrier_id.delivery_type not in ['fixed', 'base_on_rule'] and picking.carrier_id.integration_level == 'rate':
                    picking.send_to_shipper()

                if picking.carrier_tracking_ref:
                    self.shipstation_ready_for_download = True
                    picking.shipstation_send_to_shipper_process_done = True
            except Exception as exception:
                message = "Delivery Order : %s Description : %s", (picking.name, exception)
                self.unlink_old_message_and_post_new_message(body=message)
                _logger.exception(
                    "Error while processing for shipstation_send_to_shipper_ept - Picking : %s ", picking.name)
                continue

        return True

    def shipstation_download_labels(self):
        """
        To download all labels for the picking from batch.
        @return: Zip file for all labels.
        """
        self.ensure_one()
        file_path = "/tmp/labels/"
        directory = os.path.dirname(file_path)
        try:
            os.stat(directory)
        except:
            os.system("mkdir {}".format(file_path))

        pickings = self.picking_ids.filtered(
            lambda x: x.picking_type_code in ('outgoing') and x.state in (
                'done') and x.carrier_id and x.carrier_tracking_ref)
        for picking in pickings:
            file_name = picking.name.replace('/', '_')
            label_attachments = self.env['ir.attachment'].search(
                [('res_model', '=', 'stock.picking'), ('res_id', '=', picking.id)])
            if not label_attachments:
                continue
            for sequence, label_attachment in enumerate(label_attachments, start=1):
                file_extension = label_attachment.name.split('.')[1] if \
                    label_attachment.name.split('.')[1] else "pdf"
                with open("%s%s_%s.%s" % (file_path, sequence, file_name, file_extension), "wb") as f:
                    f.write(base64.b64decode(label_attachment and label_attachment.datas))
        file_name = "%s.tar.gz" % (self.name and self.name.replace('/', '_') or 'Shipping_Labels')
        if os.stat(directory):
            os.system("tar -czvf /tmp/%s %s" % (file_name, directory))
            os.system("rm -R %s" % directory)
        with open("/tmp/%s" % file_name, "rb") as f1:
            f1.seek(0)
            buffer = f1.read()
            f1.close()
            file_data_temp = base64.b64encode(buffer)
        # Modified the file name by [ES] | Task: 183286 | Dated 27, Jan 2022
        att_id = self.env['ir.attachment'].create({'name': "Wave -%s" % (file_name or ""),
                                                   'store_fname': "Wave - %s" % (
                                                           file_name or ""),
                                                   'datas': file_data_temp or "",
                                                   'res_model': 'stock.picking.batch',
                                                   'res_id': self.id, 'res_name': self.name})
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % att_id.id,
            'target': 'self'
        }

    def shipstation_download_invoices(self):
        """
        To download invoices for all pickings in batch.
        @return: Zip file for all Invoices.
        """
        self.ensure_one()
        allow_partial_invoice = self.env['ir.config_parameter'].sudo().get_param(
            'batch_pickings_validate_ept.download_partial_invoice')
        invoice_ids = []
        invoice_messages = []
        not_allow_invoice = False
        for picking_id in self.picking_ids:
            if picking_id.sale_id and picking_id.sale_id.invoice_ids:
                for invoice_id in picking_id.sale_id.invoice_ids:
                    invoice_ids.append(invoice_id.id)
            else:
                not_allow_invoice = True
                invoice_messages.append("Invoice Is Not Created For This Order %s (%s)." % (
                    picking_id.origin, picking_id.name))
        if not invoice_ids:
            raise UserError(_("%s" % ('\n'.join(invoice_messages))))
        if not allow_partial_invoice and not_allow_invoice:
            raise UserError(_("Invoice Is Not Available In Following Order\n %s" % ('\n'.join(invoice_messages))))
        invoices = self.env['account.move'].search([('id', 'in', invoice_ids)])
        return self.env.ref('account.account_invoices').report_action(invoices)

    def unlink_old_message_and_post_new_message(self, body):
        message_ids = self.env["mail.message"].sudo().search(
            [('model', '=', 'stock.picking.batch'), ('res_id', '=', self.id), ('body', '=', body)])
        message_ids.unlink()
        self.message_post(body=body)

    def create_batch_using_cronjob(self, ctx={}):
        """
        Using the cronjob create the batch and confirm the batch, Done Batch and
        generate the label according to the configuration.
        @return: Return Batch details in log.
        """
        batch_picking_obj = self.env['stock.picking.batch']
        carrier_ids = self.env['delivery.carrier'].search([('shipstation_auto_create_batch', '=', True)])
        instance_id = ctx.get('shipstation_instance_id')
        instance = self.env['shipstation.instance.ept'].browse(instance_id)
        if not instance:
            return True
        for carrier_id in carrier_ids:
            _logger.info("CRON: Auto create batch for carrier '{}'".format(carrier_id.name))
            batch_id = batch_picking_obj.search(
                [('carrier_id', '=', carrier_id.id), ('state', '=', 'draft'),
                 ('shipstation_instance_id', '=', instance.id)], limit=1)
            try:
                batch_list = self.create_batches(
                    instance, carrier_id.id, False, False,
                    batch_id if carrier_id.shipstation_use_existing_batch_cronjob else False)
            except Exception as exception:
                _logger.exception("CRON: There is an error while creating batch for carrier {}, "
                                  "\n Error: {}".format(carrier_id.name, str(exception)))
                continue
            self._cr.commit()
            for batch in batch_list:
                if batch and carrier_id.shipstation_auto_done_pickings:
                    try:
                        batch.action_confirm()
                        if not all(batch.mapped('picking_ids.state')) == "assigned":
                            batch.action_assign()
                        not_assigned_pickings = batch.mapped('picking_ids').filtered(
                            lambda x: x.state not in ['assigned'])
                        if not_assigned_pickings:
                            batch.unlink_old_message_and_post_new_message(
                                body="pickings with no stock assigned %s" % not_assigned_pickings.mapped(
                                    'picking_ids.name'))
                        pickings_to_process = batch.mapped('picking_ids').filtered(lambda x: x.state == "assigned")
                        for picking in pickings_to_process:
                            for move in picking.move_lines:
                                if move.move_line_ids:
                                    for move_line in move.move_line_ids:
                                        move_line.qty_done = move_line.product_uom_qty
                                else:
                                    move.quantity_done = move.product_uom_qty
                        batch.action_done()
                    except Exception as exception:
                        _logger.info("CRON: Process Issue.%s", exception)
                    batch.batch_processed_via_shipstation_cron = True
                self._cr.commit()
        return True

    def create_batches(self, instance, carrier_id, start_date=False, end_date=False, existing_batch=False):
        """
        Create batch. Using this method check the picking and set the batch Id in
        spacific picking.
        :param carrier_id: delivery carrier id
        :param delivery_type: delivery_type
        :param start_date: start date h
        :param end_date: end date of
        :param batch: existing batch
        @return:  Return Batch details.
        """
        batch_picking_obj = self.env['stock.picking.batch']
        carrier_id = self.env['delivery.carrier'].browse(carrier_id)
        batch_limit = carrier_id.shipstation_batch_limit or 100
        batch_list = self.env['stock.picking.batch']

        if start_date > end_date:
            raise UserError("Please select valid start date and End date, End date must be greater than start date")
        query = """select sp.id from stock_picking sp
                    join stock_picking_type spt on spt.id=sp.picking_type_id 
                    where batch_id Is Null
                    and carrier_id={} and spt.code='outgoing'
                    and state not in('done','cancel')
                    and shipstation_instance_id={}""".format(carrier_id.id, instance.id)
        if start_date and end_date:
            query += """and scheduled_date BETWEEN '{}' and '{}'""".format(start_date, end_date)
        self._cr.execute(query)
        pickings = self._cr.fetchall()
        picking_ids = []
        for picking in pickings:
            picking_ids.append(str(picking[0]))
        if not picking_ids:
            raise UserError("Picking is not available according to the filter!")
        company_id = self.env['stock.picking'].search([('id', 'in', picking_ids)], limit=1).mapped(
            'company_id').id or '1'
        counter = 0
        while picking_ids[counter * batch_limit:counter * batch_limit + batch_limit]:
            remaining_pickings = picking_ids[counter * batch_limit:counter * batch_limit + batch_limit]
            if existing_batch and len(existing_batch.mapped('picking_ids')) < batch_limit:
                self._cr.execute('update stock_picking set batch_id=%s WHERE id in (%s)' % (
                    existing_batch.id, ",".join(remaining_pickings)))
                batch_list += existing_batch
                counter = counter + 1
                continue
            batch = batch_picking_obj.create(
                {'carrier_id': carrier_id.id,
                 'company_id': company_id,
                 'shipstation_instance_id': instance.id})
            self._cr.execute('update stock_picking set batch_id=%s WHERE id in (%s)' % (
                batch.id, ",".join(remaining_pickings)))
            counter = counter + 1

            batch.write({
                'user_id': carrier_id.shipstation_user_id.id if carrier_id and carrier_id.shipstation_user_id else self.env.user.id
            })
            _logger.info("CRON: Batch Created : %s", batch.name)
            batch_list += batch
        return batch_list
