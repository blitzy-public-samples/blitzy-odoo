/**
 * @fileoverview POST /api/v1/render endpoint handler for the document-sidecar service.
 *
 * This handler processes PDF generation requests by:
 * 1. Validating incoming JSON requests using Zod DocumentRequestSchema
 * 2. Coordinating with TemplateService to render Handlebars templates to HTML
 * 3. Using RendererService to generate PDF via Puppeteer
 * 4. Extracting page count via PdfService
 * 5. Encoding PDF to base64 and returning RenderSuccessResponse
 *
 * Per Agent Action Plan Section 0.8.1:
 * - Single-record rendering only (batch rendering is OUT OF SCOPE)
 * - When multiple record_ids are provided, only the first is used
 * - Warning is logged for batch request attempts
 *
 * Error Handling (per Section 0.8.6):
 * - VALIDATION_ERROR (400): Zod schema validation fails
 * - TEMPLATE_NOT_FOUND (404): Unknown report_type in request
 * - RENDER_FAILED (500): Puppeteer rendering error
 *
 * @module api/render.handler
 * @see Agent Action Plan Sections 0.3.1, 0.3.2, 0.5.1, 0.5.4, 0.8.1
 */

import type { FastifyRequest, FastifyReply } from 'fastify';
import {
  DocumentRequestSchema,
  type DocumentRequest,
} from '../contracts/request.schema.js';
import { createSuccessResponse } from '../contracts/response.schema.js';
import { templateService } from '../services/template.service.js';
import { rendererService } from '../services/renderer.service.js';
import { getPageCount } from '../services/pdf.service.js';
import { encodeToBase64 } from '../utils/base64.js';
import { createRequestLogger } from '../utils/logger.js';
import type { BaseDocumentData } from '../contracts/domain.types.js';
import {
  AppError,
  templateNotFoundError,
  renderError,
} from '../middleware/error-handler.js';

// =============================================================================
// CONSTANTS
// =============================================================================

/**
 * Mapping of report types to filename prefixes for generated PDFs.
 * Used by generateFilename() to create human-readable file names.
 *
 * @constant
 * @type {Record<string, string>}
 */
const FILENAME_PREFIXES: Record<string, string> = {
  invoice: 'Invoice',
  quote: 'Quote',
  delivery_slip: 'DeliverySlip',
};

/**
 * Default filename prefix for unknown report types.
 * Should rarely be used as validation catches unknown types.
 *
 * @constant
 */
const DEFAULT_FILENAME_PREFIX = 'Document';

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Generates a filename for the PDF based on report type and document number.
 *
 * Creates a human-readable filename combining the document type prefix
 * with the document number from metadata. The filename is sanitized to
 * replace any characters that might cause issues in file systems.
 *
 * @param reportType - The type of report ('invoice', 'quote', 'delivery_slip')
 * @param documentNumber - The document number from metadata (e.g., 'INV-2024-001')
 * @returns Generated filename with .pdf extension
 *
 * @example
 * ```typescript
 * generateFilename('invoice', 'INV-2024-001');
 * // Returns: 'Invoice_INV-2024-001.pdf'
 *
 * generateFilename('delivery_slip', 'WH/OUT/00001');
 * // Returns: 'DeliverySlip_WH-OUT-00001.pdf'
 * ```
 */
