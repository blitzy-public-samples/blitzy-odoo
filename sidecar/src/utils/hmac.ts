/**
 * HMAC-SHA256 Signature Utility Module
 *
 * Provides cryptographic functions for request signing and verification
 * in the document-sidecar service. This module implements HMAC-SHA256
 * signature generation and constant-time signature verification to ensure
 * request integrity and prevent tampering.
 *
 * Security Features:
 * - HMAC-SHA256 for cryptographic strength
 * - Constant-time comparison to prevent timing attacks
 * - Stateless design - secret key passed as parameter
 *
 * @module utils/hmac
 */

import { createHmac, timingSafeEqual } from 'crypto';

/**
 * Generates an HMAC-SHA256 signature for the given payload.
 *
 * This function creates a cryptographic signature that can be used to verify
 * the integrity of request data. The signature is computed using the shared
 * secret key, ensuring that only parties with knowledge of the secret can
 * generate valid signatures.
 *
 * @param payload - The string payload to sign (typically JSON stringified request body)
 * @param secretKey - The shared secret key for HMAC generation
 * @returns Hex-encoded HMAC-SHA256 signature (64 characters lowercase hex)
 *
 * @example
 * ```typescript
 * const payload = JSON.stringify({ report_type: 'invoice', data: {} });
 * const signature = generateSignature(payload, 'my-secret-key');
 * // signature: '3d2c4f5e6a7b8c9d...' (64 hex chars)
 * ```
 */
export function generateSignature(payload: string, secretKey: string): string {
  // Create HMAC instance with SHA-256 algorithm and the secret key
  const hmac = createHmac('sha256', secretKey);

  // Update the HMAC with the payload data
  hmac.update(payload, 'utf8');

  // Return the digest as a lowercase hexadecimal string
  return hmac.digest('hex');
}

/**
 * Verifies an HMAC-SHA256 signature using constant-time comparison
 * to prevent timing attacks.
 *
 * This function validates that a provided signature matches the expected
 * signature for the given payload. It uses Node.js's timingSafeEqual
 * function to ensure that the comparison takes the same amount of time
 * regardless of where the first difference occurs, preventing attackers
 * from using timing information to deduce valid signatures.
 *
 * @param payload - The original string payload that was signed
 * @param signature - The signature to verify (hex-encoded, case-insensitive)
 * @param secretKey - The shared secret key used for signing
 * @returns True if the signature is valid and matches the expected signature
 *
 * @example
 * ```typescript
 * const payload = JSON.stringify({ report_type: 'invoice', data: {} });
 * const signature = '3d2c4f5e6a7b8c9d...'; // from X-HMAC-Signature header
 * const isValid = verifySignature(payload, signature, 'my-secret-key');
 * if (!isValid) {
 *   throw new Error('Invalid signature - request may have been tampered with');
 * }
 * ```
 */
export function verifySignature(
  payload: string,
  signature: string,
  secretKey: string
): boolean {
  // Handle empty or invalid inputs gracefully
  if (!payload || !signature || !secretKey) {
    return false;
  }

  // Normalize signature to lowercase for consistent comparison
  const normalizedSignature = signature.toLowerCase();

  // Generate the expected signature for the payload
  const expectedSignature = generateSignature(payload, secretKey);

  // Validate signature format before buffer conversion
  // A valid hex-encoded SHA-256 signature is exactly 64 characters
  if (normalizedSignature.length !== 64 || !/^[0-9a-f]+$/.test(normalizedSignature)) {
    return false;
  }

  // Convert both signatures to buffers for timing-safe comparison
  // Using 'hex' encoding ensures proper byte-level comparison
  const sigBuffer = Buffer.from(normalizedSignature, 'hex');
  const expectedBuffer = Buffer.from(expectedSignature, 'hex');

  // Double-check buffer lengths match (they should always be 32 bytes for SHA-256)
  // This check is technically redundant given the format validation above,
  // but provides defense-in-depth against any edge cases
  if (sigBuffer.length !== expectedBuffer.length) {
    return false;
  }

  // Perform constant-time comparison to prevent timing attacks
  // timingSafeEqual ensures the comparison takes the same time
  // regardless of where the first difference occurs
  return timingSafeEqual(sigBuffer, expectedBuffer);
}
