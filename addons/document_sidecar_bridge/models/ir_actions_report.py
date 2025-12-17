# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Sidecar Bridge - ir.actions.report Extension

This module extends Odoo's ir.actions.report model to intercept supported PDF
report types and route them to an external TypeScript sidecar service for
rendering. It implements:

- SIDECAR_REPORT_TYPES mapping for routing invoice, quote, and delivery slip
  reports to the appropriate sidecar template types
- Override of _render_qweb_pdf to intercept and route supported reports
- Comprehensive fallback mechanism ensuring zero-disruption compatibility
- Single-record rendering constraint (batch rendering is out of scope)
- Feature toggle via document_sidecar.enabled configuration parameter

The fallback mechanism ensures that:
- Any sidecar unavailability triggers automatic QWeb fallback
- Any sidecar errors trigger automatic QWeb fallback
- Users never see sidecar-related errors - they get their PDF via QWeb instead

Example usage:
    When a user clicks "Print Invoice", the flow is:
    1. Odoo calls _render_qweb_pdf()
    2. This extension checks if sidecar is enabled and report type is supported
    3. If yes, routes to sidecar via SidecarClient.render_report()
    4. If sidecar fails or is disabled, falls back to native QWeb rendering
"""

import logging
import traceback

from odoo import api, models

from ..services.sidecar_client import SidecarClient, SidecarUnavailable

_logger = logging.getLogger(__name__)


# Mapping of Odoo report names to sidecar report types.
# Only reports listed here will be routed to the sidecar service.
# All other reports use standard QWeb rendering unchanged.
SIDECAR_REPORT_TYPES = {
    'account.report_invoice': 'invoice',
    'sale.report_saleorder': 'quote',
    'stock.report_deliveryslip': 'delivery_slip',
}


class IrActionsReport(models.Model):
    """
    Extension of ir.actions.report for sidecar PDF rendering integration.

    This class extends the base ir.actions.report model to intercept supported
    PDF report types and route them to an external TypeScript sidecar service.
    It maintains 100% backward compatibility by implementing comprehensive
    fallback to native QWeb rendering when the sidecar is unavailable or
    encounters errors.

    Key features:
    - Intercepts invoice, quote, and delivery slip reports
    - Routes supported reports to sidecar via HTTP API
    - Automatic fallback to QWeb on any sidecar failure
    - Single-record rendering (logs warning for batch requests)
    - Feature toggle via ir.config_parameter

    Note:
        This extension uses the standard Odoo _inherit pattern to extend
        the base report model without modifying Odoo core code.
    """

    _inherit = 'ir.actions.report'

    def _is_sidecar_enabled(self):
        """
        Check if the sidecar service is enabled in configuration.

        Reads the document_sidecar.enabled parameter from ir.config_parameter.
        Returns False if the parameter is not set or set to a falsy value.

        Returns:
            bool: True if sidecar is enabled, False otherwise.
        """
        IrConfigParameter = self.env['ir.config_parameter'].sudo()
        enabled_param = IrConfigParameter.get_param(
            'document_sidecar.enabled',
            default='False',
        )
        # Handle various truthy string representations
        return enabled_param.lower() in ('true', '1', 'yes')

    def _get_sidecar_report_type(self, report):
        """
        Get the sidecar report type for a given Odoo report.

        Looks up the report's report_name in the SIDECAR_REPORT_TYPES mapping
        to determine if it should be routed to the sidecar and what type
        identifier to use.

        Args:
            report: The ir.actions.report record to check.

        Returns:
            str or None: The sidecar report type ('invoice', 'quote',
                        'delivery_slip') or None if not supported.
        """
        return SIDECAR_REPORT_TYPES.get(report.report_name)

    def _get_record_for_sidecar(self, report, res_ids):
        """
        Get the record to render via sidecar.

        Handles the single-record constraint by:
        1. Converting int to list if needed
        2. Logging a warning if multiple records are passed
        3. Using only the first record ID

        Args:
            report: The ir.actions.report record being rendered.
            res_ids: Single record ID (int) or list of record IDs.

        Returns:
            recordset: The single record to render, or empty recordset if
                      res_ids is empty/None.
        """
        # Normalize res_ids to list
        if res_ids is None:
            return self.env[report.model].browse()
        if isinstance(res_ids, int):
            res_ids = [res_ids]

        # Handle single-record constraint (batch rendering is out of scope)
        if len(res_ids) > 1:
            _logger.warning(
                "Sidecar bridge received batch render request with %d records "
                "for report '%s'. Batch rendering is out of scope - only the "
                "first record (id=%s) will be rendered via sidecar. "
                "Remaining %d records will NOT be included.",
                len(res_ids),
                report.report_name,
                res_ids[0],
                len(res_ids) - 1,
            )

        # Get only the first record
        if res_ids:
            return self.env[report.model].browse(res_ids[0])
        return self.env[report.model].browse()

    def _render_via_sidecar(self, report, res_ids, data=None):
        """
        Render a report via the external sidecar service.

        This method handles the actual communication with the sidecar service:
        1. Determines the sidecar report type
        2. Gets the record to render (enforcing single-record constraint)
        3. Creates a SidecarClient and calls render_report()
        4. Returns the PDF content in the same format as _render_qweb_pdf

        Args:
            report: The ir.actions.report record being rendered.
            res_ids: Record ID(s) to render (only first is used).
            data: Optional additional data dictionary (passed through from
                  original call but not currently used by sidecar).

        Returns:
            tuple: (pdf_content: bytes, 'pdf')

        Raises:
            SidecarUnavailable: When the sidecar cannot generate the PDF.
                This exception should be caught by the caller to trigger
                fallback to QWeb rendering.
        """
        # Get the sidecar report type
        sidecar_report_type = self._get_sidecar_report_type(report)
        if not sidecar_report_type:
            # This shouldn't happen if called correctly, but be defensive
            raise SidecarUnavailable(
                f"Report '{report.report_name}' is not supported by sidecar",
            )

        # Get the single record to render
        record = self._get_record_for_sidecar(report, res_ids)
        if not record:
            msg = "No record provided for sidecar rendering"
            raise SidecarUnavailable(msg)

        # Create client and render
        client = SidecarClient(self.env)
        pdf_content, content_type = client.render_report(
            sidecar_report_type,
            record,
            report,
        )

        _logger.info(
            "Successfully rendered report '%s' (id=%s) via sidecar, "
            "PDF size: %d bytes",
            report.report_name,
            record.id,
            len(pdf_content),
        )

        return (pdf_content, content_type)

    @api.model
    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """
        Override to intercept supported reports and route to sidecar.

        This method intercepts the PDF rendering process for supported report
        types and routes them to the external TypeScript sidecar service.
        It implements comprehensive fallback to native QWeb rendering when:
        - Sidecar is disabled via configuration
        - Report type is not supported by sidecar
        - Sidecar service is unavailable
        - Sidecar returns an error
        - Any unexpected exception occurs

        The fallback mechanism ensures zero-disruption compatibility - users
        always get their PDF, either from sidecar or from native QWeb.

        Args:
            report_ref: Report reference (name or ID) identifying the report.
            res_ids: Record ID(s) to render. For sidecar routing, only the
                    first record is used (single-record rendering).
            data: Optional additional data dictionary for rendering context.

        Returns:
            tuple: (pdf_content: bytes, 'pdf') - Binary PDF content and type.
        """
        # Get the report record for analysis
        report = self._get_report(report_ref)

        # Check if we should route to sidecar:
        # 1. Sidecar must be enabled
        # 2. Report type must be in SIDECAR_REPORT_TYPES mapping
        should_use_sidecar = (
            self._is_sidecar_enabled()
            and self._get_sidecar_report_type(report) is not None
        )

        if not should_use_sidecar:
            # Not a sidecar candidate - use standard QWeb rendering
            return super()._render_qweb_pdf(report_ref, res_ids, data)

        # Attempt sidecar rendering with fallback to QWeb
        try:
            _logger.info(
                "Attempting sidecar rendering for report '%s' with res_ids=%s",
                report.report_name,
                res_ids,
            )
            return self._render_via_sidecar(report, res_ids, data)

        except SidecarUnavailable as e:
            # Sidecar is unavailable or returned an error
            # This is expected behavior - fall back to QWeb gracefully
            _logger.warning(
                "Sidecar unavailable for report '%s' (res_ids=%s): %s. "
                "Falling back to native QWeb rendering.",
                report.report_name,
                res_ids,
                e,
            )
            return super()._render_qweb_pdf(report_ref, res_ids, data)

        except Exception as e:  # noqa: BLE001 - Intentional catch-all for fallback
            # Catch any other unexpected exceptions
            # Log with full traceback for debugging, but still fall back gracefully
            _logger.error(
                "Unexpected error during sidecar rendering for report '%s' "
                "(res_ids=%s): %s. Falling back to native QWeb rendering.\n"
                "Traceback:\n%s",
                report.report_name,
                res_ids,
                e,
                traceback.format_exc(),
            )
            return super()._render_qweb_pdf(report_ref, res_ids, data)
