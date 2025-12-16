/**
 * @fileoverview Structured error handler middleware for the document-sidecar Fastify service.
 *
 * This module implements Fastify's setErrorHandler to catch all unhandled errors
 * and format them into consistent ErrorResponse structures with appropriate HTTP status codes.
 *
 * Error Code to HTTP Status Mapping (per Agent Action Plan Section 0.8.6):
 * - VALIDATION_ERROR: 400 Bad Request
 * - AUTH_FAILED: 401 Unauthorized
 * - TEMPLATE_NOT_FOUND: 404 Not Found
 * - RATE_LIMITED: 429 Too Many Requests
 * - RENDER_FAILED: 500 Internal Server Error
 * - INTERNAL_ERROR: 500 Internal Server Error
 *
 * All API errors return consistent JSON responses with:
 * - error.code: Machine-readable error code
 * - error.message: Human-readable error description
 * - error.details: Optional additional context (validation errors, etc.)
 * - error.request_id: Request correlation ID for distributed tracing
 *
 * @module middleware/error-handler
 */

import type { FastifyInstance, FastifyRequest, FastifyReply, FastifyError } from 'fastify';
import { ZodError } from 'zod';
import {
  ErrorCode,
  createErrorResponse,
  ERROR_CODE_TO_STATUS,
} from '../contracts/response.schema.js';
import { logger } from '../utils/logger.js';

// =============================================================================
// CUSTOM APPLICATION ERROR CLASS
// =============================================================================

/**
 * Custom application error class with error code support.
 *
 * This error class extends the native Error to include:
 * - An ErrorCode that maps to a specific HTTP status
 * - Optional details object for additional context
 *
 * Use the factory functions (authError, validationError, etc.) to create
 * instances of this class for cleaner, more readable code.
 *
 * @example
 * ```typescript
 * // Using the factory function (recommended)
 * throw authError('Invalid API key');
 *
 * // Using the class directly
 * throw new AppError('VALIDATION_ERROR', 'Invalid request', { field: 'report_type' });
 * ```
 */
export class AppError extends Error {
  /**
   * The error code identifying the type of error.
   * Maps to an HTTP status code via ERROR_CODE_TO_STATUS.
   */
  readonly code: ErrorCode;

  /**
   * Optional additional context about the error.
   * Included in the error response for debugging.
   */
  readonly details?: Record<string, unknown>;

  /**
   * Creates a new AppError instance.
   *
   * @param code - The error code from the ErrorCode enum
   * @param message - Human-readable error description
   * @param details - Optional additional context for debugging
   */
  constructor(code: ErrorCode, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    // Only assign details if provided (satisfies exactOptionalPropertyTypes)
    if (details !== undefined) {
      this.details = details;
    }

    // Maintains proper stack trace for where error was thrown (V8 engines)
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, AppError);
    }
  }
}

// =============================================================================
// ERROR CLASSIFICATION HELPERS
// =============================================================================

/**
 * Maps Zod validation errors to a structured details object.
 *
 * Extracts the path, message, and code from each Zod issue to provide
 * clear, actionable error information to API consumers.
 *
 * @param error - ZodError instance from failed validation
 * @returns Structured validation error details with issues array
 *
 * @example
 * ```typescript
 * try {
 *   DocumentRequestSchema.parse(invalidData);
 * } catch (error) {
 *   if (error instanceof ZodError) {
 *     const details = mapZodErrorToDetails(error);
 *     // { issues: [{ path: 'report_type', message: 'Invalid enum value', code: 'invalid_enum_value' }] }
 *   }
 * }
 * ```
 */
function mapZodErrorToDetails(error: ZodError): Record<string, unknown> {
  return {
    issues: error.issues.map((issue) => ({
      path: issue.path.join('.'),
      message: issue.message,
      code: issue.code,
    })),
  };
}

