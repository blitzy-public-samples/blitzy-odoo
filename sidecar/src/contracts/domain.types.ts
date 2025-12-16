/**
 * Business Domain Type Definitions for Document Sidecar Service
 *
 * This module defines pure TypeScript interfaces for the data structures
 * used across invoice, quote, and delivery slip documents. These types
 * represent data serialized from Odoo ORM objects and passed to the
 * sidecar service for PDF rendering.
 *
 * The sidecar is stateless - all data for rendering is received in
 * self-contained request payloads matching these type definitions.
 *
 * @module domain.types
 */

// ============================================================================
// REPORT TYPE DEFINITIONS
// ============================================================================

/**
 * Supported report types for PDF generation.
 * These map to Odoo report names:
 * - 'invoice' -> 'account.report_invoice'
 * - 'quote' -> 'sale.report_saleorder'
 * - 'delivery_slip' -> 'stock.report_deliveryslip'
 */
export const REPORT_TYPES = ['invoice', 'quote', 'delivery_slip'] as const;

/**
 * Union type representing valid report types.
 * Derived from REPORT_TYPES constant for type safety.
 */
export type ReportType = typeof REPORT_TYPES[number];

// ============================================================================
// PAGE SIZE DEFINITIONS
// ============================================================================

/**
 * Supported page sizes for PDF generation.
 * - 'A4': ISO 216 standard (210mm x 297mm) - Default for most regions
 * - 'Letter': US standard (8.5" x 11")
 * - 'Legal': US legal size (8.5" x 14")
 */
export const PAGE_SIZES = ['A4', 'Letter', 'Legal'] as const;

/**
 * Union type representing valid page sizes.
 * Derived from PAGE_SIZES constant for type safety.
 */
export type PageSize = typeof PAGE_SIZES[number];

// ============================================================================
// COMPANY INTERFACE
// ============================================================================

/**
 * Company information for document header.
 *
 * Contains the issuing company's details displayed in the document header,
 * including contact information, address, and branding assets.
 *
 * @example
 * ```typescript
 * const company: Company = {
 *   name: "Acme Corporation",
 *   street: "123 Main Street",
 *   city: "San Francisco",
 *   state: "CA",
 *   zip: "94102",
 *   country: "United States",
 *   vat: "US123456789",
 *   phone: "+1 (555) 123-4567",
 *   email: "info@acme.com",
 *   website: "https://www.acme.com",
 *   logo_url: "https://www.acme.com/logo.png"
 * };
 * ```
 */
export interface Company {
  /**
   * Legal company name.
   * Required field displayed prominently in document header.
   */
  name: string;

  /**
   * Primary street address line.
   * @example "123 Main Street"
   */
  street?: string;

  /**
   * Secondary street address line (suite, floor, building, etc.).
   * @example "Suite 500"
   */
  street2?: string;

  /**
   * City name.
   * @example "San Francisco"
   */
  city?: string;

  /**
   * State, province, or region name.
   * @example "California" or "CA"
   */
  state?: string;

  /**
   * Postal/ZIP code.
   * @example "94102"
   */
  zip?: string;

  /**
   * Country name.
   * @example "United States"
   */
  country?: string;

  /**
   * VAT/Tax identification number.
   * Format varies by country.
   * @example "US123456789", "GB123456789", "DE123456789"
   */
  vat?: string;

  /**
   * Primary phone number.
   * @example "+1 (555) 123-4567"
   */
  phone?: string;

  /**
   * Primary email address.
   * @example "info@company.com"
   */
  email?: string;

  /**
   * Company website URL.
   * @example "https://www.company.com"
   */
  website?: string;

  /**
   * URL to company logo image.
   * Should be accessible by the sidecar service for rendering.
   * Recommended formats: PNG, JPEG, SVG.
   * @example "https://www.company.com/logo.png"
   */
  logo_url?: string;
}

// ============================================================================
// PARTNER INTERFACE
// ============================================================================

/**
 * Customer or vendor contact information.
 *
 * Represents the recipient/customer for invoices and quotes,
 * or the delivery address for delivery slips.
 *
 * @example
 * ```typescript
 * const partner: Partner = {
 *   name: "John Doe",
 *   street: "456 Oak Avenue",
 *   city: "Los Angeles",
 *   state: "CA",
 *   zip: "90001",
 *   country: "United States",
 *   email: "john.doe@example.com"
 * };
 * ```
 */
export interface Partner {
  /**
   * Partner/customer name (individual or company).
   * Required field displayed as recipient in document.
   */
  name: string;

