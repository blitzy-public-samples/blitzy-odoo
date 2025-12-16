/**
 * X-Request-ID correlation ID middleware for the document-sidecar Fastify service.
 * 
 * This middleware intercepts incoming requests to extract the X-Request-ID header
 * if present, or generates a new UUID v4 if missing. The request ID is attached
 * to the request object for downstream logging and included in response headers
 * for distributed tracing across Odoo → Sidecar communication.
 * 
 * Request correlation enables:
 * - Tracing requests from Odoo through the sidecar service
 * - Correlating log entries across distributed systems
 * - Debugging and monitoring request flows
 * - Performance analysis of end-to-end request processing
 * 
 * @module middleware/request-id
 */

import { FastifyRequest, FastifyReply } from 'fastify';
import { randomUUID } from 'crypto';
import { logger } from '../utils/logger.js';

/**
 * HTTP header name for request correlation ID.
 * 
 * This header is used both for extracting incoming request IDs from Odoo
 * and for setting the correlation ID in outgoing responses.
 * 
 * Standard convention uses lowercase header names for consistency.
 * 
 * @constant {string}
 */
export const REQUEST_ID_HEADER = 'x-request-id';

/**
 * Extend Fastify's request type definition to include the requestId property.
 * 
 * This declaration merging allows TypeScript to recognize the `requestId`
 * property on all FastifyRequest objects after the middleware has processed
 * the request.
 * 
 * @see https://www.fastify.io/docs/latest/Reference/TypeScript/#creating-a-typed-plugin
 */
declare module 'fastify' {
  interface FastifyRequest {
    /**
     * Unique identifier for this request, either extracted from the
     * X-Request-ID header or generated as a new UUID v4.
     * 
     * Available after the requestIdMiddleware hook has executed.
     */
    requestId: string;
  }
}

/**
 * Fastify onRequest hook that extracts or generates X-Request-ID
 * for request correlation in distributed tracing.
 * 
 * This middleware performs the following operations:
 * 1. Extracts existing X-Request-ID header if present from incoming request
 * 2. Generates a new RFC 4122 compliant UUID v4 if header is missing
 * 3. Attaches requestId to request object for downstream access in handlers
 * 4. Adds requestId to response headers for client correlation
 * 5. Logs request received event with correlation ID for tracing
 * 
 * The middleware is designed to be registered as a Fastify onRequest hook,
 * ensuring it runs before any route handlers or other middleware that may
 * need access to the request ID.
 * 
 * @param request - The incoming Fastify request object
 * @param reply - The Fastify reply object for setting response headers
 * @returns Promise<void> - Resolves when middleware processing is complete
 * 
 * @example
 * ```typescript
 * import Fastify from 'fastify';
 * import { requestIdMiddleware } from './middleware/request-id.js';
 * 
 * const app = Fastify();
 * 
 * // Register as onRequest hook
 * app.addHook('onRequest', requestIdMiddleware);
 * 
 * // Access requestId in route handlers
 * app.get('/health', async (request, reply) => {
 *   console.log(`Request ID: ${request.requestId}`);
 *   return { status: 'ok', requestId: request.requestId };
 * });
 * ```
 */
export async function requestIdMiddleware(
  request: FastifyRequest,
  reply: FastifyReply
): Promise<void> {
  // Extract existing X-Request-ID from incoming request headers
  // If the header exists and is a string, use it; otherwise generate new UUID
  const existingRequestId = request.headers[REQUEST_ID_HEADER];
  const requestId: string = typeof existingRequestId === 'string' && existingRequestId.length > 0
    ? existingRequestId
    : randomUUID();
  
  // Attach request ID to request object for downstream access
  // This allows route handlers and other middleware to access the correlation ID
  request.requestId = requestId;
  
  // Add request ID to response headers for client-side correlation
  // Enables the calling service (Odoo) to correlate responses with requests
  reply.header(REQUEST_ID_HEADER, requestId);
  
  // Log request received event with structured context for distributed tracing
  // Includes correlation ID, HTTP method, and URL for request identification
  logger.info(
    { 
      requestId, 
      method: request.method, 
      url: request.url 
    }, 
    'Request received'
  );
}

/**
 * Safely extracts request ID from a FastifyRequest object.
 * 
 * This utility function provides a clean interface for accessing the
 * request correlation ID from the request object. It should be used
 * after the requestIdMiddleware has processed the request.
 * 
 * @param request - The Fastify request object (must have been processed by requestIdMiddleware)
 * @returns The request ID string associated with this request
 * 
 * @example
 * ```typescript
 * import { getRequestId } from './middleware/request-id.js';
 * import { createRequestLogger } from '../utils/logger.js';
 * 
 * app.post('/api/v1/render', async (request, reply) => {
 *   const requestId = getRequestId(request);
 *   const log = createRequestLogger(requestId);
 *   
 *   log.info('Processing render request');
 *   // ... handler logic
 * });
 * ```
 */
export function getRequestId(request: FastifyRequest): string {
  return request.requestId;
}
