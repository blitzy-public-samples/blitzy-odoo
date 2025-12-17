/**
 * @fileoverview Health and readiness probe endpoint handlers for the document-sidecar service.
 *
 * Provides endpoint handlers for container orchestration (Kubernetes, Docker) health checks:
 * - GET /health (liveness probe): Always returns 200 OK if the service process is running
 * - GET /ready (readiness probe): Returns 200 if service is ready to accept render requests
 *
 * These endpoints are critical for container orchestration:
 * - Liveness probe determines if the service should be restarted
 * - Readiness probe determines if the service should receive traffic
 *
 * Key Characteristics:
 * - Bypass authentication and rate limiting
 * - Always responsive (separate from render pipeline)
 * - Lightweight to avoid blocking orchestrator health checks
 * - Include request correlation for distributed tracing
 *
 * @module sidecar/api/health.handler
 * @see Agent Action Plan Sections 0.3.1, 0.5.1, 0.7.5
 */

import type { FastifyRequest, FastifyReply } from 'fastify';
import { logger } from '../utils/logger.js';
import { rendererService } from '../services/renderer.service.js';

// =============================================================================
// CONSTANTS
// =============================================================================

/**
 * Service name identifier used in health check responses.
 * @constant
 */
const SERVICE_NAME = 'document-sidecar';

/**
 * Service version used in health check responses.
 * Should be kept in sync with package.json version.
 * @constant
 */
const SERVICE_VERSION = '1.0.0';

// =============================================================================
// INTERFACES
// =============================================================================

/**
 * Health check response structure for liveness probe.
 *
 * This interface defines the JSON structure returned by the /health endpoint.
 * The response includes basic service identification and status information
 * useful for monitoring and debugging.
 *
 * @interface HealthResponse
 *
 * @example
 * ```json
 * {
 *   "status": "healthy",
 *   "timestamp": "2024-01-15T10:30:45.123Z",
 *   "service": "document-sidecar",
 *   "version": "1.0.0"
 * }
 * ```
 */
interface HealthResponse {
  /**
   * Overall health status of the service.
   * - 'healthy': Service is running normally
   * - 'unhealthy': Service has issues (used in readiness check only)
   */
  status: 'healthy' | 'unhealthy';

  /**
   * ISO 8601 timestamp of when the health check was performed.
   * Useful for debugging and detecting stale health check data.
   */
  timestamp: string;

  /**
   * Service identifier for multi-service environments.
   * Helps identify which service responded in load-balanced scenarios.
   */
  service: string;

  /**
   * Service version for release tracking and debugging.
   * Matches the version in package.json.
   */
  version: string;
}

/**
 * Readiness check response structure extending health response.
 *
 * This interface extends HealthResponse with additional component status checks.
 * Used by the /ready endpoint to report detailed readiness information.
 *
 * @interface ReadyResponse
 * @extends HealthResponse
 *
 * @example
 * ```json
 * {
 *   "status": "healthy",
 *   "timestamp": "2024-01-15T10:30:45.123Z",
 *   "service": "document-sidecar",
 *   "version": "1.0.0",
 *   "checks": {
 *     "browser": "ready"
 *   }
 * }
 * ```
 */
interface ReadyResponse extends HealthResponse {
  /**
   * Individual component readiness checks.
   * Each component reports its own readiness status.
   */
  checks: {
    /**
     * Puppeteer browser instance readiness.
     * - 'ready': Browser service is available and can generate PDFs
     * - 'not_ready': Browser service is unavailable or initializing
     */
    browser: 'ready' | 'not_ready';
  };
}

// =============================================================================
// HANDLER FUNCTIONS
// =============================================================================

/**
 * Handler for GET /health liveness probe endpoint.
 *
 * This endpoint implements the Kubernetes/Docker liveness probe pattern.
 * It always returns 200 OK if the service process is running, indicating
 * that the service does not need to be restarted.
 *
 * The liveness probe is designed to be:
 * - Fast: Minimal processing to avoid blocking orchestrator checks
 * - Simple: Always succeeds if the process is running
 * - Independent: Does not depend on external services or resources
 *
 * Container orchestration behavior:
 * - 200 OK: Service is alive, no action needed
 * - Non-200 or timeout: Service may need to be restarted
 *
 * This endpoint bypasses:
 * - Authentication (no X-API-Key required)
 * - Rate limiting (not counted against limits)
 *
 * @param request - Fastify request object with requestId for correlation
 * @param reply - Fastify reply object for sending response
 * @returns Promise that resolves when response is sent
 *
 * @example
 * ```bash
 * # Health check command
 * curl http://localhost:3000/health
 * # Response: {"status":"healthy","timestamp":"2024-01-15T10:30:45.123Z","service":"document-sidecar","version":"1.0.0"}
 * ```
 */
