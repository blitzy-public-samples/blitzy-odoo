# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Tests package initializer for the document_sidecar_bridge Odoo addon.

This package contains unit tests for validating the sidecar bridge functionality:
- SidecarClient HTTP communication and data serialization
- ir.actions.report extension for report routing
- Fallback mechanisms for sidecar unavailability
"""

from . import test_sidecar_bridge
