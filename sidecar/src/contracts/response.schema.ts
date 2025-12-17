/**
 * @fileoverview Response type definitions and error codes for the document-sidecar service.
 *
 * This module defines Zod schemas for all API response types including:
 * - Error codes with HTTP status mapping
 * - Standardized error response format
 * - Successful PDF render response format
 * - Helper functions for creating responses
 *
 * Zod schemas serve as the single source of truth for TypeScript contracts,
 * providing both runtime validation and type inference capabilities.
 *
 * @module contracts/response.schema
 */

import { z } from 'zod';

// =============================================================================
// ERROR CODES
// =============================================================================

/**
 * Error codes returned by the sidecar service.
 *
 * Each error code maps to a specific HTTP status code and indicates a distinct
 * type of failure in the request processing pipeline.
 *
 * - VALIDATION_ERROR (400): Request payload failed Zod schema validation
 * - AUTH_FAILED (401): Invalid API key or HMAC signature
 * - TEMPLATE_NOT_FOUND (404): Unknown report_type in request
 * - RATE_LIMITED (429): Request rate exceeds configured limit
 * - RENDER_FAILED (500): Puppeteer rendering encountered an error
 * - INTERNAL_ERROR (500): Unexpected server error
 */
export const ErrorCodeSchema = z.enum([
  'VALIDATION_ERROR',
  'AUTH_FAILED',
  'TEMPLATE_NOT_FOUND',
  'RATE_LIMITED',
  'RENDER_FAILED',
  'INTERNAL_ERROR',
]);

/**
 * TypeScript type for error codes, inferred from the Zod schema.
 * One of: 'VALIDATION_ERROR' | 'AUTH_FAILED' | 'TEMPLATE_NOT_FOUND' | 'RATE_LIMITED' | 'RENDER_FAILED' | 'INTERNAL_ERROR'
 */
export type ErrorCode = z.infer<typeof ErrorCodeSchema>;

// =============================================================================
// ERROR CODE TO HTTP STATUS MAPPING
// =============================================================================

/**
 * Maps error codes to their corresponding HTTP status codes.
 *
 * This mapping ensures consistent HTTP status responses across the API:
 * - VALIDATION_ERROR → 400 Bad Request
 * - AUTH_FAILED → 401 Unauthorized
 * - TEMPLATE_NOT_FOUND → 404 Not Found
 * - RATE_LIMITED → 429 Too Many Requests
 * - RENDER_FAILED → 500 Internal Server Error
 * - INTERNAL_ERROR → 500 Internal Server Error
 *
 * @example
 * ```typescript
 * import { ERROR_CODE_TO_STATUS, ErrorCode } from './response.schema.js';
 *
 * const errorCode: ErrorCode = 'VALIDATION_ERROR';
 * const httpStatus = ERROR_CODE_TO_STATUS[errorCode]; // 400
 * ```
 */
export const ERROR_CODE_TO_STATUS: Record<ErrorCode, number> = {
  VALIDATION_ERROR: 400,
  AUTH_FAILED: 401,
  TEMPLATE_NOT_FOUND: 404,
  RATE_LIMITED: 429,
  RENDER_FAILED: 500,
  INTERNAL_ERROR: 500,
};

// =============================================================================
// ERROR RESPONSE SCHEMA
// =============================================================================

/**
 * Zod schema for the error details object.
 *
 * Contains structured information about the error:
 * - code: The specific error code from ErrorCodeSchema
 * - message: Human-readable error description
 * - details: Optional additional context (validation errors, etc.)
 * - request_id: Optional request correlation ID for tracing
 */
const ErrorDetailsSchema = z.object({
  code: ErrorCodeSchema,
  message: z.string().min(1),
  details: z.record(z.unknown()).optional(),
  request_id: z.string().uuid().optional(),
});

