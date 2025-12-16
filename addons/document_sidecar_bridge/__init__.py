# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Document Sidecar Bridge - Odoo Addon

This addon bridges Odoo's report system with an external TypeScript PDF
sidecar service. It intercepts supported report types (invoice, quote,
delivery slip) and routes them to the sidecar for rendering, with
automatic fallback to native QWeb rendering when the sidecar is unavailable.
"""

from . import models, services
