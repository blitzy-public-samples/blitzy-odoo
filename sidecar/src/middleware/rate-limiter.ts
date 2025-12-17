/**
 * @fileoverview Rate limiting middleware configuration for the document-sidecar Fastify service.
 *
 * This module configures request rate limiting using the @fastify/rate-limit plugin
 * to protect the sidecar service from overwhelming concurrent requests. Rate limits
 * are configurable via environment variables:
 * - RATE_LIMIT_MAX: Maximum requests per window (default: 100)
 * - RATE_LIMIT_WINDOW: Time window in milliseconds (default: 60000ms / 1 minute)
 *
 * When rate limits are exceeded, the middleware returns an HTTP 429 response with
 * a standardized RATE_LIMITED error code and includes retry-after headers.
 *
 * Key features:
 * - API key-based rate limiting (falls back to IP if no API key present)
 * - Configurable limits via environment variables
 * - Structured logging for rate limit events
 * - Standardized error responses consistent with the API contract
 * - Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
 *
 * @module middleware/rate-limiter
 */

import type { FastifyInstance, FastifyRequest } from 'fastify';
import rateLimit from '@fastify/rate-limit';
import { config } from '../config.js';
import { logger } from '../utils/logger.js';
import { AppError } from './error-handler.js';

// =============================================================================
// TYPE DEFINITIONS
// =============================================================================

/**
 * Rate limit configuration options.
 *
 * Defines the parameters for configuring the @fastify/rate-limit plugin.
 * These values can be customized per-environment via the Config module
 * or overridden when registering the rate limiter.
 *
 * @interface RateLimitConfig
 * @property {number} max - Maximum number of requests allowed within the time window
 * @property {number} timeWindow - Duration of the time window in milliseconds
 *
 * @example
 * ```typescript
 * const customConfig: RateLimitConfig = {
 *   max: 50,           // 50 requests
 *   timeWindow: 30000, // per 30 seconds
 * };
 * ```
 */
export interface RateLimitConfig {
  /**
   * Maximum number of requests allowed per time window.
   * When this limit is exceeded, requests will receive HTTP 429 responses.
   * Default: 100 (from RATE_LIMIT_MAX environment variable)
   */
  max: number;

  /**
   * Time window duration in milliseconds.
   * After this window expires, the request count resets.
   * Default: 60000 (1 minute, from RATE_LIMIT_WINDOW environment variable)
   */
  timeWindow: number;
}

/**
 * Rate limit context provided by @fastify/rate-limit in error callbacks.
 * This interface represents the shape of the context object passed to
 * the errorResponseBuilder callback as per @fastify/rate-limit types.
 * 
 * @see https://github.com/fastify/fastify-rate-limit#error-response-builder
 */
interface RateLimitContext {
  /** Whether the client is banned (exceeded ban threshold) */
  ban: boolean;
  /** Time until the rate limit resets (human-readable string like "1 second") */
  after: string;
  /** Maximum requests allowed per window */
  max: number;
  /** Time to live in milliseconds until reset */
  ttl: number;
}

// =============================================================================
// CONFIGURATION HELPERS
// =============================================================================

/**
 * Gets the default rate limit configuration from environment variables.
 *
 * Retrieves rate limiting parameters from the centralized config module,
 * which reads from environment variables (RATE_LIMIT_MAX, RATE_LIMIT_WINDOW).
 *
 * Default values (as defined in config.ts):
 * - max: 100 requests per window
 * - timeWindow: 60000ms (1 minute)
 *
 * @returns {RateLimitConfig} Rate limit configuration object with max and timeWindow
 *
 * @example
 * ```typescript
 * import { getDefaultRateLimitConfig } from './middleware/rate-limiter.js';
 *
 * const config = getDefaultRateLimitConfig();
 * console.log(`Rate limit: ${config.max} requests per ${config.timeWindow}ms`);
 * // Output: "Rate limit: 100 requests per 60000ms"
 * ```
 */
export function getDefaultRateLimitConfig(): RateLimitConfig {
  return {
    max: config.rateLimitMax,
    timeWindow: config.rateLimitWindow,
  };
}

// =============================================================================
// RATE LIMITER REGISTRATION
// =============================================================================

