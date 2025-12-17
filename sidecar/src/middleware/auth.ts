/**
 * @fileoverview Authentication middleware for the document-sidecar Fastify service.
 *
 * Implements API key validation via X-API-Key header and HMAC-SHA256 signature
 * verification via X-HMAC-Signature header. Uses constant-time comparison to
 * prevent timing attacks. Returns HTTP 401 AUTH_FAILED error on invalid or
 * missing credentials.
 *
 * Security Features:
 * - API key validation ensures client identity
 * - HMAC-SHA256 signature ensures request integrity (prevents tampering)
 * - Constant-time comparison prevents timing attacks
 * - Health/ready endpoints are excluded from authentication
 *
 * Authentication Flow:
 * 1. Extract X-API-Key header and validate against configured API_KEY
 * 2. For POST/PUT/PATCH requests, extract X-HMAC-Signature header
 * 3. Verify HMAC-SHA256 signature of request body using SECRET_KEY
 * 4. On failure, throw AppError with AUTH_FAILED code (HTTP 401)
 *
 * @module middleware/auth
 */

import type { FastifyRequest, FastifyReply, preHandlerAsyncHookHandler } from 'fastify';
import { config } from '../config.js';
import { verifySignature } from '../utils/hmac.js';
import { logger } from '../utils/logger.js';
import { AppError } from './error-handler.js';

// =============================================================================
// CONSTANTS
// =============================================================================

/**
 * HTTP header name for API key authentication.
 * Clients must include this header with their API key to authenticate requests.
 *
 * @constant {string}
 * @example
 * ```
 * X-API-Key: your-api-key-here
 * ```
 */
export const API_KEY_HEADER = 'x-api-key';

/**
 * HTTP header name for HMAC-SHA256 signature verification.
 * Clients must include this header with the HMAC signature of the request body
 * for POST/PUT/PATCH requests to ensure request integrity.
 *
 * @constant {string}
 * @example
 * ```
 * X-HMAC-Signature: a1b2c3d4e5f6...
 * ```
 */
export const HMAC_SIGNATURE_HEADER = 'x-hmac-signature';

/**
 * Routes that should skip authentication (health endpoints).
 * These endpoints must remain accessible without credentials for
 * container orchestration health checks and load balancer probes.
 *
 * @constant {string[]}
 */
const SKIP_AUTH_ROUTES: string[] = ['/health', '/ready'];

// =============================================================================
// TYPE DECLARATIONS
// =============================================================================

/**
 * Declaration merging to extend FastifyRequest with authentication state.
 * Allows downstream handlers to check if the request was authenticated.
 */
