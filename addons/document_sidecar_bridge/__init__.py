# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Document Sidecar Bridge - Odoo Addon Package Initializer

This addon bridges Odoo's report system with an external TypeScript PDF
sidecar service. It intercepts supported report types (invoice, quote,
delivery slip) and routes them to the sidecar for rendering, with
automatic fallback to native QWeb rendering when the sidecar is unavailable.

Architecture:
    - models/ir_actions_report.py: Extends ir.actions.report to intercept
      _render_qweb_pdf calls and route to the sidecar service
    - services/sidecar_client.py: HTTP client for communicating with the
      TypeScript PDF sidecar service

Configuration:
    The addon is controlled via ir.config_parameter settings:
    - document_sidecar.enabled: Feature toggle (True/False)
    - document_sidecar.url: Sidecar service base URL
    - document_sidecar.api_key: API authentication key
    - document_sidecar.secret_key: HMAC signing secret
    - document_sidecar.timeout: Request timeout in seconds

Usage:
    Once installed and configured, the addon automatically intercepts
    supported report types. No code changes required in other modules.
    If the sidecar is unavailable, reports fall back to native QWeb
    rendering transparently.

Supported Report Types:
    - account.report_invoice -> invoice
    - sale.report_saleorder -> quote
    - stock.report_deliveryslip -> delivery_slip
"""

# Import models subpackage to register ORM model extensions with Odoo's registry.
# This enables the ir.actions.report extension to be discovered and applied
# when the addon is installed or updated.
from . import models

# Import services subpackage to load the SidecarClient HTTP client class
# for communication with the external TypeScript PDF sidecar service.
from . import services