/**
 * Registers the @fastify/rate-limit plugin with the Fastify instance.
 *
 * This function configures comprehensive rate limiting for the sidecar service
 * to protect against overwhelming concurrent requests. The rate limiter is
 * configured with the following features:
 *
 * **Rate Limiting Strategy:**
 * - Uses API key (X-API-Key header) as the primary identifier
 * - Falls back to client IP address if no API key is present
 * - This ensures per-client rate limiting rather than global limiting
 *
 * **Error Handling:**
 * - Returns standardized RATE_LIMITED error response (HTTP 429)
 * - Includes retry information in response body and headers
 * - Logs warnings with full context for monitoring
 *
 * **Response Headers:**
 * - X-RateLimit-Limit: Maximum requests allowed per window
 * - X-RateLimit-Remaining: Requests remaining in current window
 * - X-RateLimit-Reset: Timestamp when the rate limit resets
 * - Retry-After: Seconds until the client can retry
 *
 * @param app - The Fastify instance to register the plugin with
 * @param customConfig - Optional custom rate limit configuration to override defaults
 * @returns Promise that resolves when the plugin is registered
 *
 * @example
 * ```typescript
 * import Fastify from 'fastify';
 * import { registerRateLimiter } from './middleware/rate-limiter.js';
 *
 * const app = Fastify();
 *
 * // Register with default configuration
 * await registerRateLimiter(app);
 *
 * // Or with custom configuration
 * await registerRateLimiter(app, {
 *   max: 50,           // Override max requests
 *   timeWindow: 30000, // Override time window
 * });
 * ```
 *
 * @example
 * ```typescript
 * // Rate limited response format (HTTP 429):
 * {
 *   "success": false,
 *   "error": {
 *     "code": "RATE_LIMITED",
 *     "message": "Rate limit exceeded. Maximum 100 requests per 60000ms. Try again later.",
 *     "details": {
 *       "limit": 100,
 *       "remaining": 0,
 *       "reset": "1 second"
 *     },
 *     "request_id": "550e8400-e29b-41d4-a716-446655440000"
 *   }
 * }
 * ```
 */
export async function registerRateLimiter(
  app: FastifyInstance,
  customConfig?: Partial<RateLimitConfig>
): Promise<void> {
  // Merge default configuration with any custom overrides
  const rateLimitConfig: RateLimitConfig = {
    ...getDefaultRateLimitConfig(),
    ...customConfig,
  };

  // Register the @fastify/rate-limit plugin with full configuration
  await app.register(rateLimit, {
    // Maximum requests allowed per time window
    max: rateLimitConfig.max,

    // Duration of the time window in milliseconds
    timeWindow: rateLimitConfig.timeWindow,

    /**
     * Key generator function for identifying rate-limited clients.
     *
     * Uses the API key from X-API-Key header as the primary identifier,
     * falling back to the client's IP address if no API key is present.
     * This allows per-API-key rate limiting which is more appropriate
     * for our authentication model.
     *
     * @param request - The incoming Fastify request
     * @returns Unique identifier string for rate limiting
     */
    keyGenerator: (request: FastifyRequest): string => {
      // Use API key if present in headers (case-insensitive header access)
      const apiKey = request.headers['x-api-key'];
      if (typeof apiKey === 'string' && apiKey.length > 0) {
        return apiKey;
      }
      // Fall back to client IP address for requests without API key
      return request.ip;
    },

    /**
     * Custom error response builder for rate limit exceeded scenarios.
     *
     * Generates an AppError with RATE_LIMITED code that the central error
     * handler (error-handler.ts) will process into a standardized response.
     * Also logs a warning with full context for monitoring and alerting.
     *
     * IMPORTANT: @fastify/rate-limit throws the return value of this function.
     * We throw an AppError which the error handler recognizes and processes
     * into the appropriate HTTP 429 response with structured error body.
     *
     * @param request - The rate-limited request
     * @param context - Rate limit context with limit, remaining, and reset info
     * @returns AppError with RATE_LIMITED code and details
     */
    errorResponseBuilder: (
      request: FastifyRequest,
      context: RateLimitContext
    ) => {
      // Extract request ID for correlation (may be undefined if request-id middleware hasn't run)
      const requestId = (request as FastifyRequest & { requestId?: string }).requestId;

      // Log warning with full context for monitoring
      logger.warn(
        {
          requestId,
          ip: request.ip,
          limit: context.max,
          resetAfter: context.after,
          ttl: context.ttl,
          banned: context.ban,
          apiKeyPresent: Boolean(request.headers['x-api-key']),
        },
        'Rate limit exceeded'
      );

      // Create an AppError that the central error handler will process
      // The error handler maps RATE_LIMITED to HTTP 429 and includes details
      return new AppError(
        'RATE_LIMITED',
        `Rate limit exceeded. Maximum ${context.max} requests per ${rateLimitConfig.timeWindow}ms. Try again later.`,
        {
          limit: context.max,
          reset: context.after,
          ttl: context.ttl,
          banned: context.ban,
        }
      );
    },

    /**
     * Configure rate limit headers to be included in responses.
     *
     * These headers help clients understand their rate limit status
     * and implement appropriate retry logic.
     */
    addHeaders: {
      // X-RateLimit-Limit: Maximum requests per window
      'x-ratelimit-limit': true,
      // X-RateLimit-Remaining: Requests remaining in current window
      'x-ratelimit-remaining': true,
      // X-RateLimit-Reset: Timestamp when the window resets
      'x-ratelimit-reset': true,
      // Retry-After: Seconds until client can retry (only on 429)
      'retry-after': true,
    },
  });

  // Log successful registration with configuration details
  logger.info(
    {
      max: rateLimitConfig.max,
      timeWindow: rateLimitConfig.timeWindow,
      timeWindowSeconds: Math.round(rateLimitConfig.timeWindow / 1000),
    },
    'Rate limiter registered'
  );
}
