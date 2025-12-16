/**
 * Pino structured JSON logging configuration module for the document-sidecar service.
 * 
 * Provides a pre-configured Pino logger instance with:
 * - Configurable log level from environment (trace/debug/info/warn/error/fatal)
 * - JSON output format for production (machine-readable, suitable for log aggregation)
 * - Pretty-printed colored output for development (human-readable)
 * - Service metadata (name, version) included in all log entries
 * - Sensitive field redaction for security (API keys, authorization headers)
 * - Request correlation via child loggers for distributed tracing
 * 
 * Used throughout the sidecar service for structured logging that supports
 * distributed tracing across Odoo → Sidecar communication via request ID correlation.
 * 
 * @module logger
 */

import pino from 'pino';
import { config } from '../config.js';

/**
 * Determines if the service is running in development mode.
 * Used to toggle between pretty-printed output (development) and JSON output (production).
 */
const isDevelopment = config.nodeEnv === 'development';

/**
 * Pre-configured Pino logger instance for the document-sidecar service.
 * 
 * Configuration:
 * - Log level: Controlled by LOG_LEVEL environment variable (default: 'info')
 * - Transport: pino-pretty in development for colored, human-readable output
 * - Base context: Includes service name and version for log aggregation
 * - Redaction: Automatically redacts sensitive headers (authorization, API keys)
 * 
 * Log Levels (in order of verbosity):
 * - trace: Most verbose, includes detailed debugging information
 * - debug: Debugging information useful during development
 * - info: General operational messages (default)
 * - warn: Warning messages for potentially harmful situations
 * - error: Error events that might still allow the application to continue
 * - fatal: Severe error events that might cause the application to terminate
 * 
 * @constant
 * @type {pino.Logger}
 * 
 * @example
 * ```typescript
 * import { logger } from './utils/logger.js';
 * 
 * // Basic logging at different levels
 * logger.info('Server started');
 * logger.debug({ port: 3000 }, 'Listening on port');
 * logger.warn('Rate limit approaching threshold');
 * logger.error({ err }, 'Failed to generate PDF');
 * 
 * // Structured logging with context
 * logger.info({ reportType: 'invoice', recordId: 123 }, 'Processing document request');
 * ```
 */
/**
 * Sensitive fields to redact from log output.
 * Prevents accidental logging of authentication credentials.
 */
const redactPaths: string[] = [
  // Redact Authorization headers (e.g., Bearer tokens)
  'req.headers.authorization',
  // Redact API key headers (case-insensitive access)
  'req.headers["x-api-key"]',
  'req.headers["X-API-Key"]',
  // Redact HMAC signature headers
  'req.headers["x-hmac-signature"]',
  'req.headers["X-HMAC-Signature"]',
];

/**
 * Base context included in all log entries for log aggregation and filtering.
 */
const baseContext = {
  // Service identifier for multi-service log aggregation
  service: 'document-sidecar',
  // Service version for debugging and release tracking
  version: '1.0.0',
};

/**
 * Pino transport configuration for development mode.
 * Uses pino-pretty for human-readable colored output.
 */
const devTransport: pino.TransportSingleOptions = {
  target: 'pino-pretty',
  options: {
    // Enable colorized output for better readability in terminal
    colorize: true,
    // Format timestamps in local system time (e.g., "2024-01-15 10:30:45")
    translateTime: 'SYS:standard',
    // Omit pid and hostname to reduce noise in development logs
    ignore: 'pid,hostname',
  },
};

// Create logger with transport only in development mode
// In production, JSON output is used (no transport means default JSON formatting)
export const logger: pino.Logger = isDevelopment
  ? pino({
      level: config.logLevel,
      base: baseContext,
      redact: redactPaths,
      transport: devTransport,
    })
  : pino({
      level: config.logLevel,
      base: baseContext,
      redact: redactPaths,
    });

/**
 * Creates a child logger with request correlation ID for distributed tracing.
 * 
 * Child loggers inherit all settings from the parent logger but include
 * additional context (the request ID) in every log entry. This enables
 * tracing requests across the Odoo → Sidecar communication boundary.
 * 
 * The request ID is typically passed via the X-Request-ID header from Odoo
 * and should be included in all log entries for that request.
 * 
 * @param requestId - The unique request ID for correlation (typically UUID)
 * @returns Child Pino logger instance with request context bound
 * 
 * @example
 * ```typescript
 * import { createRequestLogger } from './utils/logger.js';
 * 
 * // In a request handler
 * function handleRenderRequest(req: FastifyRequest) {
 *   const requestId = req.headers['x-request-id'] as string || generateUUID();
 *   const log = createRequestLogger(requestId);
 *   
 *   log.info('Processing render request');
 *   // Output: {"level":30,"time":1234567890,"service":"document-sidecar","version":"1.0.0","requestId":"abc-123","msg":"Processing render request"}
 *   
 *   log.debug({ reportType: 'invoice' }, 'Validated request payload');
 *   log.error({ err }, 'PDF generation failed');
 * }
 * ```
 */
export function createRequestLogger(requestId: string): pino.Logger {
  return logger.child({ requestId });
}

/**
 * Type alias for Pino logger instance.
 * 
 * Exported for use in type annotations throughout the application,
 * enabling strong typing for logger parameters and return values.
 * 
 * @typedef {pino.Logger} Logger
 * 
 * @example
 * ```typescript
 * import { Logger, createRequestLogger } from './utils/logger.js';
 * 
 * class MyService {
 *   private readonly log: Logger;
 *   
 *   constructor(requestId: string) {
 *     this.log = createRequestLogger(requestId);
 *   }
 *   
 *   doSomething(): void {
 *     this.log.info('Doing something');
 *   }
 * }
 * ```
 */
export type Logger = pino.Logger;
