# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Claude Assistant',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Role-aware Anthropic Claude AI chat assistant embedded in the Odoo backend',
    'description': """
Claude Assistant
================
Embeds an Anthropic Claude conversational assistant into the Odoo web client,
surfaced through a single systray entry visible to internal users. Four
stakeholder roles (System Administrators, Business Users, Developers,
Partners & Integrators) each unlock a fixed set of modes backed by live Odoo
ORM context injected into the Claude system prompt. The Anthropic API key is
stored in ir.config_parameter and edited from General Settings. Conversation
state is ephemeral (client-side only).
    """,
    'depends': ['base', 'web'],
    'data': [
        'security/claude_assistant_security.xml',
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'claude_assistant/static/src/**/*.js',
            'claude_assistant/static/src/**/*.xml',
            'claude_assistant/static/src/**/*.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'author': 'Odoo S.A.',
}
