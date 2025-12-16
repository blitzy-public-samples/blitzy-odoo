/**
 * Base64 Encoding/Decoding Utilities
 *
 * Provides functions for converting binary data (Buffer) to and from base64-encoded strings.
 * Essential for transmitting binary PDF data over HTTP JSON responses in the document-sidecar service.
 *
 * All functions are pure and stateless, with no side effects.
 *
 * @module utils/base64
 */

/**
 * Encodes a Buffer to a base64 string.
 *
 * Used primarily for encoding PDF binary data into a format suitable for JSON serialization
 * and transmission over HTTP responses.
 *
 * @param buffer - The binary buffer to encode (typically PDF content)
 * @returns Base64-encoded string representation of the buffer
 *
 * @example
 * ```typescript
 * const pdfBuffer = await generatePdf(html);
 * const base64Pdf = encodeToBase64(pdfBuffer);
 * // Use in JSON response: { pdf_base64: base64Pdf }
 * ```
 */
export function encodeToBase64(buffer: Buffer): string {
  return buffer.toString('base64');
}

/**
 * Decodes a base64 string to a Buffer.
 *
 * Used for decoding base64-encoded binary data back to its original buffer format.
 * Useful for processing incoming base64-encoded data or for testing purposes.
 *
 * @param base64String - The base64-encoded string to decode
 * @returns Binary buffer containing the decoded data
 *
 * @example
 * ```typescript
 * const pdfBuffer = decodeFromBase64(request.pdf_base64);
 * await fs.writeFile('output.pdf', pdfBuffer);
 * ```
 */
export function decodeFromBase64(base64String: string): Buffer {
  return Buffer.from(base64String, 'base64');
}

/**
 * Validates whether a string is valid base64 encoding.
 *
 * Performs structural validation to ensure the string conforms to base64 encoding rules:
 * - Contains only valid base64 characters (A-Z, a-z, 0-9, +, /)
 * - Has proper padding with '=' characters (0, 1, or 2 at the end)
 * - Has a length that is a multiple of 4
 *
 * Note: This validates the format but does not guarantee the decoded content
 * is meaningful or represents valid PDF data.
 *
 * @param str - String to validate for base64 encoding
 * @returns True if the string is valid base64 encoding, false otherwise
 *
 * @example
 * ```typescript
 * if (!isValidBase64(input)) {
 *   throw new Error('Invalid base64 input');
 * }
 * const buffer = decodeFromBase64(input);
 * ```
 */
export function isValidBase64(str: string): boolean {
  // Empty string is technically valid base64 (represents empty data)
  if (str.length === 0) {
    return true;
  }

  // Base64 strings must have length divisible by 4
  if (str.length % 4 !== 0) {
    return false;
  }

  // Regex validates:
  // - Main body: A-Z, a-z, 0-9, +, / characters only
  // - Padding: 0, 1, or 2 '=' characters at the end
  const base64Regex = /^[A-Za-z0-9+/]*={0,2}$/;

  return base64Regex.test(str);
}

/**
 * Calculates the approximate size in bytes of the data represented by a base64 string.
 *
 * Base64 encoding increases the size by approximately 33% (4 characters encode 3 bytes).
 * This function provides an estimate useful for validation or logging purposes.
 *
 * @param base64String - The base64-encoded string
 * @returns Approximate size in bytes of the decoded data
 *
 * @example
 * ```typescript
 * const sizeBytes = getBase64DecodedSize(pdfBase64);
 * logger.info({ sizeBytes }, 'Generated PDF');
 * ```
 */
export function getBase64DecodedSize(base64String: string): number {
  if (base64String.length === 0) {
    return 0;
  }

  // Count padding characters
  let paddingCount = 0;
  if (base64String.endsWith('==')) {
    paddingCount = 2;
  } else if (base64String.endsWith('=')) {
    paddingCount = 1;
  }

  // Each 4 base64 characters represent 3 bytes
  // Subtract bytes for padding characters
  const decodedSize = (base64String.length * 3) / 4 - paddingCount;

  return decodedSize;
}
