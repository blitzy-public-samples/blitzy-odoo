# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Models package initializer for the document_sidecar_bridge Odoo addon.

This package contains the ir.actions.report extension that intercepts
supported PDF report types (invoice, quote, delivery_slip) and routes
them to the external TypeScript sidecar service for rendering.

Importing this package registers the IrActionsReport class with Odoo's ORM,
enabling PDF report interception when the addon is installed or updated.

Exports from ir_actions_report module:
    - IrActionsReport: The ir.actions.report model extension class
    - SIDECAR_REPORT_TYPES: Mapping of Odoo report names to sidecar types
    - SidecarUnavailable: Exception raised when sidecar service is unavailable
"""

from . import ir_actions_report