  /**
   * Primary street address line.
   * @example "456 Oak Avenue"
   */
  street?: string;

  /**
   * Secondary street address line.
   * @example "Apt 2B"
   */
  street2?: string;

  /**
   * City name.
   * @example "Los Angeles"
   */
  city?: string;

  /**
   * State, province, or region.
   * @example "California" or "CA"
   */
  state?: string;

  /**
   * Postal/ZIP code.
   * @example "90001"
   */
  zip?: string;

  /**
   * Country name.
   * @example "United States"
   */
  country?: string;

  /**
   * VAT/Tax identification number.
   * Used for B2B transactions and tax reporting.
   * @example "GB123456789"
   */
  vat?: string;

  /**
   * Contact phone number.
   * @example "+1 (555) 987-6543"
   */
  phone?: string;

  /**
   * Contact email address.
   * @example "customer@example.com"
   */
  email?: string;
}

// ============================================================================
// LINE ITEM INTERFACE
// ============================================================================

/**
 * Individual line item in a document.
 *
 * Represents a single product or service line on invoices, quotes,
 * or delivery slips. Contains quantity, pricing, and description.
 *
 * Note: For delivery slips, unit_price and subtotal will be 0 as
 * these documents show quantities only (per Section 0.8.5).
 *
 * @example
 * ```typescript
 * const lineItem: LineItem = {
 *   sequence: 1,
 *   product_name: "Widget Pro",
 *   description: "Professional-grade widget with extended warranty",
 *   quantity: 10,
 *   uom: "Units",
 *   unit_price: 99.99,
 *   discount: 10,
 *   tax_names: ["VAT 20%"],
 *   subtotal: 899.91
 * };
 * ```
 */
export interface LineItem {
  /**
   * Line sequence number for ordering.
   * Used to maintain consistent line item ordering in the document.
   */
  sequence: number;

  /**
   * Product or service name.
   * Primary identifier displayed for the line item.
   */
  product_name: string;

  /**
   * Extended description or notes for the line item.
   * May contain additional product details or special instructions.
   */
  description?: string;

  /**
   * Quantity of items.
   * Can be fractional for weight/volume-based products.
   */
  quantity: number;

  /**
   * Unit of measure.
   * @example "Units", "kg", "hours", "pieces"
   */
  uom?: string;

  /**
   * Unit price before discount.
   * Note: Set to 0 for delivery slips (quantities only).
   */
  unit_price: number;

  /**
   * Discount percentage applied to this line.
   * Value from 0-100 representing percentage.
   * @example 10 for 10% discount
   */
  discount: number;

  /**
   * Names of applicable taxes.
   * Array of tax descriptions applied to this line.
   * @example ["VAT 20%", "Local Tax 2%"]
   */
  tax_names?: string[];

  /**
   * Calculated subtotal for this line after discount.
   * Formula: (quantity * unit_price) * (1 - discount/100)
   * Note: Set to 0 for delivery slips (quantities only).
   */
  subtotal: number;
}

// ============================================================================
// TAX LINE INTERFACE
// ============================================================================

/**
 * Tax breakdown line showing individual tax calculations.
 *
 * Provides detailed tax information for document totals section,
 * showing the base amount and calculated tax for each tax type.
 *
 * @example
 * ```typescript
 * const taxLine: TaxLine = {
 *   name: "VAT 20%",
 *   base: 1000.00,
 *   amount: 200.00
 * };
 * ```
 */
export interface TaxLine {
  /**
   * Tax name/description.
   * @example "VAT 20%", "Sales Tax", "GST"
   */
  name: string;

  /**
   * Base amount the tax is calculated on.
   * Sum of applicable line subtotals before tax.
   */
  base: number;

  /**
   * Calculated tax amount.
   * Result of applying tax rate to base amount.
   */
  amount: number;
}

// ============================================================================
// TOTALS INTERFACE
// ============================================================================

/**
 * Document totals and amounts.
 *
 * Contains all monetary summaries for the document including
 * subtotals, taxes, and final amounts due.
 *
 * @example
 * ```typescript
 * const totals: Totals = {
 *   subtotal: 1000.00,
 *   tax_amount: 200.00,
 *   total: 1200.00,
 *   amount_paid: 500.00,
 *   amount_due: 700.00,
 *   currency_symbol: "$",
 *   tax_lines: [
 *     { name: "VAT 20%", base: 1000.00, amount: 200.00 }
 *   ]
 * };
 * ```
 */
export interface Totals {
  /**
   * Sum of all line subtotals before tax.
   * Total of all LineItem.subtotal values.
   */
  subtotal: number;