/**
 * Zod schema for standardized error responses.
 *
 * All error responses from the sidecar service follow this structure
 * to ensure consistent error handling on the client side.
 *
 * @example
 * ```typescript
 * // Validation error response
 * const errorResponse: ErrorResponse = {
 *   success: false,
 *   error: {
 *     code: 'VALIDATION_ERROR',
 *     message: 'Invalid request payload',
 *     details: { field: 'report_type', issue: 'Invalid enum value' },
 *     request_id: '550e8400-e29b-41d4-a716-446655440000',
 *   },
 * };
 * ```
 */
export const ErrorResponseSchema = z.object({
  success: z.literal(false),
  error: ErrorDetailsSchema,
});

/**
 * TypeScript type for error responses, inferred from the Zod schema.
 */
export type ErrorResponse = z.infer<typeof ErrorResponseSchema>;

// =============================================================================
// SUCCESS RESPONSE SCHEMA
// =============================================================================

/**
 * Zod schema for the successful render data payload.
 *
 * Contains all information about the generated PDF:
 * - pdf_base64: The PDF document encoded as base64 string
 * - filename: Suggested filename for the PDF (e.g., "INV-2024-001.pdf")
 * - page_count: Number of pages in the generated PDF
 * - content_type: MIME type (always "application/pdf")
 * - render_time_ms: Time taken to render the PDF in milliseconds
 */
const RenderDataSchema = z.object({
  pdf_base64: z.string().min(1),
  filename: z.string().min(1),
  page_count: z.number().int().positive(),
  content_type: z.string().default('application/pdf'),
  render_time_ms: z.number().int().nonnegative(),
});

/**
 * Zod schema for successful PDF render responses.
 *
 * Returned when the PDF generation completes successfully.
 * The response includes the base64-encoded PDF data along with
 * metadata about the generated document.
 *
 * @example
 * ```typescript
 * const successResponse: RenderSuccessResponse = {
 *   success: true,
 *   data: {
 *     pdf_base64: 'JVBERi0xLjQKJeLj...',
 *     filename: 'INV-2024-001.pdf',
 *     page_count: 2,
 *     content_type: 'application/pdf',
 *     render_time_ms: 1250,
 *   },
 *   request_id: '550e8400-e29b-41d4-a716-446655440000',
 * };
 * ```
 */
export const RenderSuccessResponseSchema = z.object({
  success: z.literal(true),
  data: RenderDataSchema,
  request_id: z.string().uuid(),
});

/**
 * TypeScript type for successful render responses, inferred from the Zod schema.
 */
export type RenderSuccessResponse = z.infer<typeof RenderSuccessResponseSchema>;

// =============================================================================
// UNION RESPONSE SCHEMA
// =============================================================================

/**
 * Zod schema for all possible API responses (union of success and error).
 *
 * This discriminated union allows type-safe handling of responses:
 *
 * @example
 * ```typescript
 * function handleResponse(response: RenderResponse) {
 *   if (response.success) {
 *     // TypeScript knows this is RenderSuccessResponse
 *     console.log(`PDF has ${response.data.page_count} pages`);
 *   } else {
 *     // TypeScript knows this is ErrorResponse
 *     console.error(`Error: ${response.error.code} - ${response.error.message}`);
 *   }
 * }
 * ```
 */
export const RenderResponseSchema = z.union([
  RenderSuccessResponseSchema,
  ErrorResponseSchema,
]);

/**
 * TypeScript type for all possible render API responses.
 * Discriminated union on the `success` field.
 */
export type RenderResponse = z.infer<typeof RenderResponseSchema>;

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Creates a standardized error response object.
 *
 * This helper function ensures consistent error response structure
 * across all error handling code paths in the sidecar service.
 *
 * @param code - The error code identifying the type of error
 * @param message - Human-readable error description
 * @param requestId - Optional request correlation ID for distributed tracing
 * @param details - Optional additional context (e.g., validation error details)
 * @returns A fully-formed ErrorResponse object
 *
 * @example
 * ```typescript
 * // Create a validation error response
 * const response = createErrorResponse(
 *   'VALIDATION_ERROR',
 *   'Invalid request payload',
 *   '550e8400-e29b-41d4-a716-446655440000',
 *   { field: 'report_type', issue: 'Invalid enum value' }
 * );
 *
 * // Create a simple auth error
 * const authError = createErrorResponse('AUTH_FAILED', 'Invalid API key');
 * ```
 */