declare module 'fastify' {
  interface FastifyRequest {
    /**
     * Indicates whether the request passed authentication.
     * True if API key and HMAC signature (when applicable) were valid.
     * False for unauthenticated routes (health endpoints).
     */
    authenticated: boolean;
  }
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Validates the API key from request headers using constant-time comparison.
 *
 * Uses a character-by-character XOR comparison to ensure the validation
 * takes constant time regardless of where the first mismatch occurs,
 * preventing timing attacks that could reveal valid API key prefixes.
 *
 * @param apiKey - The API key extracted from the X-API-Key header
 * @returns True if the API key matches the configured API_KEY, false otherwise
 *
 * @example
 * ```typescript
 * const apiKey = request.headers['x-api-key'] as string;
 * if (!validateApiKey(apiKey)) {
 *   throw new AppError('AUTH_FAILED', 'Invalid or missing API key');
 * }
 * ```
 */
function validateApiKey(apiKey: string | undefined): boolean {
  // Reject if API key is missing from request or not configured
  if (!apiKey || !config.apiKey) {
    return false;
  }

  // Length check before constant-time comparison
  // This early return is safe as it doesn't reveal information about the actual key
  if (apiKey.length !== config.apiKey.length) {
    return false;
  }

  // Constant-time comparison using XOR
  // Accumulates differences without short-circuiting to prevent timing attacks
  let result = 0;
  for (let i = 0; i < apiKey.length; i++) {
    result |= apiKey.charCodeAt(i) ^ config.apiKey.charCodeAt(i);
  }

  // Result is 0 only if all characters matched
  return result === 0;
}

/**
 * Validates the HMAC signature of the request body.
 *
 * Delegates to the hmac utility's verifySignature function which uses
 * Node.js's timingSafeEqual for constant-time comparison to prevent
 * timing attacks.
 *
 * @param signature - The HMAC signature from the X-HMAC-Signature header
 * @param body - The raw request body string (JSON stringified)
 * @returns True if the signature is valid, false otherwise
 *
 * @example
 * ```typescript
 * const signature = request.headers['x-hmac-signature'] as string;
 * const rawBody = JSON.stringify(request.body);
 * if (!validateHmacSignature(signature, rawBody)) {
 *   throw new AppError('AUTH_FAILED', 'Invalid HMAC signature');
 * }
 * ```
 */
function validateHmacSignature(signature: string | undefined, body: string): boolean {
  // Reject if signature is missing from request or secret key not configured
  if (!signature || !config.secretKey) {
    return false;
  }

  // Delegate to hmac utility for constant-time signature verification
  return verifySignature(body, signature, config.secretKey);
}

// =============================================================================
// MIDDLEWARE FUNCTIONS
// =============================================================================

/**
 * Checks if a route should skip authentication.
 *
 * Health check endpoints (/health, /ready) must be accessible without
 * authentication to support container orchestration health probes and
 * load balancer checks.
 *
 * @param url - The request URL path to check
 * @returns True if authentication should be skipped for this route
 *
 * @example
 * ```typescript
 * if (shouldSkipAuth(request.url)) {
 *   // Skip authentication for health endpoints
 *   return;
 * }
 * ```
 */
export function shouldSkipAuth(url: string): boolean {
  return SKIP_AUTH_ROUTES.some((route) => url.startsWith(route));
}

/**
 * Core authentication logic that performs API key and HMAC validation.
 *
 * This internal function encapsulates the authentication process and is
 * called by both authMiddleware and conditionalAuthMiddleware.
 *
 * @param request - Fastify request object with headers, body, and metadata
 * @throws {AppError} With AUTH_FAILED code on authentication failure
 * @internal
 */
async function performAuthentication(request: FastifyRequest): Promise<void> {
  // Get request ID for correlation in logs
  // requestId is typically set by the request-id middleware
  const requestId = (request.id ?? request.headers['x-request-id'] ?? 'unknown') as string;

  // Extract authentication headers (case-insensitive access)
  const apiKey = request.headers[API_KEY_HEADER] as string | undefined;
  const hmacSignature = request.headers[HMAC_SIGNATURE_HEADER] as string | undefined;

  // Log authentication attempt without exposing sensitive data
  logger.debug(
    {
      requestId,
      hasApiKey: !!apiKey,
      hasSignature: !!hmacSignature,
      method: request.method,
      url: request.url,
    },
    'Authentication attempt'
  );

  // Step 1: Validate API key using constant-time comparison
  if (!validateApiKey(apiKey)) {
    logger.warn(
      {
        requestId,
        url: request.url,
      },
      'Invalid or missing API key'
    );
    throw new AppError('AUTH_FAILED', 'Invalid or missing API key');
  }

  // Step 2: Validate HMAC signature for requests with body content
  // Only POST, PUT, and PATCH requests typically have request bodies
  const method = request.method.toUpperCase();
  if (['POST', 'PUT', 'PATCH'].includes(method)) {
    // Get raw body as string for signature verification
    // Fastify parses JSON body automatically, so we need to re-stringify
    const rawBody = JSON.stringify(request.body);

    if (!validateHmacSignature(hmacSignature, rawBody)) {
      logger.warn(
        {
          requestId,
          url: request.url,
        },
        'Invalid HMAC signature'
      );
      throw new AppError('AUTH_FAILED', 'Invalid HMAC signature');
    }
  }

  // Mark request as authenticated for downstream handlers
  request.authenticated = true;

  logger.debug(
    {
      requestId,
    },
    'Authentication successful'
  );
}

/**
 * Fastify preHandler hook that validates authentication for protected routes.
 *
 * Authentication is performed in two stages:
 * 1. API Key Validation: Checks X-API-Key header against configured API_KEY
 * 2. HMAC Signature Validation: For POST/PUT/PATCH requests, verifies
 *    X-HMAC-Signature header using HMAC-SHA256 of the request body with
 *    the configured SECRET_KEY
 *
 * Both validations must pass for the request to proceed. On failure,
 * throws AppError with AUTH_FAILED code resulting in HTTP 401 response.
 *
 * Uses constant-time comparison to prevent timing attacks that could
 * reveal information about valid API keys or signatures.
 *
 * @param request - Fastify request object with headers, body, and metadata
 * @param _reply - Fastify reply object (unused but required by hook signature)
 * @throws {AppError} With AUTH_FAILED code on authentication failure
 *
 * @example
 * ```typescript
 * // Register as global preHandler hook
 * app.addHook('preHandler', authMiddleware);
 *
 * // Or apply to specific routes
 * app.post('/api/v1/render', { preHandler: authMiddleware }, renderHandler);
 * ```
 */
export const authMiddleware: preHandlerAsyncHookHandler = async (
  request: FastifyRequest,
  _reply: FastifyReply
): Promise<void> => {
  await performAuthentication(request);
};

/**
 * Conditional authentication middleware that skips health check endpoints.
 *
 * This wrapper middleware checks if the current route should skip
 * authentication before delegating to the main authMiddleware.
 * Health endpoints (/health, /ready) are excluded to allow container
 * orchestration probes and load balancer health checks without credentials.
 *
 * Routes that skip authentication will have request.authenticated set to false.
 *
 * @param request - Fastify request object
 * @param reply - Fastify reply object
 * @throws {AppError} With AUTH_FAILED code on authentication failure (for protected routes)
 *
 * @example
 * ```typescript
 * // Register as global preHandler hook with automatic skip for health endpoints
 * app.addHook('preHandler', conditionalAuthMiddleware);
 *
 * // Health endpoints (/health, /ready) will be accessible without auth
 * // All other routes require valid API key and HMAC signature
 * ```
 */
export const conditionalAuthMiddleware: preHandlerAsyncHookHandler = async (
  request: FastifyRequest,
  _reply: FastifyReply
): Promise<void> => {
  // Check if this route should skip authentication
  if (shouldSkipAuth(request.url)) {
    // Mark as unauthenticated for tracking purposes
    request.authenticated = false;

    logger.debug(
      {
        requestId: (request.id ?? 'unknown') as string,
        url: request.url,
      },
      'Skipping authentication for health endpoint'
    );

    return;
  }

  // Delegate to core authentication logic for protected routes
  await performAuthentication(request);
};