  /**
   * Total tax amount.
   * Sum of all TaxLine.amount values.
   */
  tax_amount: number;

  /**
   * Grand total including tax.
   * subtotal + tax_amount
   */
  total: number;

  /**
   * Amount already paid (for invoices).
   * Used to calculate remaining balance.
   */
  amount_paid?: number;

  /**
   * Amount remaining to be paid (for invoices).
   * Calculated as: total - amount_paid
   */
  amount_due?: number;

  /**
   * Currency symbol for display.
   * @example "$", "€", "£", "¥"
   */
  currency_symbol: string;

  /**
   * Detailed tax breakdown by tax type.
   * Array of individual tax calculations.
   */
  tax_lines?: TaxLine[];
}

// ============================================================================
// DOCUMENT METADATA INTERFACE
// ============================================================================

/**
 * Metadata common to all document types.
 *
 * Contains reference numbers, dates, and additional information
 * that appears in the document header or footer areas.
 *
 * @example
 * ```typescript
 * const metadata: DocumentMetadata = {
 *   number: "INV-2024-001234",
 *   date: "2024-01-15",
 *   due_date: "2024-02-15",
 *   reference: "PO-2024-5678",
 *   salesperson: "Jane Smith",
 *   payment_terms: "Net 30",
 *   notes: "Thank you for your business!",
 *   terms_and_conditions: "Standard terms apply."
 * };
 * ```
 */
export interface DocumentMetadata {
  /**
   * Document number/reference.
   * Primary identifier displayed on the document.
   * @example "INV-2024-001234", "SO-2024-5678", "WH/OUT/00001"
   */
  number: string;

  /**
   * Document date (issue date).
   * ISO 8601 date string format.
   * @example "2024-01-15"
   */
  date: string;

  /**
   * Payment due date (for invoices) or validity date (for quotes).
   * ISO 8601 date string format.
   * @example "2024-02-15"
   */
  due_date?: string;

  /**
   * External reference number (customer PO, etc.).
   * @example "PO-2024-5678", "Customer Ref: ABC123"
   */
  reference?: string;

  /**
   * Salesperson or account manager name.
   * @example "Jane Smith"
   */
  salesperson?: string;

  /**
   * Payment terms description.
   * @example "Net 30", "Due on receipt", "50% upfront"
   */
  payment_terms?: string;

  /**
   * Additional notes to display on the document.
   * Typically shown in a notes section.
   * @example "Thank you for your business!"
   */
  notes?: string;

  /**
   * Terms and conditions text.
   * May be displayed in footer or dedicated section.
   */
  terms_and_conditions?: string;
}

// ============================================================================
// BASE DOCUMENT DATA INTERFACE
// ============================================================================

/**
 * Base structure for all document data payloads.
 *
 * Contains the common structure shared by invoices, quotes, and
 * delivery slips. Extended by document-specific interfaces.
 *
 * @example
 * ```typescript
 * const baseData: BaseDocumentData = {
 *   company: { name: "Acme Corp", ... },
 *   partner: { name: "John Doe", ... },
 *   lines: [{ sequence: 1, product_name: "Widget", ... }],
 *   totals: { subtotal: 100, tax_amount: 20, total: 120, currency_symbol: "$" },
 *   metadata: { number: "DOC-001", date: "2024-01-15" }
 * };
 * ```
 */
export interface BaseDocumentData {
  /**
   * Issuing company information.
   * Displayed in document header.
   */
  company: Company;

  /**
   * Recipient/customer information.
   * Displayed in recipient address block.
   */
  partner: Partner;

  /**
   * Array of document line items.
   * Products/services listed in the document body.
   */
  lines: LineItem[];

  /**
   * Document totals and amounts.
   * Displayed in totals section.
   */
  totals: Totals;

  /**
   * Document metadata (numbers, dates, references).
   * Displayed in header and various document sections.
   */
  metadata: DocumentMetadata;
}

// ============================================================================
// INVOICE DATA INTERFACE
// ============================================================================

/**
 * Invoice-specific document data.
 *
 * Extends BaseDocumentData with fields specific to invoices,
 * including payment information and invoice type.
 *
 * Supported invoice types:
 * - 'out_invoice': Customer invoice (accounts receivable)
 * - 'out_refund': Credit note / refund
 *
 * @example
 * ```typescript
 * const invoiceData: InvoiceData = {
 *   company: { name: "Acme Corp", ... },
 *   partner: { name: "John Doe", ... },
 *   lines: [...],
 *   totals: { ..., amount_due: 500.00 },
 *   metadata: { number: "INV-2024-001", date: "2024-01-15", due_date: "2024-02-15" },
 *   invoice_type: "out_invoice",
 *   payment_state: "not_paid"
 * };
 * ```
 */
