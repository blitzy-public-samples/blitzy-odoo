/**
 * @fileoverview Zod schema definitions for validating incoming PDF render requests
 * to the document-sidecar service.
 *
 * This module serves as the single source of truth for request contracts, providing:
 * - Runtime type validation via Zod schemas
 * - TypeScript type inference via z.infer<>
 * - Validation of report_type, record_ids, data payload, and rendering options
 *
 * @module sidecar/contracts/request.schema
 * @see Agent Action Plan Section 0.1.1 - Zod schemas as source of truth
 */

import { z } from 'zod';

// =============================================================================
// ENUM SCHEMAS
// =============================================================================

/**
 * Schema for supported report types in the document-sidecar service.
 *
 * Supported types:
 * - `invoice`: Invoice documents from account.move records
 * - `quote`: Quotation/Sale Order documents from sale.order records
 * - `delivery_slip`: Delivery slip documents from stock.picking records
 *
 * @example
 * ```typescript
 * const result = ReportTypeSchema.safeParse('invoice');
 * if (result.success) {
 *   console.log(result.data); // 'invoice'
 * }
 * ```
 */
export const ReportTypeSchema = z.enum(['invoice', 'quote', 'delivery_slip']);

/**
 * TypeScript type for supported report types.
 * Inferred from ReportTypeSchema: 'invoice' | 'quote' | 'delivery_slip'
 */
export type ReportType = z.infer<typeof ReportTypeSchema>;

/**
 * Schema for supported page sizes in PDF generation.
 *
 * Supported sizes:
 * - `A4`: ISO A4 (210mm × 297mm) - Default
 * - `Letter`: US Letter (8.5" × 11")
 * - `Legal`: US Legal (8.5" × 14")
 *
 * @example
 * ```typescript
 * const result = PageSizeSchema.safeParse('A4');
 * if (result.success) {
 *   console.log(result.data); // 'A4'
 * }
 * ```
 */
export const PageSizeSchema = z.enum(['A4', 'Letter', 'Legal']);

/**
 * TypeScript type for supported page sizes.
 * Inferred from PageSizeSchema: 'A4' | 'Letter' | 'Legal'
 */
export type PageSize = z.infer<typeof PageSizeSchema>;

// =============================================================================
// RENDER OPTIONS SCHEMA
// =============================================================================

/**
 * Schema for optional rendering configuration.
 *
 * All fields have sensible defaults:
 * - `page_size`: Defaults to 'A4'
 * - `language`: Defaults to 'en_US' (only supported language per spec)
 * - `copies`: Defaults to 1 (must be positive integer)
 *
 * @example
 * ```typescript
 * const options = RenderOptionsSchema.parse({
 *   page_size: 'Letter',
 *   copies: 2,
 * });
 * // options.language === 'en_US' (default applied)
 * ```
 */
export const RenderOptionsSchema = z.object({
  /**
   * Page size for PDF output.
   * @default 'A4'
   */
  page_size: PageSizeSchema.default('A4'),

  /**
   * Language code for document rendering.
   * Note: Only 'en_US' is currently supported per Agent Action Plan.
   * @default 'en_US'
   */
  language: z.string().default('en_US'),

  /**
   * Number of copies to generate (affects page count in response).
   * Must be a positive integer.
   * @default 1
   */
  copies: z.number().int().positive().default(1),
}).optional();

/**
 * TypeScript type for optional rendering configuration.
 * Inferred from RenderOptionsSchema.
 */
export type RenderOptions = z.infer<typeof RenderOptionsSchema>;

// =============================================================================
// COMPANY DATA SCHEMA
// =============================================================================

/**
 * Schema for company information used in document headers.
 *
 * Required fields:
 * - `name`: Company name (required)
 *
 * Optional fields include address components, VAT number, contact info, and logo.
 *
 * @example
 * ```typescript
 * const company = CompanyDataSchema.parse({
 *   name: 'Acme Corporation',
 *   street: '123 Business Ave',
 *   city: 'Commerce City',
 *   country: 'United States',
 *   email: 'info@acme.com',
 * });
 * ```
 */
export const CompanyDataSchema = z.object({
  /** Company legal name (required) */
  name: z.string(),

  /** Primary street address line */
  street: z.string().optional(),

  /** Secondary street address line (suite, unit, etc.) */
  street2: z.string().optional(),

  /** City name */
  city: z.string().optional(),

  /** State, province, or region */
  state: z.string().optional(),

  /** Postal/ZIP code */
  zip: z.string().optional(),

  /** Country name */
  country: z.string().optional(),

  /** VAT/Tax identification number */
  vat: z.string().optional(),

  /** Primary phone number */
  phone: z.string().optional(),

  /** Primary email address (validated format) */
  email: z.string().email().optional(),

  /** Company website URL (validated format) */
  website: z.string().url().optional(),

  /** URL to company logo image (validated format) */
  logo_url: z.string().url().optional(),
});

// =============================================================================
// PARTNER DATA SCHEMA
// =============================================================================

