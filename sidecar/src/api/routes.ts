/**
 * @fileoverview Route registration module for the document-sidecar Fastify service.
 *
 * This module exports a Fastify plugin function (`registerRoutes`) that mounts all API
 * endpoints for the document-sidecar service. It follows the Fastify plugin architecture
 * for modular route registration.
 *
 * Registered Routes:
 * - GET /health - Liveness probe (no authentication required)
 * - GET /ready - Readiness probe (no authentication required)
 * - POST /api/v1/render - PDF generation endpoint (requires authentication)
 *
 * Design Decisions:
 * - Health endpoints bypass authentication for container orchestration compatibility
 * - Protected routes use authMiddleware for API key + HMAC-SHA256 validation
 * - Route handlers are kept in separate files for separation of concerns
 * - Route path constants are exported for use in testing and documentation
 *
 * @module api/routes
 * @see Agent Action Plan Sections 0.3.1, 0.5.1
 */

import type { FastifyInstance, FastifyPluginOptions } from 'fastify';
import { renderHandler } from './render.handler.js';
import { healthHandler, readyHandler } from './health.handler.js';
import { authMiddleware } from '../middleware/auth.js';
import { logger } from '../utils/logger.js';

// =============================================================================
// CONSTANTS
// =============================================================================

/**
 * Route path constants for the document-sidecar API.
 *
 * Provides a centralized, type-safe reference to all API endpoint paths.
 * These constants are useful for:
 * - Testing: Construct URLs in test assertions
 * - Documentation: Reference paths consistently
 * - Refactoring: Change paths in one place
 *
 * @constant
 * @type {Object}
 * @property {string} HEALTH - Liveness probe endpoint path
 * @property {string} READY - Readiness probe endpoint path
 * @property {string} RENDER - PDF generation endpoint path
 *
 * @example
 * ```typescript
 * import { ROUTES } from './routes.js';
 *
 * // In tests
 * const response = await app.inject({
 *   method: 'GET',
 *   url: ROUTES.HEALTH,
 * });
 *
 * // In documentation
 * console.log(`Health endpoint: ${ROUTES.HEALTH}`);
 * ```
 */
export const ROUTES = {
  /**
   * Liveness probe endpoint.
   * Returns 200 OK if the service process is running.
   * Used by container orchestrators (Kubernetes, Docker) to determine
   * if the service needs to be restarted.
   */
  HEALTH: '/health',

  /**
   * Readiness probe endpoint.
   * Returns 200 OK if the service is ready to accept render requests.
   * Checks availability of critical components (e.g., Puppeteer browser).
   * Used by container orchestrators to determine if traffic should be routed.
   */
  READY: '/ready',

  /**
   * PDF generation endpoint.
   * Accepts POST requests with document data and returns base64-encoded PDF.
   * Requires API key authentication and HMAC-SHA256 signature verification.
   */
  RENDER: '/api/v1/render',
} as const;

/**
 * Type for route path values, enabling type-safe route references.
 *
 * @typedef {typeof ROUTES[keyof typeof ROUTES]} RoutePath
 */
export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];

// =============================================================================
// ROUTE REGISTRATION
// =============================================================================