export interface InvoiceData extends BaseDocumentData {
  /**
   * Type of invoice document.
   * - 'out_invoice': Standard customer invoice
   * - 'out_refund': Credit note / refund to customer
   */
  invoice_type?: 'out_invoice' | 'out_refund';

  /**
   * Current payment status of the invoice.
   * @example "not_paid", "partial", "paid", "in_payment"
   */
  payment_state?: string;
}

// ============================================================================
// QUOTE DATA INTERFACE
// ============================================================================

/**
 * Quote/Sale Order specific document data.
 *
 * Extends BaseDocumentData with fields specific to quotations
 * and sales orders, including validity and customer references.
 *
 * @example
 * ```typescript
 * const quoteData: QuoteData = {
 *   company: { name: "Acme Corp", ... },
 *   partner: { name: "John Doe", ... },
 *   lines: [...],
 *   totals: { ... },
 *   metadata: { number: "SO-2024-001", date: "2024-01-15" },
 *   validity_date: "2024-02-15",
 *   client_order_ref: "PO-CUSTOMER-123"
 * };
 * ```
 */
export interface QuoteData extends BaseDocumentData {
  /**
   * Quote validity/expiration date.
   * ISO 8601 date string format.
   * @example "2024-02-15"
   */
  validity_date?: string;

  /**
   * Customer's purchase order reference.
   * External reference number from customer.
   * @example "PO-CUSTOMER-123"
   */
  client_order_ref?: string;
}

// ============================================================================
// DELIVERY SLIP DATA INTERFACE
// ============================================================================

/**
 * Delivery Slip specific document data.
 *
 * Extends BaseDocumentData with fields specific to delivery/shipping
 * documents, including logistics and tracking information.
 *
 * **IMPORTANT (per Section 0.8.5):**
 * Delivery slips intentionally show quantities only - unit_price and
 * subtotal values are 0 for all line items. This is standard practice
 * for shipping/logistics documents as:
 * - Pricing information is confidential
 * - Warehouse/logistics staff only need quantity information
 * - These are shipping documents, not invoices
 *
 * @example
 * ```typescript
 * const deliverySlipData: DeliverySlipData = {
 *   company: { name: "Acme Corp", ... },
 *   partner: { name: "John Doe", ... },
 *   lines: [
 *     { sequence: 1, product_name: "Widget", quantity: 10, unit_price: 0, discount: 0, subtotal: 0 }
 *   ],
 *   totals: { subtotal: 0, tax_amount: 0, total: 0, currency_symbol: "$" },
 *   metadata: { number: "WH/OUT/00001", date: "2024-01-15" },
 *   scheduled_date: "2024-01-16",
 *   origin: "SO-2024-001",
 *   carrier: "FedEx Ground",
 *   tracking_reference: "794644790135"
 * };
 * ```
 */
export interface DeliverySlipData extends BaseDocumentData {
  /**
   * Scheduled delivery/shipping date.
   * ISO 8601 date string format.
   * @example "2024-01-16"
   */
  scheduled_date?: string;

  /**
   * Source document reference.
   * Typically the sales order that originated this delivery.
   * @example "SO-2024-001"
   */
  origin?: string;

  /**
   * Shipping carrier name.
   * @example "FedEx Ground", "UPS", "DHL Express"
   */
  carrier?: string;

  /**
   * Shipping tracking number/reference.
   * @example "794644790135", "1Z999AA10123456784"
   */
  tracking_reference?: string;
}

// ============================================================================
// RENDER OPTIONS INTERFACE
// ============================================================================

/**
 * Optional rendering configuration for PDF generation.
 *
 * Allows customization of PDF output properties such as
 * page size, language, and number of copies.
 *
 * Note: Language support is currently limited to 'en_US' only.
 * i18n support is explicitly out of scope per requirements.
 *
 * @example
 * ```typescript
 * const options: RenderOptions = {
 *   page_size: "A4",
 *   language: "en_US",
 *   copies: 2
 * };
 * ```
 */
export interface RenderOptions {
  /**
   * Page size for PDF output.
   * Defaults to 'A4' if not specified.
   */
  page_size?: PageSize;

  /**
   * Language code for document rendering.
   * Currently only 'en_US' is supported.
   * Parameter accepted for future i18n expansion.
   * @default "en_US"
   */
  language?: string;

  /**
   * Number of copies to generate.
   * Controls page duplication in output PDF.
   * @default 1
   */
  copies?: number;
}
