# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Document Sidecar Bridge',
    'version': '17.0.1.0.0',
    'category': 'Technical',
    'summary': 'Bridge between Odoo reports and external PDF sidecar service',
    'description': """
Document Sidecar Bridge
=======================

This module provides integration between Odoo's reporting system and an external
TypeScript-based PDF sidecar service. It enables offloading PDF document generation
to a standalone microservice while maintaining full backward compatibility with
Odoo's native QWeb report rendering.

Key Features:
-------------
* Intercepts supported report types (invoices, quotes, delivery slips) and routes
  them to the external sidecar service for PDF generation
* Automatic fallback to native QWeb rendering when the sidecar is unavailable
* HMAC-SHA256 request signing for secure communication
* Configurable via system parameters (ir.config_parameter)
* Zero modifications to Odoo core - uses standard addon extension patterns

Supported Report Types:
-----------------------
* account.report_invoice - Customer Invoices
* sale.report_saleorder - Sale Order / Quotation
* stock.report_deliveryslip - Delivery Slip / Picking Operations

Configuration:
--------------
Configure the following system parameters to enable the sidecar integration:
* document_sidecar.enabled - Enable/disable sidecar routing (True/False)
* document_sidecar.url - Base URL of the sidecar service
* document_sidecar.api_key - API key for authentication
* document_sidecar.secret_key - HMAC signing secret
* document_sidecar.timeout - Request timeout in seconds

Note: When the sidecar is disabled or unavailable, all reports will be rendered
using Odoo's native QWeb PDF generation, ensuring zero disruption to users.
    """,
    'author': 'Odoo S.A.',
    'website': 'https://www.odoo.com',
    'depends': [
        'base',
        'account',
        'sale',
        'stock',
    ],
    'data': [
        'data/ir_config_parameter.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
