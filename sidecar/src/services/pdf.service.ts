/**
 * PDF Utility Service for the document-sidecar service.
 *
 * Provides stateless utility functions for PDF document manipulation using the pdf-lib library:
 * - Extract page count from PDF buffers
 * - Read PDF metadata (title, author, creation date, etc.)
 * - Validate PDF buffer integrity
 * - Calculate and format PDF file sizes
 *
 * Used by the render handler to include page count in API responses.
 * All functions operate on raw PDF buffers without external dependencies beyond pdf-lib.
 *
 * @module pdf.service
 */

import { PDFDocument } from 'pdf-lib';
import { logger } from '../utils/logger.js';

/**
 * Metadata extracted from a PDF document.
 *
 * Contains structural and descriptive information about a PDF file,
 * including page count and optional document properties.
 *
 * @interface PdfMetadata
 */
export interface PdfMetadata {
  /**
   * Total number of pages in the PDF document.
   * Always present and >= 1 for valid PDFs.
   */
  pageCount: number;

  /**
   * Document title from PDF metadata.
   * May be undefined if not set in the document.
   */
  title?: string;

  /**
   * Document author from PDF metadata.
   * May be undefined if not set in the document.
   */
  author?: string;

  /**
   * Document subject/description from PDF metadata.
   * May be undefined if not set in the document.
   */
  subject?: string;

  /**
   * Application that created the original document.
   * May be undefined if not set in the document.
   */
  creator?: string;

  /**
   * Application that produced the PDF file.
   * May be undefined if not set in the document.
   */
  producer?: string;

  /**
   * Date when the document was originally created.
   * May be undefined if not set in the document.
   */
  creationDate?: Date;

  /**
   * Date when the document was last modified.
   * May be undefined if not set in the document.
   */
  modificationDate?: Date;
}

/**
 * Extracts the page count from a PDF buffer.
 *
 * Parses the PDF document structure to determine the total number of pages.
 * Uses ignoreEncryption option to handle encrypted PDFs that still allow reading.
 *
 * @param pdfBuffer - Raw PDF binary data as a Buffer
 * @returns Promise resolving to the number of pages in the PDF
 * @throws Error if the PDF cannot be parsed or is corrupted
 *
 * @example
 * ```typescript
 * const pdfBuffer = await fs.readFile('invoice.pdf');
 * const pageCount = await getPageCount(pdfBuffer);
 * console.log(`PDF has ${pageCount} pages`);
 * ```
 */
export async function getPageCount(pdfBuffer: Buffer): Promise<number> {
  try {
    const pdfDoc = await PDFDocument.load(pdfBuffer, {
      ignoreEncryption: true,
    });
    const pageCount = pdfDoc.getPageCount();
    logger.debug({ pageCount }, 'PDF page count extracted');
    return pageCount;
  } catch (error) {
    logger.error({ error }, 'Failed to extract page count from PDF');
    throw new Error('Invalid PDF: unable to extract page count');
  }
}

/**
 * Extracts full metadata from a PDF buffer.
 *
 * Parses the PDF document to retrieve all available metadata properties
 * including page count, title, author, dates, and application information.
 * Optional fields will be undefined if not present in the source document.
 *
 * @param pdfBuffer - Raw PDF binary data as a Buffer
 * @returns Promise resolving to PdfMetadata object with all available metadata
 * @throws Error if the PDF cannot be parsed or is corrupted
 *
 * @example
 * ```typescript
 * const pdfBuffer = await fs.readFile('report.pdf');
 * const metadata = await getMetadata(pdfBuffer);
 * console.log(`Title: ${metadata.title || 'Unknown'}`);
 * console.log(`Pages: ${metadata.pageCount}`);
 * console.log(`Created: ${metadata.creationDate?.toISOString()}`);
 * ```
 */
export async function getMetadata(pdfBuffer: Buffer): Promise<PdfMetadata> {
  try {
    const pdfDoc = await PDFDocument.load(pdfBuffer, {
      ignoreEncryption: true,
    });

    const metadata: PdfMetadata = {
      pageCount: pdfDoc.getPageCount(),
      title: pdfDoc.getTitle(),
      author: pdfDoc.getAuthor(),
      subject: pdfDoc.getSubject(),
      creator: pdfDoc.getCreator(),
      producer: pdfDoc.getProducer(),
      creationDate: pdfDoc.getCreationDate(),
      modificationDate: pdfDoc.getModificationDate(),
    };

    logger.debug({ pageCount: metadata.pageCount }, 'PDF metadata extracted');
    return metadata;
  } catch (error) {
    logger.error({ error }, 'Failed to extract metadata from PDF');
    throw new Error('Invalid PDF: unable to extract metadata');
  }
}

/**
 * Validates that a buffer contains a valid PDF document.
 *
 * Performs two-stage validation:
 * 1. Checks for PDF magic bytes ("%PDF-") at the start of the buffer
 * 2. Attempts to parse the document structure using pdf-lib
 *
 * This function never throws - it returns false for any invalid input.
 *
 * @param buffer - Buffer to validate as PDF
 * @returns Promise resolving to true if buffer contains valid PDF data, false otherwise
 *
 * @example
 * ```typescript
 * const buffer = await fs.readFile('unknown-file.bin');
 * if (await isValidPdf(buffer)) {
 *   // Process as PDF
 * } else {
 *   // Handle invalid file
 * }
 * ```
 */
export async function isValidPdf(buffer: Buffer): Promise<boolean> {
  try {
    // Check minimum length for PDF magic bytes
    if (buffer.length < 5) {
      return false;
    }

    // Check PDF magic bytes at the beginning of the file
    const header = buffer.subarray(0, 5).toString('ascii');
    if (header !== '%PDF-') {
      return false;
    }

    // Attempt to parse the document to validate internal structure
    await PDFDocument.load(buffer, {
      ignoreEncryption: true,
    });

    return true;
  } catch {
    // Any parsing error means invalid PDF
    return false;
  }
}

/**
 * Gets the size of a PDF buffer in bytes.
 *
 * Simple utility function that returns the byte length of the PDF buffer.
 * Useful for including file size information in API responses.
 *
 * @param pdfBuffer - Raw PDF binary data as a Buffer
 * @returns Size of the PDF in bytes
 *
 * @example
 * ```typescript
 * const pdfBuffer = await generatePdf(html);
 * const sizeBytes = getPdfSize(pdfBuffer);
 * console.log(`Generated PDF size: ${sizeBytes} bytes`);
 * ```
 */
export function getPdfSize(pdfBuffer: Buffer): number {
  return pdfBuffer.length;
}

/**
 * Formats a file size in bytes to a human-readable string.
 *
 * Converts byte values to appropriate units (Bytes, KB, MB, GB)
 * with two decimal places for readability.
 *
 * @param bytes - Size in bytes (must be non-negative)
 * @returns Formatted string with appropriate unit (e.g., "1.5 MB", "256 KB")
 *
 * @example
 * ```typescript
 * formatFileSize(0);         // "0 Bytes"
 * formatFileSize(1024);      // "1 KB"
 * formatFileSize(1536);      // "1.5 KB"
 * formatFileSize(1048576);   // "1 MB"
 * formatFileSize(1572864);   // "1.5 MB"
 * ```
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) {
    return '0 Bytes';
  }

  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  // Ensure index doesn't exceed available size units
  const unitIndex = Math.min(i, sizes.length - 1);

  return `${parseFloat((bytes / Math.pow(k, unitIndex)).toFixed(2))} ${sizes[unitIndex]}`;
}
