/**
 * @fileoverview Fastify server entry point for the document-sidecar TypeScript service.
 *
 * This is the main entry point for the document-sidecar service, a standalone
 * TypeScript service that generates PDF documents (invoices, quotes, delivery slips)
 * from JSON data using Handlebars templates and Puppeteer headless Chrome.
 *
 * The server provides:
 * - High-performance HTTP API via Fastify 4.x
 * - Rate limiting to prevent request flooding
 * - Request correlation via X-Request-ID headers for distributed tracing
 * - Structured JSON logging via Pino
 * - Graceful shutdown handling for container orchestration
 * - Consistent error response formatting
 *
 * Architecture Flow:
 * 1. Configuration validation (API_KEY, SECRET_KEY required)
 * 2. Fastify instance creation with logger and request ID configuration
 * 3. Plugin registration (rate limiting)
 * 4. Middleware setup (request ID injection, error handling)
 * 5. Route registration (health, ready, render endpoints)
 * 6. Server startup with graceful shutdown signal handlers
 *
 * @module index
 * @see Agent Action Plan Sections 0.3.2, 0.5.1
 */

import Fastify from 'fastify';
import type { IncomingMessage } from 'http';
import rateLimit from '@fastify/rate-limit';
import { randomUUID } from 'crypto';

// Internal imports from dependency files
import { config, validateConfig } from './config.js';
import { registerRoutes } from './api/routes.js';
import { registerErrorHandler } from './middleware/error-handler.js';
import { requestIdMiddleware } from './middleware/request-id.js';
import { logger } from './utils/logger.js';

// =============================================================================
// CONFIGURATION VALIDATION
// =============================================================================

/**
 * Validate configuration before server startup.
 *
 * This ensures all required environment variables are set and valid.
 * Fails fast with descriptive error messages if configuration is invalid.
 *
 * Required configuration:
 * - API_KEY: For request authentication
 * - SECRET_KEY: For HMAC signature verification
 * - PORT: Valid port number (1-65535)
 * - RATE_LIMIT_MAX: Positive number
 * - RATE_LIMIT_WINDOW: Positive number (milliseconds)
 */
try {
  validateConfig();
  logger.info(
    {
      port: config.port,
      rateLimitMax: config.rateLimitMax,
      rateLimitWindow: config.rateLimitWindow,
      logLevel: config.logLevel,
      nodeEnv: config.nodeEnv,
    },
    'Configuration validated successfully'
  );
} catch (error) {
  logger.error({ err: error }, 'Configuration validation failed');
  process.exit(1);
}

// =============================================================================
// FASTIFY INSTANCE CREATION
// =============================================================================

/**
 * Fastify application instance.
 *
 * Configured with:
 * - Pino logger for structured JSON logging
 * - Request ID header extraction/generation for distributed tracing
 * - Custom request ID generator using crypto.randomUUID
 *
 * The instance is exported for testing purposes, allowing injection
 * and mocking in unit/integration tests.
 *
 * @constant
 * @exports app
 */
export const app = Fastify({
  // Use pre-configured Pino logger for structured logging
  // This integrates Fastify's internal logging with our application logger
  logger: logger,

  // Header name to extract existing request ID from incoming requests
  // Standard convention for correlation ID propagation
  requestIdHeader: 'x-request-id',

  // Custom request ID generator function
  // Uses existing X-Request-ID header if present and non-empty,
  // otherwise generates a new RFC 4122 UUID v4
  // Note: genReqId receives the raw IncomingMessage, not FastifyRequest
  genReqId: (req: IncomingMessage): string => {
    const existingId = req.headers['x-request-id'];
    if (typeof existingId === 'string' && existingId.length > 0) {
      return existingId;
    }
    return randomUUID();
  },
});

// =============================================================================
// PLUGIN REGISTRATION
// =============================================================================

/**
 * Registers all Fastify plugins required by the application.
 *
 * Plugin registration is performed asynchronously in sequence.
 * Plugins are loaded in dependency order to ensure proper initialization.
 *
 * Registered Plugins:
 * - @fastify/rate-limit: Request rate limiting (100 req/min default)
 *
 * @async
 * @returns Promise that resolves when all plugins are registered
 */
async function registerPlugins(): Promise<void> {
  // Rate Limiting Plugin
  // Protects the sidecar from overwhelming concurrent requests
  // Configuration is loaded from environment variables via config module
  await app.register(rateLimit, {
    // Maximum number of requests allowed per time window
    max: config.rateLimitMax,

    // Time window duration in milliseconds
    timeWindow: config.rateLimitWindow,

    // Custom error response format for rate limit exceeded
    errorResponseBuilder: (_request, context) => ({
      error: {
        code: 'RATE_LIMITED',
        message: `Rate limit exceeded. Maximum ${context.max} requests per ${context.after}. Please retry after the time window.`,
      },
    }),
  });

  logger.info(
    {
      maxRequests: config.rateLimitMax,
      timeWindow: config.rateLimitWindow,
    },
    'Rate limiter plugin registered'
  );
}

// =============================================================================
// MIDDLEWARE REGISTRATION
// =============================================================================

