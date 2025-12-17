/**
 * Environment variable configuration module for the document-sidecar service.
 * 
 * Centralizes all configuration values with sensible defaults including server port,
 * API authentication key, HMAC signing secret, log level, rate limiting parameters,
 * and environment mode. Uses typed configuration object for type-safe access
 * throughout the application.
 * 
 * Configuration is read from environment variables at module load time.
 * Required variables (API_KEY, SECRET_KEY) must be validated before server startup.
 * 
 * @module config
 */

/**
 * Configuration interface defining all environment-based settings for the sidecar service.
 * 
 * @interface Config
 * @property {number} port - HTTP server port (default: 3000)
 * @property {string} apiKey - API authentication key for X-API-Key header validation
 * @property {string} secretKey - HMAC signing secret for request signature verification
 * @property {string} logLevel - Logging verbosity level (trace/debug/info/warn/error)
 * @property {string} nodeEnv - Environment mode (development/production/test)
 * @property {number} rateLimitMax - Maximum requests allowed per rate limit window
 * @property {number} rateLimitWindow - Rate limit time window in milliseconds
 */
export interface Config {
  /** HTTP server port for Fastify to bind to */
  port: number;
  
  /** API authentication key used for X-API-Key header validation */
  apiKey: string;
  
  /** HMAC signing secret used for request signature verification (X-HMAC-Signature) */
  secretKey: string;
  
  /** Logging verbosity level: trace, debug, info, warn, error, or fatal */
  logLevel: string;
  
  /** Environment mode: development, production, or test */
  nodeEnv: string;
  
  /** Maximum number of requests allowed per rate limit window */
  rateLimitMax: number;
  
  /** Rate limit time window in milliseconds */
  rateLimitWindow: number;
}

/**
 * Application configuration object populated from environment variables.
 * 
 * Environment Variables:
 * - PORT: HTTP server port (default: 3000)
 * - API_KEY: API authentication key (required in production)
 * - SECRET_KEY: HMAC signing secret (required in production)
 * - LOG_LEVEL: Logging verbosity (default: 'info')
 * - NODE_ENV: Environment mode (default: 'development')
 * - RATE_LIMIT_MAX: Max requests per window (default: 100)
 * - RATE_LIMIT_WINDOW: Rate limit window in ms (default: 60000)
 * 
 * @constant
 * @type {Config}
 * 
 * @example
 * ```typescript
 * import { config } from './config.js';
 * 
 * // Access configuration values
 * console.log(`Server will start on port ${config.port}`);
 * console.log(`Rate limit: ${config.rateLimitMax} requests per ${config.rateLimitWindow}ms`);
 * ```
 */
export const config: Config = {
  // HTTP server port - defaults to 3000 for local development
  port: parseInt(process.env.PORT || '3000', 10),
  
  // API key for authentication - empty string as default, validation enforces presence
  apiKey: process.env.API_KEY || '',
  
  // Secret key for HMAC signature verification - empty string as default, validation enforces presence
  secretKey: process.env.SECRET_KEY || '',
  
  // Logging level - defaults to 'info' for production-appropriate verbosity
  logLevel: process.env.LOG_LEVEL || 'info',
  
  // Environment mode - defaults to 'development' for safety
  nodeEnv: process.env.NODE_ENV || 'development',
  
  // Rate limit ceiling - defaults to 100 requests per window
  rateLimitMax: parseInt(process.env.RATE_LIMIT_MAX || '100', 10),
  
  // Rate limit window - defaults to 60000ms (1 minute)
  rateLimitWindow: parseInt(process.env.RATE_LIMIT_WINDOW || '60000', 10),
};

/**
 * Validates that all required configuration values are present.
 * 
 * This function should be called before server startup to ensure the service
 * is properly configured. It throws descriptive errors for missing required values.
 * 
 * Required configuration:
 * - API_KEY: Must be set for request authentication
 * - SECRET_KEY: Must be set for HMAC signature verification
 * 
 * Additionally validates:
 * - PORT must be a valid number between 1 and 65535
 * - RATE_LIMIT_MAX must be a positive number
 * - RATE_LIMIT_WINDOW must be a positive number
 * 
 * @throws {Error} If API_KEY environment variable is not set or empty
 * @throws {Error} If SECRET_KEY environment variable is not set or empty
 * @throws {Error} If PORT is not a valid port number (1-65535)
 * @throws {Error} If RATE_LIMIT_MAX is not a positive number
 * @throws {Error} If RATE_LIMIT_WINDOW is not a positive number
 * 
 * @example
 * ```typescript
 * import { validateConfig } from './config.js';
 * 
 * try {
 *   validateConfig();
 *   // Configuration is valid, proceed with server startup
 * } catch (error) {
 *   console.error('Configuration error:', error.message);
 *   process.exit(1);
 * }
 * ```
 */
export function validateConfig(): void {
  // Validate required API_KEY for request authentication
  if (!config.apiKey) {
    throw new Error('API_KEY environment variable is required');
  }
  
  // Validate required SECRET_KEY for HMAC signature verification
  if (!config.secretKey) {
    throw new Error('SECRET_KEY environment variable is required');
  }
  
  // Validate port is within valid range (1-65535)
  if (isNaN(config.port) || config.port < 1 || config.port > 65535) {
    throw new Error('PORT must be a valid port number between 1 and 65535');
  }
  
  // Validate rate limit max is a positive number
  if (isNaN(config.rateLimitMax) || config.rateLimitMax <= 0) {
    throw new Error('RATE_LIMIT_MAX must be a positive number');
  }
  
  // Validate rate limit window is a positive number
  if (isNaN(config.rateLimitWindow) || config.rateLimitWindow <= 0) {
    throw new Error('RATE_LIMIT_WINDOW must be a positive number in milliseconds');
  }
}
