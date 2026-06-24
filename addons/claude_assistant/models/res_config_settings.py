# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    claude_assistant_api_key = fields.Char(
        string='Claude API Key',
        config_parameter='claude_assistant.api_key',
    )