/**
 * Registers middleware hooks with the Fastify instance.
 *
 * Middleware is registered as Fastify hooks that execute in order:
 * 1. onRequest: Request ID injection/extraction
 *
 * Additional middleware (error handler) is registered separately
 * using Fastify's setErrorHandler method.
 */
function registerMiddleware(): void {
  // Request ID Middleware
  // Extracts X-Request-ID from incoming requests or generates new UUID
  // Attaches request ID to request object and response headers
  // Enables distributed tracing across Odoo → Sidecar communication
  app.addHook('onRequest', requestIdMiddleware);

  logger.info('Request ID middleware registered');

  // Error Handler
  // Catches all unhandled errors and formats them into consistent
  // ErrorResponse structures with appropriate HTTP status codes
  // Maps error types to status codes per Agent Action Plan Section 0.8.6
  registerErrorHandler(app);

  logger.info('Error handler registered');
}

// =============================================================================
// GRACEFUL SHUTDOWN HANDLING
// =============================================================================

/**
 * Flag to prevent multiple shutdown attempts.
 * Ensures graceful shutdown logic runs only once.
 */
let isShuttingDown = false;

/**
 * Handles graceful shutdown when receiving termination signals.
 *
 * This function ensures:
 * 1. Logs the received signal for operational visibility
 * 2. Prevents multiple simultaneous shutdown attempts
 * 3. Closes Fastify server gracefully (completes in-flight requests)
 * 4. Allows ongoing PDF generations to complete
 * 5. Exits process with success code (0)
 *
 * The graceful shutdown is critical for:
 * - Container orchestration (Kubernetes, Docker) health checks
 * - Completing in-flight PDF generations before container termination
 * - Proper resource cleanup (browser instances, file handles)
 *
 * @param signal - The signal name that triggered shutdown (SIGTERM, SIGINT)
 * @async
 */
async function shutdown(signal: string): Promise<void> {
  // Prevent multiple shutdown attempts
  if (isShuttingDown) {
    logger.warn({ signal }, 'Shutdown already in progress, ignoring signal');
    return;
  }

  isShuttingDown = true;

  logger.info({ signal }, 'Received shutdown signal, initiating graceful shutdown');

  try {
    // Close Fastify server gracefully
    // This will:
    // - Stop accepting new connections
    // - Wait for existing requests to complete (with default timeout)
    // - Close all plugins and decorators
    await app.close();

    logger.info('Graceful shutdown completed successfully');
    process.exit(0);
  } catch (error) {
    logger.error({ err: error }, 'Error during graceful shutdown');
    process.exit(1);
  }
}

// Register signal handlers for graceful shutdown
// SIGTERM: Sent by container orchestrators (Kubernetes, Docker) for graceful termination
process.on('SIGTERM', () => {
  void shutdown('SIGTERM');
});

// SIGINT: Sent when pressing Ctrl+C in terminal (development use)
process.on('SIGINT', () => {
  void shutdown('SIGINT');
});

// Handle uncaught exceptions
// Log the error and exit to prevent undefined state
process.on('uncaughtException', (error: Error) => {
  logger.fatal({ err: error }, 'Uncaught exception, shutting down');
  process.exit(1);
});

// Handle unhandled promise rejections
// Log the error and exit to prevent undefined state
process.on('unhandledRejection', (reason: unknown) => {
  logger.fatal({ reason }, 'Unhandled promise rejection, shutting down');
  process.exit(1);
});

// =============================================================================
// SERVER STARTUP
// =============================================================================

/**
 * Initializes and starts the Fastify HTTP server.
 *
 * Startup sequence:
 * 1. Register all plugins (rate limiting)
 * 2. Register middleware (request ID, error handler)
 * 3. Register API routes (health, ready, render)
 * 4. Bind server to configured port on all interfaces (0.0.0.0)
 * 5. Log successful startup with server details
 *
 * Error Handling:
 * - Plugin registration failures are logged and cause process exit
 * - Port binding failures are logged and cause process exit
 * - All errors include contextual information for debugging
 *
 * @async
 */
async function start(): Promise<void> {
  try {
    // Step 1: Register plugins (rate limiting)
    await registerPlugins();

    // Step 2: Register middleware (request ID, error handler)
    registerMiddleware();

    // Step 3: Register API routes
    // This registers:
    // - GET /health - Liveness probe
    // - GET /ready - Readiness probe
    // - POST /api/v1/render - PDF generation endpoint
    await app.register(registerRoutes);

    logger.info('API routes registered');

    // Step 4: Start server on configured port
    // Binding to 0.0.0.0 allows connections from any network interface
    // This is required for Docker container networking
    await app.listen({
      port: config.port,
      host: '0.0.0.0',
    });

    // Step 5: Log successful startup
    logger.info(
      {
        port: config.port,
        host: '0.0.0.0',
        environment: config.nodeEnv,
        rateLimitMax: config.rateLimitMax,
        rateLimitWindow: config.rateLimitWindow,
      },
      `Document sidecar server started on port ${config.port}`
    );
  } catch (error) {
    // Log startup error with full context
    logger.error(
      {
        err: error,
        port: config.port,
      },
      'Failed to start server'
    );

    // Exit with error code to signal failure to container orchestrator
    process.exit(1);
  }
}

// Start the server
// Using void to explicitly ignore the promise (IIFE pattern)
// The promise rejection is handled internally via try/catch
void start();