export function createErrorResponse(
  code: ErrorCode,
  message: string,
  requestId?: string,
  details?: Record<string, unknown>
): ErrorResponse {
  return {
    success: false,
    error: {
      code,
      message,
      ...(details !== undefined && { details }),
      ...(requestId !== undefined && { request_id: requestId }),
    },
  };
}

/**
 * Creates a successful render response object.
 *
 * This helper function ensures consistent success response structure
 * when returning PDF generation results to the client.
 *
 * @param pdfBase64 - The PDF document encoded as base64 string
 * @param filename - Suggested filename for the PDF download
 * @param pageCount - Number of pages in the generated PDF
 * @param renderTimeMs - Time taken to render the PDF in milliseconds
 * @param requestId - Request correlation ID for distributed tracing
 * @returns A fully-formed RenderSuccessResponse object
 *
 * @example
 * ```typescript
 * const pdfBuffer = await renderService.generatePdf(html, options);
 * const pdfBase64 = pdfBuffer.toString('base64');
 * const pageCount = await pdfService.getPageCount(pdfBuffer);
 *
 * const response = createSuccessResponse(
 *   pdfBase64,
 *   'INV-2024-001.pdf',
 *   pageCount,
 *   1250,
 *   '550e8400-e29b-41d4-a716-446655440000'
 * );
 * ```
 */
export function createSuccessResponse(
  pdfBase64: string,
  filename: string,
  pageCount: number,
  renderTimeMs: number,
  requestId: string
): RenderSuccessResponse {
  return {
    success: true,
    data: {
      pdf_base64: pdfBase64,
      filename,
      page_count: pageCount,
      content_type: 'application/pdf',
      render_time_ms: renderTimeMs,
    },
    request_id: requestId,
  };
}

// =============================================================================
// ADDITIONAL UTILITY TYPES AND FUNCTIONS
// =============================================================================

/**
 * Gets the HTTP status code for a given error code.
 *
 * This is a convenience function that wraps the ERROR_CODE_TO_STATUS mapping
 * with type-safe access.
 *
 * @param code - The error code to look up
 * @returns The corresponding HTTP status code
 *
 * @example
 * ```typescript
 * const status = getHttpStatusForError('RATE_LIMITED'); // 429
 * reply.status(status).send(errorResponse);
 * ```
 */
export function getHttpStatusForError(code: ErrorCode): number {
  return ERROR_CODE_TO_STATUS[code];
}

/**
 * Type guard to check if a response is a success response.
 *
 * @param response - The response to check
 * @returns True if the response is a RenderSuccessResponse
 *
 * @example
 * ```typescript
 * const response = await fetchRenderResult();
 * if (isSuccessResponse(response)) {
 *   // TypeScript narrows type to RenderSuccessResponse
 *   downloadPdf(response.data.pdf_base64);
 * }
 * ```
 */
export function isSuccessResponse(
  response: RenderResponse
): response is RenderSuccessResponse {
  return response.success === true;
}

/**
 * Type guard to check if a response is an error response.
 *
 * @param response - The response to check
 * @returns True if the response is an ErrorResponse
 *
 * @example
 * ```typescript
 * const response = await fetchRenderResult();
 * if (isErrorResponse(response)) {
 *   // TypeScript narrows type to ErrorResponse
 *   logError(response.error.code, response.error.message);
 * }
 * ```
 */
export function isErrorResponse(
  response: RenderResponse
): response is ErrorResponse {
  return response.success === false;
}