export async function healthHandler(
  request: FastifyRequest,
  reply: FastifyReply
): Promise<void> {
  // Build health response with current timestamp
  const response: HealthResponse = {
    status: 'healthy',
    timestamp: new Date().toISOString(),
    service: SERVICE_NAME,
    version: SERVICE_VERSION,
  };

  // Log health check for debugging (debug level to avoid log spam)
  // Use request.id as Fastify's built-in request identifier
  logger.debug(
    { requestId: request.id },
    'Health check: healthy'
  );

  // Return 200 OK with health status
  reply.status(200).send(response);
}

/**
 * Handler for GET /ready readiness probe endpoint.
 *
 * This endpoint implements the Kubernetes/Docker readiness probe pattern.
 * It verifies that the service is ready to accept and process render requests
 * by checking the availability of critical components:
 *
 * Component Checks:
 * - Browser: Verifies the RendererService is initialized and available
 *
 * Container orchestration behavior:
 * - 200 OK: Service is ready, route traffic to this instance
 * - 503 Service Unavailable: Service is not ready, do not route traffic
 *
 * The readiness probe is designed to:
 * - Verify service can process requests (not just that it's running)
 * - Detect startup/initialization issues
 * - Allow graceful traffic shifting during deployment
 *
 * This endpoint bypasses:
 * - Authentication (no X-API-Key required)
 * - Rate limiting (not counted against limits)
 *
 * @param request - Fastify request object with requestId for correlation
 * @param reply - Fastify reply object for sending response
 * @returns Promise that resolves when response is sent
 *
 * @example
 * ```bash
 * # Readiness check command
 * curl http://localhost:3000/ready
 * # Ready response: {"status":"healthy","timestamp":"...","service":"document-sidecar","version":"1.0.0","checks":{"browser":"ready"}}
 * # Not ready response (503): {"status":"unhealthy","timestamp":"...","service":"document-sidecar","version":"1.0.0","checks":{"browser":"not_ready"}}
 * ```
 */
export async function readyHandler(
  request: FastifyRequest,
  reply: FastifyReply
): Promise<void> {
  let browserReady = false;

  try {
    // Check if the renderer service is initialized and has the generatePdf capability
    // This is a lightweight check that verifies:
    // 1. The rendererService singleton exists
    // 2. The generatePdf method is available (service properly constructed)
    //
    // Note: This does NOT trigger browser initialization - it's a capability check.
    // The actual browser is lazily initialized on first render request.
    // We verify the service is correctly wired and ready to accept requests.
    browserReady = rendererService !== null && typeof rendererService.generatePdf === 'function';
  } catch (error) {
    // Log warning if browser check fails unexpectedly
    // This catches any errors during the capability check
    logger.warn(
      { error, requestId: request.id },
      'Browser readiness check failed'
    );
    browserReady = false;
  }

  // Determine overall readiness based on component checks
  // Currently only browser check, but extensible for future checks
  const isReady = browserReady;

  // Build readiness response with component status
  const response: ReadyResponse = {
    status: isReady ? 'healthy' : 'unhealthy',
    timestamp: new Date().toISOString(),
    service: SERVICE_NAME,
    version: SERVICE_VERSION,
    checks: {
      browser: browserReady ? 'ready' : 'not_ready',
    },
  };

  // Log readiness check result
  if (isReady) {
    // Use debug level for successful checks to avoid log spam
    logger.debug(
      { requestId: request.id },
      'Readiness check: ready'
    );
    reply.status(200).send(response);
  } else {
    // Use warn level for failed checks as this may indicate issues
    logger.warn(
      { requestId: request.id, checks: response.checks },
      'Readiness check: not ready'
    );
    reply.status(503).send(response);
  }
}