/**
 * Schema for customer/vendor (partner) information.
 *
 * Used to represent the recipient of documents (customer on invoices/quotes,
 * delivery address on delivery slips).
 *
 * Required fields:
 * - `name`: Partner name (required)
 *
 * @example
 * ```typescript
 * const partner = PartnerDataSchema.parse({
 *   name: 'John Smith',
 *   street: '456 Customer Lane',
 *   city: 'Buyerville',
 *   email: 'john@example.com',
 * });
 * ```
 */
export const PartnerDataSchema = z.object({
  /** Partner/customer name (required) */
  name: z.string(),

  /** Primary street address line */
  street: z.string().optional(),

  /** Secondary street address line */
  street2: z.string().optional(),

  /** City name */
  city: z.string().optional(),

  /** State, province, or region */
  state: z.string().optional(),

  /** Postal/ZIP code */
  zip: z.string().optional(),

  /** Country name */
  country: z.string().optional(),

  /** VAT/Tax identification number */
  vat: z.string().optional(),

  /** Contact phone number */
  phone: z.string().optional(),

  /** Contact email address (validated format) */
  email: z.string().email().optional(),
});

// =============================================================================
// LINE ITEM SCHEMA
// =============================================================================

/**
 * Schema for individual line items in documents.
 *
 * Represents a single product/service line with quantity, pricing, and tax info.
 *
 * Note: For delivery slips, unit_price and subtotal will be 0 as per
 * Agent Action Plan Section 0.8.5 (delivery slips show quantities only).
 *
 * @example
 * ```typescript
 * const lineItem = LineItemSchema.parse({
 *   sequence: 1,
 *   product_name: 'Widget Pro',
 *   description: 'Professional grade widget',
 *   quantity: 10,
 *   uom: 'Units',
 *   unit_price: 29.99,
 *   discount: 5,
 *   tax_names: ['VAT 20%'],
 *   subtotal: 284.91,
 * });
 * ```
 */
export const LineItemSchema = z.object({
  /** Display sequence/order (integer) */
  sequence: z.number().int(),

  /** Product or service name (required) */
  product_name: z.string(),

  /** Additional description or notes */
  description: z.string().optional(),

  /** Quantity ordered/delivered */
  quantity: z.number(),

  /** Unit of measure (e.g., 'Units', 'Hours', 'Kg') */
  uom: z.string().optional(),

  /** Price per unit (0 for delivery slips) */
  unit_price: z.number(),

  /**
   * Discount percentage applied to line item.
   * @default 0
   */
  discount: z.number().default(0),

  /** List of tax names applied to this line */
  tax_names: z.array(z.string()).optional(),

  /** Line subtotal after discount and before taxes (0 for delivery slips) */
  subtotal: z.number(),
});

// =============================================================================
// TAX LINE SCHEMA
// =============================================================================

/**
 * Schema for tax breakdown lines.
 *
 * Represents a single tax type with its base amount and calculated tax.
 *
 * @example
 * ```typescript
 * const taxLine = TaxLineSchema.parse({
 *   name: 'VAT 20%',
 *   base: 1000.00,
 *   amount: 200.00,
 * });
 * ```
 */
export const TaxLineSchema = z.object({
  /** Tax name/description (e.g., 'VAT 20%', 'Sales Tax') */
  name: z.string(),

  /** Taxable base amount */
  base: z.number(),

  /** Calculated tax amount */
  amount: z.number(),
});

// =============================================================================
// TOTALS SCHEMA
// =============================================================================

/**
 * Schema for document totals and amounts.
 *
 * Contains subtotal, taxes, grand total, and optional payment information.
 *
 * @example
 * ```typescript
 * const totals = TotalsSchema.parse({
 *   subtotal: 1000.00,
 *   tax_amount: 200.00,
 *   total: 1200.00,
 *   amount_paid: 500.00,
 *   amount_due: 700.00,
 *   currency_symbol: '€',
 *   tax_lines: [
 *     { name: 'VAT 20%', base: 1000.00, amount: 200.00 }
 *   ],
 * });
 * ```
 */
export const TotalsSchema = z.object({
  /** Subtotal before taxes */
  subtotal: z.number(),

  /** Total tax amount */
  tax_amount: z.number(),

  /** Grand total including taxes */
  total: z.number(),

  /** Amount already paid (for invoices) */
  amount_paid: z.number().optional(),

  /** Remaining amount due (for invoices) */
  amount_due: z.number().optional(),

  /**
   * Currency symbol for display.
   * @default '$'
   */
  currency_symbol: z.string().default('$'),

  /** Detailed tax breakdown by tax type */
  tax_lines: z.array(TaxLineSchema).optional(),
});

// =============================================================================
// DOCUMENT METADATA SCHEMA
// =============================================================================

/**
 * Schema for document metadata common to all document types.
 *
 * Contains document identifiers, dates, and additional text fields.
 *
 * @example
 * ```typescript
 * const metadata = DocumentMetadataSchema.parse({
 *   number: 'INV/2024/0001',
 *   date: '2024-01-15',
 *   due_date: '2024-02-15',
 *   reference: 'PO-12345',
 *   salesperson: 'Jane Doe',
 *   payment_terms: 'Net 30',
 *   notes: 'Thank you for your business!',
 * });
 * ```
 */