/**
 * Determines the appropriate error code for an error.
 *
 * Classification logic:
 * 1. AppError: Use the error's own code property
 * 2. ZodError: Classify as VALIDATION_ERROR (400)
 * 3. FastifyError: Map statusCode to appropriate error code
 * 4. Unknown errors: Default to INTERNAL_ERROR (500)
 *
 * @param error - The error to classify
 * @returns The appropriate ErrorCode for the error
 *
 * @example
 * ```typescript
 * const code = determineErrorCode(new AppError('AUTH_FAILED', 'Invalid key'));
 * // Returns: 'AUTH_FAILED'
 *
 * const code = determineErrorCode(new ZodError([]));
 * // Returns: 'VALIDATION_ERROR'
 * ```
 */
function determineErrorCode(error: Error | FastifyError): ErrorCode {
  // AppError carries its own error code
  if (error instanceof AppError) {
    return error.code;
  }

  // ZodError indicates validation failure
  if (error instanceof ZodError) {
    return 'VALIDATION_ERROR';
  }

  // FastifyError or errors with statusCode property
  if ('statusCode' in error) {
    const fastifyError = error as FastifyError;
    const statusCode = fastifyError.statusCode;

    // Map known status codes to error codes
    if (statusCode === 429) {
      return 'RATE_LIMITED';
    }
    if (statusCode === 401) {
      return 'AUTH_FAILED';
    }
    if (statusCode === 404) {
      return 'TEMPLATE_NOT_FOUND';
    }
    if (statusCode === 400) {
      return 'VALIDATION_ERROR';
    }
  }

  // Default to internal error for unknown error types
  return 'INTERNAL_ERROR';
}

// =============================================================================
// ERROR HANDLER REGISTRATION
// =============================================================================

/**
 * Registers the global error handler with the Fastify instance.
 *
 * This function sets up Fastify's error handler to catch all unhandled errors
 * and format them into consistent ErrorResponse structures. The handler:
 *
 * 1. Extracts the request ID for correlation tracking
 * 2. Determines the appropriate error code from the error type
 * 3. Maps the error code to an HTTP status code
 * 4. Logs the error with appropriate severity (warn for 4xx, error for 5xx)
 * 5. Sends a structured JSON error response
 *
 * Error Code to HTTP Status Mapping (per Section 0.8.6):
 * - VALIDATION_ERROR: 400 Bad Request
 * - AUTH_FAILED: 401 Unauthorized
 * - TEMPLATE_NOT_FOUND: 404 Not Found
 * - RATE_LIMITED: 429 Too Many Requests
 * - RENDER_FAILED: 500 Internal Server Error
 * - INTERNAL_ERROR: 500 Internal Server Error
 *
 * @param app - The Fastify instance to register the handler with
 *
 * @example
 * ```typescript
 * import Fastify from 'fastify';
 * import { registerErrorHandler } from './middleware/error-handler.js';
 *
 * const app = Fastify();
 * registerErrorHandler(app);
 *
 * app.get('/test', () => {
 *   throw new AppError('VALIDATION_ERROR', 'Test error');
 * });
 * ```
 */
export function registerErrorHandler(app: FastifyInstance): void {
  app.setErrorHandler(
    (error: Error | FastifyError, request: FastifyRequest, reply: FastifyReply) => {
      // Extract request ID for correlation tracking
      // Fastify's request-id hook should have set this, fallback to 'unknown'
      const requestId = request.id as string || 'unknown';

      // Determine the error code based on error type
      const errorCode = determineErrorCode(error);

      // Map error code to HTTP status code
      const statusCode = ERROR_CODE_TO_STATUS[errorCode];

      // Extract error details based on error type
      let details: Record<string, unknown> | undefined;

      if (error instanceof ZodError) {
        // For Zod validation errors, provide structured issue information
        details = mapZodErrorToDetails(error);
      } else if (error instanceof AppError && error.details) {
        // For AppError with details, pass them through
        details = error.details;
      }

      // Log the error with appropriate severity level
      // Server errors (5xx) are logged as errors with stack traces
      // Client errors (4xx) are logged as warnings without stack traces
      if (statusCode >= 500) {
        logger.error(
          {
            requestId,
            errorCode,
            error: error.message,
            stack: error.stack,
          },
          'Internal server error'
        );
      } else {
        logger.warn(
          {
            requestId,
            errorCode,
            error: error.message,
          },
          'Client error'
        );
      }

      // Create the standardized error response
      const errorResponse = createErrorResponse(
        errorCode,
        error.message,
        requestId,
        details
      );

      // Send the error response with appropriate status code
      reply.status(statusCode).send(errorResponse);
    }
  );

  logger.info('Error handler registered');
}

