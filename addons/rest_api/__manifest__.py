{
    'name': 'REST API',
    'summary': 'Versioned REST API (/api/v1/) with a machine-generated OpenAPI 3.1 spec',
    'description': """\
REST API (OpenAPI 3.1)
======================

This module adds an opt-in, versioned REST API under ``/api/v1/`` layered over
Odoo's ORM, documented by a machine-generated OpenAPI 3.1 specification served
at ``/api/v1/openapi.json`` (reachable without authentication).

It exposes full CRUD endpoints for five pilot models -- ``res.partner``,
``sale.order``, ``account.move``, ``stock.picking`` and ``crm.lead`` -- with
request and response validation performed by pydantic schemas in strict mode
(extra fields rejected). Requests authenticate exclusively through API keys or
OAuth 2.0 bearer tokens and are authorized identically to JSON-RPC, passing
through ``ir.model.access``, ``ir.rule`` and field-group filtering. The existing
JSON-RPC and XML-RPC surfaces are left completely untouched.
""",
    'depends': ['base', 'web', 'auth_oauth'],
    'category': 'Extra Tools',
    'version': '19.0.1.0.0',
    'auto_install': False,
    'application': False,
    'external_dependencies': {'python': ['pydantic']},
    'author': 'Odoo S.A.',
    'license': 'LGPL-3',
}
