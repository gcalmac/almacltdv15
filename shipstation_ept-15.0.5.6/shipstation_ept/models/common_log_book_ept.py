import logging
from odoo import models, fields
_logger = logging.getLogger(__name__)


class CommonLogBookEpt(models.Model):
    """
    Inherit common.log.book.ept for create shipstation log
    """
    _inherit = "common.log.book.ept"

    module = fields.Selection(selection_add=[("shipstation_ept", "Shipstation")],
                              ondelete={'shipstation_ept': 'cascade'})

    def create_shipstation_log(self, operation_type, model_id):
        """
        Method for create shipstation log
        """
        log_vals = {'active': True, 'model_id': model_id, 'type': operation_type, 'module': 'shipstation_ept'}
        log_rec = self.create(log_vals)
        return log_rec

    def create_log_book_line_for_shipstation(self, message, model_id, record=False):
        """
        method for create shipstation logbook line
        """
        vals = {'log_book_id': self.id,
                'message': message,
                'model_id': model_id,
                }
        if record:
            vals.update({'order_ref': record.name, 'res_id': record.id})
        res_model = self.env["ir.model"].sudo().browse(model_id)
        if record:
            msg = "Model: {}, Record: {}, Message: {}".format(res_model.name, record.id, message)
        else:
            msg = "Model: {}, Message: {}".format(res_model.name, message)
        _logger.info(msg)
        self.env['common.log.lines.ept'].create(vals)

    def unlink_log_book_without_log_lines(self):
        """
        Remove logbook record which have no log lines
        """
        if not self.log_lines:
            self.unlink()