// =============================================================================
// ERROR FACTORY FUNCTIONS
// =============================================================================

/**
 * Creates an authentication failure error.
 *
 * Use this when API key validation or HMAC signature verification fails.
 * Results in HTTP 401 Unauthorized response.
 *
 * @param message - Human-readable error description (default: 'Authentication failed')
 * @returns AppError with AUTH_FAILED code
 *
 * @example
 * ```typescript
 * // In auth middleware
 * if (!apiKey || apiKey !== config.apiKey) {
 *   throw authError('Invalid API key');
 * }
 *
 * if (!isValidSignature) {
 *   throw authError('Invalid HMAC signature');
 * }
 * ```
 */
export function authError(message: string = 'Authentication failed'): AppError {
  return new AppError('AUTH_FAILED', message);
}

/**
 * Creates a validation error.
 *
 * Use this when request payload validation fails (outside of Zod automatic validation).
 * Results in HTTP 400 Bad Request response.
 *
 * @param message - Human-readable error description
 * @param details - Optional additional context about the validation failure
 * @returns AppError with VALIDATION_ERROR code
 *
 * @example
 * ```typescript
 * // Custom validation logic
 * if (request.record_ids.length > 1) {
 *   throw validationError('Batch rendering not supported', {
 *     field: 'record_ids',
 *     constraint: 'Only single record rendering is supported',
 *   });
 * }
 * ```
 */
export function validationError(
  message: string,
  details?: Record<string, unknown>
): AppError {
  return new AppError('VALIDATION_ERROR', message, details);
}

/**
 * Creates a template not found error.
 *
 * Use this when the requested report type doesn't have a corresponding template.
 * Results in HTTP 404 Not Found response.
 *
 * @param reportType - The report type that was not found
 * @returns AppError with TEMPLATE_NOT_FOUND code
 *
 * @example
 * ```typescript
 * // In template service
 * const template = this.templates.get(reportType);
 * if (!template) {
 *   throw templateNotFoundError(reportType);
 * }
 * ```
 */
export function templateNotFoundError(reportType: string): AppError {
  return new AppError(
    'TEMPLATE_NOT_FOUND',
    `Template not found for report type: ${reportType}`
  );
}

/**
 * Creates a render failure error.
 *
 * Use this when Puppeteer PDF rendering encounters an error.
 * Results in HTTP 500 Internal Server Error response.
 *
 * @param message - Human-readable error description
 * @param details - Optional additional context about the render failure
 * @returns AppError with RENDER_FAILED code
 *
 * @example
 * ```typescript
 * // In renderer service
 * try {
 *   const pdfBuffer = await page.pdf(options);
 *   return pdfBuffer;
 * } catch (err) {
 *   throw renderError('PDF generation failed', {
 *     puppeteerError: err.message,
 *     reportType,
 *   });
 * }
 * ```
 */
export function renderError(
  message: string,
  details?: Record<string, unknown>
): AppError {
  return new AppError('RENDER_FAILED', message, details);
}

/**
 * Creates an internal server error.
 *
 * Use this for unexpected errors that don't fit other categories.
 * Results in HTTP 500 Internal Server Error response.
 *
 * @param message - Human-readable error description (default: 'Internal server error')
 * @returns AppError with INTERNAL_ERROR code
 *
 * @example
 * ```typescript
 * // Catch-all for unexpected errors
 * try {
 *   await performOperation();
 * } catch (err) {
 *   logger.error({ err }, 'Unexpected error during operation');
 *   throw internalError('An unexpected error occurred');
 * }
 * ```
 */
export function internalError(message: string = 'Internal server error'): AppError {
  return new AppError('INTERNAL_ERROR', message);
}
