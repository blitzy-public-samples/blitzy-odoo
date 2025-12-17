# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Sidecar Client Service Module

This module provides the HTTP client service for communicating with the external
TypeScript PDF sidecar service. It handles:
- HMAC-SHA256 signature generation for request authentication
- Data serialization for invoices, sale orders, and stock pickings
- HTTP communication with the sidecar API
- Error handling and automatic fallback triggering

The SidecarClient class is the main entry point for all sidecar communication,
and the SidecarUnavailable exception is used to signal when fallback to native
QWeb rendering should occur.
"""

import base64
import hashlib
import hmac
import json
import logging
import uuid

import requests

_logger = logging.getLogger(__name__)


class SidecarUnavailable(Exception):
    """
    Exception raised when the sidecar service is unavailable.

    This exception is caught by the ir.actions.report extension to trigger
    automatic fallback to native QWeb PDF rendering. It can be raised due to:
    - Connection errors (sidecar service not running)
    - Timeout errors (sidecar taking too long to respond)
    - HTTP errors from the sidecar service
    - Any unexpected errors during sidecar communication

    Example usage:
        try:
            result = sidecar_client.render_report('invoice', invoice, report)
        except SidecarUnavailable as e:
            _logger.warning("Sidecar unavailable: %s, falling back to QWeb", e)
            return super()._render_qweb_pdf(report_ref, res_ids, data)
    """
    pass


class SidecarClient:
    """
    HTTP client service for communicating with the TypeScript PDF sidecar.

    This class handles all communication between Odoo and the external sidecar
    service, including:
    - Reading configuration from ir.config_parameter
    - Generating HMAC-SHA256 signatures for request authentication
    - Serializing Odoo records to JSON payloads
    - Sending HTTP requests and handling responses
    - Converting responses back to binary PDF data

    The client is designed to be stateless - each method call is independent
    and configuration is read fresh from ir.config_parameter.

    Attributes:
        env: The Odoo environment object used to access ir.config_parameter
             and read configuration values.

    Example usage:
        client = SidecarClient(self.env)
        try:
            pdf_content, report_type = client.render_report('invoice', invoice, report)
        except SidecarUnavailable:
            # Handle fallback to QWeb
            pass
    """

    # Default configuration values
    DEFAULT_URL = 'http://localhost:3000'
    DEFAULT_TIMEOUT = 30

    def __init__(self, env):
        """
        Initialize the SidecarClient with an Odoo environment.

        Args:
            env: The Odoo environment object (self.env from a model).
                 Used to access ir.config_parameter for configuration.
        """
        self.env = env

    def _get_config(self):
        """
        Read sidecar configuration from ir.config_parameter.

        Retrieves all necessary configuration values for communicating with
        the sidecar service. Uses default values where appropriate.

        Returns:
            dict: Configuration dictionary containing:
                - url (str): Base URL of the sidecar service
                - api_key (str): API key for authentication
                - secret_key (str): Secret key for HMAC signature generation
                - timeout (int): Request timeout in seconds
                - enabled (bool): Whether the sidecar is enabled

        Note:
            The enabled flag should be checked before attempting to use the
            sidecar. If False, the caller should fall back to QWeb rendering.
        """
        IrConfigParameter = self.env['ir.config_parameter'].sudo()

        return {
            'url': IrConfigParameter.get_param(
                'document_sidecar.url',
                default=self.DEFAULT_URL,
            ),
            'api_key': IrConfigParameter.get_param(
                'document_sidecar.api_key',
                default='',
            ),
            'secret_key': IrConfigParameter.get_param(
                'document_sidecar.secret_key',
                default='',
            ),
            'timeout': int(IrConfigParameter.get_param(
                'document_sidecar.timeout',
                default=str(self.DEFAULT_TIMEOUT),
            )),
            'enabled': IrConfigParameter.get_param(
                'document_sidecar.enabled',
                default='False',
            ).lower() in ('true', '1', 'yes'),
        }

    def _sign_request(self, payload):
        """
        Generate HMAC-SHA256 signature for a request payload.

        Creates a cryptographic signature of the JSON payload using the
        configured secret key. This signature is used by the sidecar to
        verify request integrity and authenticity.

        Args:
            payload (dict): The request payload dictionary to sign.

        Returns:
            str: Hexadecimal representation of the HMAC-SHA256 signature.

        Note:
            The payload is converted to a JSON string with sorted keys and
            no extra whitespace to ensure consistent signature generation.
        """
        config = self._get_config()
        secret_key = config['secret_key']

        # Convert payload to JSON string with consistent formatting
        payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))

        # Generate HMAC-SHA256 signature
        return hmac.new(
            secret_key.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

    def _format_date(self, date_value):
        """
        Format a date value to ISO string format.

        Args:
            date_value: A date, datetime, or None value.

        Returns:
            str or None: ISO format date string (YYYY-MM-DD) or None.
        """
        if date_value:
            return str(date_value)[:10]  # Extract YYYY-MM-DD portion
        return None

    def _format_datetime(self, datetime_value):
        """
        Format a datetime value to ISO string format.

        Args:
            datetime_value: A datetime or None value.

        Returns:
            str or None: ISO format datetime string or None.
        """
        if datetime_value:
            return datetime_value.isoformat() if hasattr(datetime_value, 'isoformat') else str(datetime_value)
        return None

    def _format_monetary(self, value, currency=None):
        """
        Format a monetary value to float with appropriate precision.

        Args:
            value: Numeric value to format.
            currency: Optional currency record for precision.

        Returns:
            float: Formatted monetary value.
        """
        if value is None:
            return 0.0
        return round(float(value), 2)

    def _get_partner_address(self, partner):
        """
        Build an address dictionary from a res.partner record.

        Args:
            partner: res.partner record.

        Returns:
            dict: Address dictionary with street, city, state, zip, country.
        """
        if not partner:
            return {
                'street': '',
                'street2': '',
                'city': '',
                'state': '',
                'zip': '',
                'country': '',
            }

        return {
            'street': partner.street or '',
            'street2': partner.street2 or '',
            'city': partner.city or '',
            'state': partner.state_id.name if partner.state_id else '',
            'zip': partner.zip or '',
            'country': partner.country_id.name if partner.country_id else '',
        }

    def _get_company_info(self, company):
        """
        Build company information dictionary from a res.company record.

        Args:
            company: res.company record.

        Returns:
            dict: Company information dictionary.
        """
        if not company:
            return {
                'name': '',
                'address': self._get_partner_address(None),
                'vat': '',
                'phone': '',
                'email': '',
                'website': '',
                'logo': None,
            }

        # Get company logo as base64 if available
        logo_base64 = None
        if company.logo:
            logo_base64 = company.logo.decode('utf-8') if isinstance(company.logo, bytes) else company.logo

        return {
            'name': company.name or '',
            'address': self._get_partner_address(company.partner_id),
            'vat': company.vat or '',
            'phone': company.phone or '',
            'email': company.email or '',
            'website': company.website or '',
            'logo': logo_base64,
        }

    def _serialize_invoice_data(self, invoice):
        """
        Serialize an account.move (invoice) record to JSON-compatible dict.

        Converts an Odoo invoice record into a dictionary structure that
        matches the sidecar's expected Zod schema for invoice documents.

        Args:
            invoice: An account.move record representing an invoice.

        Returns:
            dict: Serialized invoice data containing:
                - company: Company information (name, address, vat, phone, email, logo)
                - partner: Customer information (name, address, vat)
                - invoice_metadata: Number, date, due_date, payment_terms
                - lines: Array of line items with product, quantity, prices, taxes
                - totals: Subtotal, tax_amount, total
                - metadata: Currency symbol, notes

        Note:
            Only product lines (display_type == 'product') are included in the
            lines array. Section and note lines are filtered out.
        """
        company = invoice.company_id
        partner = invoice.partner_id
        currency = invoice.currency_id

        # Serialize invoice lines (only product lines)
        lines = []
        for line in invoice.invoice_line_ids:
            if line.display_type != 'product':
                continue

            # Calculate tax rate from tax_ids
            tax_rate = 0.0
            if line.tax_ids:
                # Sum up all tax amounts (simplified - assumes percentage taxes)
                for tax in line.tax_ids:
                    if tax.amount_type == 'percent':
                        tax_rate += tax.amount

            lines.append({
                'product': line.product_id.name if line.product_id else '',
                'product_code': line.product_id.default_code if line.product_id else '',
                'description': line.name or '',
                'quantity': self._format_monetary(line.quantity),
                'unit_of_measure': line.product_uom_id.name if line.product_uom_id else '',
                'unit_price': self._format_monetary(line.price_unit),
                'discount': self._format_monetary(line.discount),
                'tax_rate': self._format_monetary(tax_rate),
                'subtotal': self._format_monetary(line.price_subtotal),
            })

        # Get payment terms name
        payment_terms = ''
        if invoice.invoice_payment_term_id:
            payment_terms = invoice.invoice_payment_term_id.name

        return {
            'company': self._get_company_info(company),
            'partner': {
                'name': partner.name if partner else '',
                'address': self._get_partner_address(partner),
                'vat': partner.vat if partner else '',
                'email': partner.email if partner else '',
                'phone': partner.phone if partner else '',
            },
            'invoice_metadata': {
                'number': invoice.name or '',
                'date': self._format_date(invoice.invoice_date),
                'due_date': self._format_date(invoice.invoice_date_due),
                'payment_terms': payment_terms,
                'reference': invoice.ref or '',
                'payment_reference': invoice.payment_reference or '',
            },
            'lines': lines,
            'totals': {
                'subtotal': self._format_monetary(invoice.amount_untaxed),
                'tax_amount': self._format_monetary(invoice.amount_tax),
                'total': self._format_monetary(invoice.amount_total),
                'amount_due': self._format_monetary(invoice.amount_residual),
            },
            'metadata': {
                'currency_symbol': currency.symbol if currency else '$',
                'currency_code': currency.name if currency else 'USD',
                'notes': invoice.narration or '' if hasattr(invoice, 'narration') else '',
            },
        }

    def _serialize_sale_order_data(self, order):
        """
        Serialize a sale.order record to JSON-compatible dict.

        Converts an Odoo sale order record into a dictionary structure that
        matches the sidecar's expected Zod schema for quote documents.

        Args:
            order: A sale.order record representing a quotation or sales order.

        Returns:
            dict: Serialized sale order data containing:
                - company: Company information (name, address, vat, phone, email, logo)
                - partner: Customer information (name, address, vat)
                - order_metadata: Reference, date, salesperson, validity_date
                - lines: Array of line items with product, quantity, prices, discounts
                - totals: Subtotal, tax_amount, total
                - metadata: Payment terms, notes

        Note:
            Only regular product lines are included. Section, subsection, and
            note lines (display_type is set) are filtered out.
        """
        company = order.company_id
        partner = order.partner_id
        currency = order.currency_id

        # Serialize order lines (only product lines, not sections/notes)
        lines = []
        for line in order.order_line:
            if line.display_type:  # Skip sections and notes
                continue

            lines.append({
                'product': line.product_id.name if line.product_id else '',
                'product_code': line.product_id.default_code if line.product_id else '',
                'description': line.name or '',
                'quantity': self._format_monetary(line.product_uom_qty),
                'unit_of_measure': line.product_uom_id.name if line.product_uom_id else '',
                'unit_price': self._format_monetary(line.price_unit),
                'discount': self._format_monetary(line.discount),
                'subtotal': self._format_monetary(line.price_subtotal),
            })

        # Get salesperson name
        salesperson = ''
        if order.user_id:
            salesperson = order.user_id.name

        # Get payment terms name
        payment_terms = ''
        if order.payment_term_id:
            payment_terms = order.payment_term_id.name

        return {
            'company': self._get_company_info(company),
            'partner': {
                'name': partner.name if partner else '',
                'address': self._get_partner_address(partner),
                'vat': partner.vat if partner else '',
                'email': partner.email if partner else '',
                'phone': partner.phone if partner else '',
            },
            'order_metadata': {
                'reference': order.name or '',
                'date': self._format_date(order.date_order),
                'salesperson': salesperson,
                'validity_date': self._format_date(order.validity_date),
                'client_reference': order.client_order_ref or '',
            },
            'lines': lines,
            'totals': {
                'subtotal': self._format_monetary(order.amount_untaxed),
                'tax_amount': self._format_monetary(order.amount_tax),
                'total': self._format_monetary(order.amount_total),
            },
            'metadata': {
                'currency_symbol': currency.symbol if currency else '$',
                'currency_code': currency.name if currency else 'USD',
                'payment_terms': payment_terms,
                'notes': order.note or '' if hasattr(order, 'note') else '',
            },
        }

    def _serialize_picking_data(self, picking):
        """
        Serialize a stock.picking record to JSON-compatible dict.

        Converts an Odoo stock picking (delivery slip) record into a dictionary
        structure that matches the sidecar's expected Zod schema for delivery
        slip documents.

        Args:
            picking: A stock.picking record representing a delivery/shipment.

        Returns:
            dict: Serialized picking data containing:
                - company: Company information (name, address, vat, phone, email, logo)
                - delivery_address: Delivery destination address
                - picking_metadata: Reference, scheduled_date, origin
                - lines: Array of line items with product, quantity
                - metadata: Notes

        Note:
            As per the Agent Action Plan, delivery slips intentionally set
            unit_price and subtotal to 0 for all line items. Delivery slips
            are shipping documents that show quantities only, not pricing
            information. This is standard business practice for shipping and
            logistics documents.
        """
        company = picking.company_id
        partner = picking.partner_id  # Delivery contact/address

        # Serialize stock moves (line items)
        # Field names must match what the Handlebars template expects
        lines = []
        for move in picking.move_ids:
            if move.state == 'cancel':
                continue

            # NOTE: Delivery slips intentionally set unit_price and subtotal to 0
            # as these documents show quantities only, not pricing information.
            # This is standard business practice for shipping/logistics documents.
            lines.append({
                'product_name': move.product_id.name if move.product_id else '',
                'product_code': move.product_id.default_code if move.product_id else '',
                'description': move.description_picking or '',
                'quantity': self._format_monetary(move.product_uom_qty),
                'quantity_ordered': self._format_monetary(move.product_uom_qty),
                'quantity_delivered': self._format_monetary(move.quantity if hasattr(move, 'quantity') else move.product_uom_qty),
                'uom': move.product_uom.name if move.product_uom else '',
                'unit_price': 0.0,  # Intentionally 0 - delivery slips don't show pricing
                'subtotal': 0.0,  # Intentionally 0 - delivery slips don't show pricing
                'lot_serial': '',  # Lot/serial tracking - populated when applicable
            })

        # Get delivery address
        delivery_address = self._get_partner_address(partner)

        # Determine picking type code for template conditional rendering
        # Map Odoo picking type to template-expected values
        picking_type_code = 'outgoing'  # default
        if picking.picking_type_id:
            picking_type = picking.picking_type_id.code or ''
            if picking_type == 'incoming':
                picking_type_code = 'incoming'
            elif picking_type == 'internal':
                picking_type_code = 'internal'
            else:
                picking_type_code = 'outgoing'

        return {
            'company': self._get_company_info(company),
            'delivery_address': delivery_address,
            'partner': {
                'name': partner.name if partner else '',
                'street': partner.street if partner else '',
                'street2': partner.street2 if partner else '',
                'city': partner.city if partner else '',
                'state': partner.state_id.name if partner and partner.state_id else '',
                'zip': partner.zip if partner else '',
                'country': partner.country_id.name if partner and partner.country_id else '',
                'phone': partner.phone if partner else '',
                'email': partner.email if partner else '',
            },
            'lines': lines,
            # All metadata fields expected by the delivery_slip.hbs template
            # must be in the 'metadata' object, not 'picking_metadata'
            'metadata': {
                'name': picking.name or '',  # Template uses data.metadata.name
                'number': picking.name or '',  # Alias for compatibility
                'origin': picking.origin or '',  # Template uses data.metadata.origin
                'scheduled_date': self._format_datetime(picking.scheduled_date),
                'date_done': self._format_datetime(picking.date_done) if hasattr(picking, 'date_done') else None,
                'state': picking.state or '',
                'picking_type': picking_type_code,  # Template uses data.metadata.picking_type
                'operator': picking.user_id.name if picking.user_id else '',
                'contact': picking.partner_id.name if picking.partner_id else '',
                'notes': picking.note or '' if hasattr(picking, 'note') else '',
            },
        }

    def render_report(self, report_type, record, report):
        """
        Render a PDF document via the sidecar service.

        This is the main entry point for generating PDFs through the sidecar.
        It handles the complete workflow:
        1. Generate a unique request ID for correlation
        2. Serialize the record data based on report type
        3. Build the request payload matching the Zod schema
        4. Sign the request with HMAC-SHA256
        5. Send HTTP POST to the sidecar API
        6. Handle the response and decode the PDF

        Args:
            report_type (str): Type of report to generate. Must be one of:
                - 'invoice': For account.move records
                - 'quote': For sale.order records
                - 'delivery_slip': For stock.picking records
            record: The Odoo record to render (account.move, sale.order, or stock.picking)
            report: The ir.actions.report record (used for options/metadata)

        Returns:
            tuple: (pdf_content, report_type) where:
                - pdf_content (bytes): The binary PDF content
                - report_type (str): Always 'pdf'

        Raises:
            SidecarUnavailable: When the sidecar cannot be reached or returns
                an error. The caller should catch this and fall back to QWeb.

        Example:
            client = SidecarClient(self.env)
            try:
                pdf_content, content_type = client.render_report(
                    'invoice',
                    self.env['account.move'].browse(invoice_id),
                    report
                )
                # pdf_content is binary PDF data
            except SidecarUnavailable:
                # Fall back to QWeb rendering
                pass
        """
        config = self._get_config()

        # Check if sidecar is enabled
        if not config['enabled']:
            msg = "Sidecar service is disabled in configuration"
            raise SidecarUnavailable(msg)

        # Validate configuration
        if not config['api_key']:
            msg = "Sidecar API key not configured"
            raise SidecarUnavailable(msg)
        if not config['secret_key']:
            msg = "Sidecar secret key not configured"
            raise SidecarUnavailable(msg)

        # Generate unique request ID for correlation/tracing
        request_id = str(uuid.uuid4())

        # Serialize record data based on report type
        if report_type == 'invoice':
            data = self._serialize_invoice_data(record)
        elif report_type == 'quote':
            data = self._serialize_sale_order_data(record)
        elif report_type == 'delivery_slip':
            data = self._serialize_picking_data(record)
        else:
            raise SidecarUnavailable(f"Unsupported report type: {report_type}")

        # Build request payload matching Zod DocumentRequestSchema
        payload = {
            'request_id': request_id,
            'report_type': report_type,
            'record_ids': [record.id],
            'data': data,
            'options': {
                'page_size': 'A4',
                'language': 'en_US',
                'copies': 1,
            },
        }

        # Generate HMAC signature
        signature = self._sign_request(payload)

        # Build request headers
        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': config['api_key'],
            'X-Request-ID': request_id,
            'X-HMAC-Signature': signature,
        }

        # Build endpoint URL
        endpoint_url = f"{config['url'].rstrip('/')}/api/v1/render"

        _logger.info(
            "Sending render request to sidecar: request_id=%s, report_type=%s, record_id=%s",
            request_id, report_type, record.id,
        )

        try:
            # Send HTTP POST request to sidecar
            response = requests.post(
                endpoint_url,
                json=payload,
                headers=headers,
                timeout=config['timeout'],
            )

            # Log response status
            _logger.info(
                "Sidecar response received: request_id=%s, status_code=%s",
                request_id, response.status_code,
            )

            # Check for HTTP errors
            if response.status_code != 200:
                error_detail = "Unknown error"
                try:
                    error_data = response.json()
                    error_detail = error_data.get('error', {}).get('message', error_detail)
                except (ValueError, json.JSONDecodeError):
                    error_detail = response.text[:500] if response.text else "No response body"

                _logger.error(
                    "Sidecar returned error: request_id=%s, status=%s, error=%s",
                    request_id, response.status_code, error_detail,
                )
                msg = f"Sidecar returned HTTP {response.status_code}: {error_detail}"
                raise SidecarUnavailable(msg)  # noqa: TRY301

            # Parse response JSON
            response_data = response.json()

            # Extract base64-encoded PDF
            pdf_base64 = response_data.get('pdf_base64')
            if not pdf_base64:
                msg = "Sidecar response missing pdf_base64 field"
                raise SidecarUnavailable(msg)  # noqa: TRY301

            # Decode base64 to binary PDF content
            pdf_content = base64.b64decode(pdf_base64)

            _logger.info(
                "PDF successfully generated via sidecar: request_id=%s, size=%d bytes",
                request_id, len(pdf_content),
            )

            return (pdf_content, 'pdf')

        except requests.exceptions.ConnectionError as e:
            _logger.warning(
                "Sidecar connection error: request_id=%s, error=%s",
                request_id, e,
            )
            raise SidecarUnavailable(f"Cannot connect to sidecar service: {e}")

        except requests.exceptions.Timeout as e:
            _logger.warning(
                "Sidecar timeout: request_id=%s, timeout=%s, error=%s",
                request_id, config['timeout'], e,
            )
            raise SidecarUnavailable(f"Sidecar request timed out after {config['timeout']}s")

        except requests.exceptions.RequestException as e:
            _logger.warning(
                "Sidecar request error: request_id=%s, error=%s",
                request_id, e,
            )
            raise SidecarUnavailable(f"Sidecar request failed: {e}")

        except (ValueError, KeyError) as e:
            _logger.error(
                "Sidecar response parsing error: request_id=%s, error=%s",
                request_id, e,
            )
            raise SidecarUnavailable(f"Invalid sidecar response: {e}")

        except Exception as e:
            _logger.exception(
                "Unexpected error during sidecar communication: request_id=%s",
                request_id,
            )
            raise SidecarUnavailable(f"Unexpected error: {e}")