function generateFilename(reportType: string, documentNumber: string): string {
  // Get the appropriate prefix for the report type
  const prefix = FILENAME_PREFIXES[reportType] || DEFAULT_FILENAME_PREFIX;

  // Sanitize the document number by replacing problematic characters
  // Forward slashes, backslashes, and other special characters are replaced with dashes
  const sanitizedNumber = documentNumber.replace(/[/\\:*?"<>|]/g, '-');

  return `${prefix}_${sanitizedNumber}.pdf`;
}

// =============================================================================
// MAIN HANDLER
// =============================================================================

/**
 * Handler for POST /api/v1/render endpoint.
 *
 * Processes PDF generation requests by validating the request body,
 * rendering the appropriate Handlebars template to HTML, generating
 * a PDF via Puppeteer, and returning a structured success response.
 *
 * ## Request Flow:
 * 1. Validate request body against DocumentRequestSchema using Zod safeParse
 * 2. Log warning if multiple record_ids (batch not supported per Section 0.8.1)
 * 3. Check template existence for the requested report_type
 * 4. Render Handlebars template with business data to HTML
 * 5. Generate PDF using Puppeteer via RendererService
 * 6. Extract page count from PDF buffer via PdfService
 * 7. Encode PDF buffer to base64 for JSON transmission
 * 8. Generate filename based on report type and document number
 * 9. Return RenderSuccessResponse with all metadata
 *
 * ## Error Handling:
 * - Validation failures: Throws AppError with VALIDATION_ERROR code (400)
 * - Unknown report type: Throws via templateNotFoundError() (404)
 * - Rendering failures: Throws via renderError() (500)
 *
 * ## Performance:
 * - Target P95 latency: Under 5 seconds for standard documents
 * - Browser instance reuse eliminates ~500ms startup per request
 * - Template caching avoids repeated filesystem reads
 *
 * @param request - Fastify request with JSON body containing DocumentRequest
 * @param reply - Fastify reply for sending HTTP responses
 * @returns Promise that resolves when response is sent
 * @throws {AppError} VALIDATION_ERROR when request body validation fails
 * @throws {AppError} TEMPLATE_NOT_FOUND when report_type is not recognized
 * @throws {AppError} RENDER_FAILED when PDF generation encounters an error
 *
 * @example
 * ```typescript
 * // Register with Fastify routes
 * app.post('/api/v1/render', renderHandler);
 *
 * // Example request body:
 * {
 *   "request_id": "550e8400-e29b-41d4-a716-446655440000",
 *   "report_type": "invoice",
 *   "record_ids": [123],
 *   "data": {
 *     "company": { "name": "Acme Corp" },
 *     "partner": { "name": "John Doe" },
 *     "lines": [...],
 *     "totals": { "subtotal": 100, "tax_amount": 20, "total": 120, "currency_symbol": "$" },
 *     "metadata": { "number": "INV-2024-001", "date": "2024-01-15" }
 *   },
 *   "options": { "page_size": "A4", "language": "en_US" }
 * }
 * ```
 */
export async function renderHandler(
  request: FastifyRequest,
  reply: FastifyReply
): Promise<void> {
  // Record start time for render_time_ms calculation
  const startTime = Date.now();

  // Get request ID for correlation tracking (set by request-id middleware)
  // Use Fastify's request.id which is set by the onRequest hook
  const requestId = (request.id as string) || 'unknown';
  const log = createRequestLogger(requestId);

  log.info({ body: request.body }, 'Processing render request');

  // =========================================================================
  // Step 1: Validate request body against DocumentRequestSchema
  // =========================================================================

  const parseResult = DocumentRequestSchema.safeParse(request.body);

  if (!parseResult.success) {
    log.warn(
      { errors: parseResult.error.issues },
      'Request validation failed'
    );

    // Throw AppError with VALIDATION_ERROR code and structured details
    // The error handler will format this into a proper ErrorResponse
    // Include Zod error code for client debugging (per error handler mapZodErrorToDetails pattern)
    throw new AppError('VALIDATION_ERROR', 'Invalid request payload', {
      issues: parseResult.error.issues.map((issue) => ({
        path: issue.path.join('.'),
        message: issue.message,
        code: issue.code,
      })),
    });
  }

  // Extract validated data with full type safety
  const documentRequest: DocumentRequest = parseResult.data;
  const { request_id: bodyRequestId, report_type, record_ids, data, options } = documentRequest;

  // =========================================================================
  // Step 2: Warn about batch requests (single-record rendering only per spec)
  // =========================================================================

  if (record_ids.length > 1) {
    log.warn(
      {
        recordCount: record_ids.length,
        recordIds: record_ids,
      },
      'Batch rendering not supported, processing first record only'
    );
  }

  // =========================================================================
  // Step 3: Check template exists for the requested report type
  // =========================================================================

  if (!templateService.hasTemplate(report_type)) {
    log.error({ reportType: report_type }, 'Template not found');
    throw templateNotFoundError(report_type);
  }

  try {
    // =========================================================================
    // Step 4: Render HTML template with business data
    // =========================================================================

    // Extract language from options, defaulting to 'en_US' per spec
    // Note: Only 'en_US' is currently supported (i18n is out of scope)
    const language = options?.language || 'en_US';

    log.debug(
      { reportType: report_type, language },
      'Rendering template'
    );

    // Render Handlebars template to HTML string
    // The template service handles template loading, caching, and partial registration
    // Cast data to BaseDocumentData - the Zod inferred type is structurally compatible
    // but TypeScript strict mode requires explicit cast due to optional field handling
    const html = await templateService.render(report_type, data as BaseDocumentData, language);

    // =========================================================================
    // Step 5: Generate PDF using Puppeteer via RendererService
    // =========================================================================

    // Determine page size from options, default to 'A4'
    const pageSize = options?.page_size || 'A4';

    log.debug(
      { pageSize },
      'Generating PDF'
    );

    // Generate PDF buffer via Puppeteer
    // The renderer service manages browser instance pooling and page lifecycle
    const pdfBuffer = await rendererService.generatePdf(
      html,
      {
        pageSize,
        printBackground: true,
      },
      requestId
    );

    // =========================================================================
    // Step 6: Extract page count from PDF buffer
    // =========================================================================

    const pageCount = await getPageCount(pdfBuffer);

    // =========================================================================
    // Step 7: Encode PDF buffer to base64 for JSON response
    // =========================================================================

    const pdfBase64 = encodeToBase64(pdfBuffer);

    // =========================================================================
    // Step 8: Generate filename for the PDF
    // =========================================================================

    const filename = generateFilename(report_type, data.metadata.number);

    // =========================================================================
    // Step 9: Calculate render time and log success
    // =========================================================================

    const renderTimeMs = Date.now() - startTime;

    log.info(
      {
        reportType: report_type,
        pageCount,
        renderTimeMs,
        pdfSizeBytes: pdfBuffer.length,
        filename,
      },
      'PDF generated successfully'
    );

    // =========================================================================
    // Step 10: Return success response
    // =========================================================================

    // Use the request_id from the body for the response (for correlation with Odoo)
    const response = createSuccessResponse(
      pdfBase64,
      filename,
      pageCount,
      renderTimeMs,
      bodyRequestId
    );

    reply.status(200).send(response);

  } catch (error) {
    // =========================================================================
    // Error Handling: Re-throw AppErrors, wrap other errors as RENDER_FAILED
    // =========================================================================

    // If it's already an AppError (like from template service), re-throw it
    // The global error handler will format it appropriately
    if (error instanceof AppError) {
      throw error;
    }

    // Calculate how long we spent before the error
    const errorTimeMs = Date.now() - startTime;

    // Log the error with full context for debugging
    log.error(
      {
        error,
        reportType: report_type,
        errorTimeMs,
      },
      'PDF rendering failed'
    );

    // Wrap unexpected errors in a RENDER_FAILED AppError
    // This ensures consistent error response format
    throw renderError(
      `Failed to render ${report_type}: ${error instanceof Error ? error.message : 'Unknown error'}`,
      { reportType: report_type }
    );
  }
}