/**
 * Registers all API routes with the Fastify instance.
 *
 * This function follows the Fastify plugin pattern and can be registered
 * using `app.register(registerRoutes)`. It mounts all API endpoints with
 * their respective handlers and middleware.
 *
 * ## Routes Registered:
 *
 * ### Health Endpoints (No Authentication):
 * - `GET /health` - Liveness probe for container orchestration
 *   - Always returns 200 OK if process is running
 *   - No authentication required
 *
 * - `GET /ready` - Readiness probe for container orchestration
 *   - Returns 200 OK if service can process requests
 *   - Checks Puppeteer browser availability
 *   - No authentication required
 *
 * ### API v1 Endpoints (Authentication Required):
 * - `POST /api/v1/render` - PDF document generation
 *   - Requires X-API-Key header with valid API key
 *   - Requires X-HMAC-Signature header with valid HMAC-SHA256 signature
 *   - Accepts JSON body with DocumentRequest schema
 *   - Returns JSON with base64-encoded PDF
 *
 * ## Security:
 * Health endpoints bypass authentication to allow container orchestrators
 * and load balancers to perform health checks without credentials. All
 * business endpoints require full authentication.
 *
 * ## Performance:
 * Route registration is synchronous and happens once during server startup.
 * No performance impact on request handling.
 *
 * @param app - The Fastify instance to register routes on
 * @param _opts - Plugin options (unused, required by Fastify plugin signature)
 * @returns Promise that resolves when all routes are registered
 *
 * @example
 * ```typescript
 * import Fastify from 'fastify';
 * import { registerRoutes } from './api/routes.js';
 *
 * const app = Fastify({ logger: true });
 *
 * // Register routes as a plugin
 * await app.register(registerRoutes);
 *
 * // Or with prefix
 * await app.register(registerRoutes, { prefix: '/v2' });
 *
 * // Start server
 * await app.listen({ port: 3000 });
 * ```
 *
 * @example
 * ```typescript
 * // Routes are now accessible:
 * // curl http://localhost:3000/health
 * // curl http://localhost:3000/ready
 * // curl -X POST http://localhost:3000/api/v1/render \
 * //   -H "Content-Type: application/json" \
 * //   -H "X-API-Key: your-api-key" \
 * //   -H "X-HMAC-Signature: signature" \
 * //   -d '{"request_id":"...","report_type":"invoice",...}'
 * ```
 */
export async function registerRoutes(
  app: FastifyInstance,
  _opts: FastifyPluginOptions
): Promise<void> {
  // =========================================================================
  // Health Endpoints (No Authentication Required)
  // =========================================================================
  //
  // These endpoints are used by container orchestrators (Kubernetes, Docker)
  // and load balancers for health checking. They must be accessible without
  // authentication to function properly in production environments.

  /**
   * GET /health - Liveness Probe
   *
   * Returns 200 OK if the service process is running. This is a simple
   * liveness check that indicates the service does not need to be restarted.
   * The response includes service name, version, and timestamp.
   */
  app.get(ROUTES.HEALTH, healthHandler);

  /**
   * GET /ready - Readiness Probe
   *
   * Returns 200 OK if the service is ready to accept and process render
   * requests. This includes checking the availability of the Puppeteer
   * browser instance. Returns 503 Service Unavailable if not ready.
   */
  app.get(ROUTES.READY, readyHandler);

  // =========================================================================
  // API v1 Routes (Authentication Required)
  // =========================================================================
  //
  // All API endpoints require authentication via:
  // 1. X-API-Key header: Must match configured API_KEY
  // 2. X-HMAC-Signature header: HMAC-SHA256 of request body using SECRET_KEY
  //
  // The authMiddleware validates both credentials before the handler executes.

  /**
   * POST /api/v1/render - PDF Document Generation
   *
   * Accepts a DocumentRequest JSON payload and generates a PDF document
   * using Handlebars templates and Puppeteer headless Chrome.
   *
   * Request Headers:
   * - Content-Type: application/json
   * - X-API-Key: API authentication key
   * - X-HMAC-Signature: HMAC-SHA256 signature of request body
   * - X-Request-ID: (optional) Correlation ID for distributed tracing
   *
   * Request Body: DocumentRequest schema (see contracts/request.schema.ts)
   * Response: RenderSuccessResponse with base64-encoded PDF
   *
   * Error Responses:
   * - 400 VALIDATION_ERROR: Invalid request payload
   * - 401 AUTH_FAILED: Invalid API key or HMAC signature
   * - 404 TEMPLATE_NOT_FOUND: Unknown report_type
   * - 429 RATE_LIMITED: Too many requests
   * - 500 RENDER_FAILED: PDF generation error
   */
  app.post(ROUTES.RENDER, {
    preHandler: authMiddleware,
    handler: renderHandler,
  });

  // Log successful route registration for operational visibility
  logger.info(
    {
      routes: {
        health: ROUTES.HEALTH,
        ready: ROUTES.READY,
        render: ROUTES.RENDER,
      },
    },
    'Routes registered successfully'
  );
}

/**
 * Default export for convenient plugin registration.
 *
 * Allows importing as:
 * ```typescript
 * import routes from './api/routes.js';
 * app.register(routes);
 * ```
 *
 * @default registerRoutes
 */
export default registerRoutes;