export const DocumentMetadataSchema = z.object({
  /** Document number/reference (e.g., 'INV/2024/0001') */
  number: z.string(),

  /** Document date (ISO format string, e.g., '2024-01-15') */
  date: z.string(),

  /** Payment due date (for invoices) */
  due_date: z.string().optional(),

  /** Customer reference (e.g., purchase order number) */
  reference: z.string().optional(),

  /** Assigned salesperson name */
  salesperson: z.string().optional(),

  /** Payment terms description */
  payment_terms: z.string().optional(),

  /** Additional notes to display on document */
  notes: z.string().optional(),

  /** Terms and conditions text */
  terms_and_conditions: z.string().optional(),
});

// =============================================================================
// DOCUMENT DATA SCHEMA
// =============================================================================

/**
 * Schema for the complete document data payload.
 *
 * Combines all data structures needed to render any document type:
 * - Company information (header)
 * - Partner/customer information
 * - Line items
 * - Totals
 * - Metadata
 *
 * @example
 * ```typescript
 * const documentData = DocumentDataSchema.parse({
 *   company: { name: 'Acme Corp', ... },
 *   partner: { name: 'John Smith', ... },
 *   lines: [{ sequence: 1, product_name: 'Widget', ... }],
 *   totals: { subtotal: 100, tax_amount: 20, total: 120 },
 *   metadata: { number: 'INV/2024/0001', date: '2024-01-15' },
 * });
 * ```
 */
export const DocumentDataSchema = z.object({
  /** Company information for document header */
  company: CompanyDataSchema,

  /** Customer/vendor information */
  partner: PartnerDataSchema,

  /** Array of line items */
  lines: z.array(LineItemSchema),

  /** Document totals and amounts */
  totals: TotalsSchema,

  /** Document metadata (number, dates, references) */
  metadata: DocumentMetadataSchema,
});

/**
 * TypeScript type for complete document data payload.
 * Inferred from DocumentDataSchema.
 */
export type DocumentData = z.infer<typeof DocumentDataSchema>;

// =============================================================================
// DOCUMENT REQUEST SCHEMA
// =============================================================================

/**
 * Main schema for validating incoming PDF render requests.
 *
 * This is the primary entry point for request validation in the sidecar service.
 * All incoming POST /api/v1/render requests are validated against this schema.
 *
 * Per Agent Action Plan Section 0.1.1, this schema serves as the single source
 * of truth for the request contract between Odoo and the sidecar service.
 *
 * Required fields:
 * - `request_id`: UUID for request correlation and logging
 * - `report_type`: One of 'invoice', 'quote', 'delivery_slip'
 * - `record_ids`: Array of Odoo record IDs (at least one required)
 * - `data`: Complete document data payload
 *
 * Optional fields:
 * - `options`: Rendering options (page_size, language, copies)
 *
 * Note: Per Agent Action Plan Section 0.8.1, only single-record rendering is
 * supported. When multiple record_ids are provided, only the first is used.
 *
 * @example
 * ```typescript
 * const request = DocumentRequestSchema.parse({
 *   request_id: '550e8400-e29b-41d4-a716-446655440000',
 *   report_type: 'invoice',
 *   record_ids: [123],
 *   data: {
 *     company: { name: 'Acme Corp' },
 *     partner: { name: 'John Smith' },
 *     lines: [...],
 *     totals: { subtotal: 100, tax_amount: 20, total: 120 },
 *     metadata: { number: 'INV/2024/0001', date: '2024-01-15' },
 *   },
 *   options: {
 *     page_size: 'A4',
 *     language: 'en_US',
 *     copies: 1,
 *   },
 * });
 * ```
 *
 * @see Agent Action Plan Section 0.1.1 for contract specification
 * @see Agent Action Plan Section 0.8.1 for single-record constraint
 */
export const DocumentRequestSchema = z.object({
  /**
   * Unique request identifier for correlation and logging.
   * Must be a valid UUID v4 format.
   */
  request_id: z.string().uuid(),

  /**
   * Type of document to render.
   * Determines which Handlebars template is used.
   */
  report_type: ReportTypeSchema,

  /**
   * Array of Odoo record IDs to render.
   * Must contain at least one positive integer.
   * Note: Only the first record is rendered (single-record rendering only).
   */
  record_ids: z.array(z.number().int().positive()).min(1),

  /**
   * Complete document data payload.
   * Contains all information needed to render the document.
   */
  data: DocumentDataSchema,

  /**
   * Optional rendering configuration.
   * Includes page size, language, and number of copies.
   */
  options: RenderOptionsSchema,
});

/**
 * TypeScript type for complete document render request.
 * Inferred from DocumentRequestSchema.
 *
 * This type is used throughout the sidecar service for type-safe
 * handling of validated request data.
 */
export type DocumentRequest = z.infer<typeof DocumentRequestSchema>;
