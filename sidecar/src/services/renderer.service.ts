/**
 * @fileoverview Puppeteer-based PDF renderer service for the document-sidecar.
 *
 * Manages a singleton browser instance with page pooling for efficient concurrent
 * PDF generation. Provides generatePdf(html, options) method that creates new browser
 * pages, sets HTML content, generates PDF with configurable page size/margins, and
 * returns the PDF buffer. Implements graceful shutdown to close browser and complete
 * in-flight requests. Uses lazy browser initialization pattern for efficient resource usage.
 *
 * Key Features:
 * - Browser instance reuse eliminates ~500ms startup per request
 * - New page created per request, closed after use
 * - Uses waitUntil: 'networkidle0' for complete page load before PDF generation
 * - Docker-compatible Chrome flags (--no-sandbox, --disable-setuid-sandbox, etc.)
 * - printBackground: true for proper background rendering
 * - Request ID correlation for distributed tracing
 * - Graceful shutdown with in-flight request completion
 *
 * @module sidecar/services/renderer.service
 * @see Agent Action Plan Section 0.3.2, 0.5.1, 0.5.4
 */

import puppeteer from 'puppeteer';
import type { Browser, Page, PDFOptions, PuppeteerLaunchOptions } from 'puppeteer';
import { logger, createRequestLogger } from '../utils/logger.js';
import type { PageSize } from '../contracts/request.schema.js';

// =============================================================================
// CONSTANTS
// =============================================================================

/**
 * Mapping of supported page sizes to their physical dimensions.
 *
 * Supported formats:
 * - A4: ISO A4 (210mm × 297mm) - International standard
 * - Letter: US Letter (8.5" × 11") - North American standard
 * - Legal: US Legal (8.5" × 14") - Legal documents
 *
 * @constant
 * @type {Record<PageSize, { width: string; height: string }>}
 */
const PAGE_DIMENSIONS: Record<PageSize, { width: string; height: string }> = {
  A4: { width: '210mm', height: '297mm' },
  Letter: { width: '8.5in', height: '11in' },
  Legal: { width: '8.5in', height: '14in' },
};

/**
 * Default PDF margins applied when not specified in options.
 * Standard document margins suitable for printing.
 *
 * @constant
 */
const DEFAULT_MARGINS = {
  top: '10mm',
  right: '10mm',
  bottom: '10mm',
  left: '10mm',
};

/**
 * Maximum time to wait for active pages to complete during shutdown (in milliseconds).
 * After this timeout, shutdown will proceed forcefully.
 *
 * @constant
 */
const SHUTDOWN_TIMEOUT_MS = 30000;

/**
 * Interval between shutdown status checks (in milliseconds).
 *
 * @constant
 */
const SHUTDOWN_POLL_INTERVAL_MS = 500;

/**
 * Timeout for setContent operation (in milliseconds).
 * Allows time for networkidle0 to be achieved for pages with resources.
 *
 * @constant
 */
const SET_CONTENT_TIMEOUT_MS = 30000;

/**
 * Default viewport dimensions for consistent rendering.
 * Wide viewport ensures proper layout for most document templates.
 *
 * @constant
 */
const DEFAULT_VIEWPORT = {
  width: 1200,
  height: 800,
};

// =============================================================================
// INTERFACES
// =============================================================================

/**
 * Configuration options for PDF rendering.
 *
 * All properties are optional with sensible defaults:
 * - pageSize: 'A4' (ISO A4 format)
 * - landscape: false (portrait orientation)
 * - printBackground: true (include CSS backgrounds)
 * - margin: 10mm on all sides
 *
 * @interface RenderPdfOptions
 *
 * @example
 * ```typescript
 * // Default options (A4 portrait with backgrounds)
 * const pdf = await rendererService.generatePdf(html);
 *
 * // Custom options (Letter landscape)
 * const pdf = await rendererService.generatePdf(html, {
 *   pageSize: 'Letter',
 *   landscape: true,
 *   margin: { top: '0.5in', right: '0.5in', bottom: '0.5in', left: '0.5in' },
 * });
 * ```
 */
export interface RenderPdfOptions {
  /**
   * Page size for the generated PDF.
   * @default 'A4'
   */
  pageSize?: PageSize;

  /**
   * Whether to generate PDF in landscape orientation.
   * @default false
   */
  landscape?: boolean;

  /**
   * Whether to print CSS background colors and images.
   * @default true
   */
  printBackground?: boolean;

  /**
   * Page margins for the PDF.
   * Accepts CSS-compatible length units (mm, in, px, cm).
   * @default { top: '10mm', right: '10mm', bottom: '10mm', left: '10mm' }
   */
  margin?: {
    top?: string;
    right?: string;
    bottom?: string;
    left?: string;
  };
}

// =============================================================================
// RENDERER SERVICE CLASS
// =============================================================================

/**
 * Puppeteer-based PDF renderer service with browser pool management.
 *
 * This service manages a singleton Chromium browser instance that is lazily
 * initialized on first use. Each PDF generation request creates a new page
 * within the shared browser, ensuring isolation between requests while
 * avoiding the ~500ms browser startup overhead.
 *
 * Key Characteristics:
 * - Lazy initialization: Browser only started when first needed
 * - Singleton pattern: Single browser instance shared across requests
 * - Page isolation: Each request gets a fresh page context
 * - Graceful shutdown: Waits for in-flight requests before closing
 * - Automatic recovery: Handles unexpected browser disconnection
 *
 * Thread Safety:
 * - activePages counter tracks concurrent operations
 * - isShuttingDown flag prevents new requests during shutdown
 * - Browser disconnection handler resets state for recovery
 *
 * @class RendererService
 *
 * @example
 * ```typescript
 * import { rendererService } from './services/renderer.service.js';
 *
 * // Generate PDF from HTML
 * const html = '<html><body><h1>Invoice</h1></body></html>';
 * const pdfBuffer = await rendererService.generatePdf(html, {
 *   pageSize: 'A4',
 *   printBackground: true,
 * });
 *
 * // Graceful shutdown on process termination
 * process.on('SIGTERM', async () => {
 *   await rendererService.shutdown();
 *   process.exit(0);
 * });
 * ```
 */
export class RendererService {
  /**
   * Singleton Puppeteer browser instance.
   * Null until first PDF generation request triggers lazy initialization.
   * @private
   */
  private browser: Browser | null = null;

  /**
   * Flag indicating whether the service is in shutdown mode.
   * When true, new PDF generation requests will be rejected.
   * @private
   */
  private isShuttingDown = false;

  /**
   * Count of currently active browser pages.
   * Used during shutdown to wait for in-flight requests to complete.
   * @private
   */
  private activePages = 0;

  /**
   * Creates a new RendererService instance.
   *
   * The constructor does not initialize the browser - this happens lazily
   * on the first call to generatePdf() for efficient resource usage.
   */
  constructor() {
    // Lazy initialization - browser created on first use
    // This allows the service to be imported without side effects
    logger.debug('RendererService instance created');
  }

  /**
   * Gets or creates the Puppeteer browser instance (lazy initialization).
   *
   * This method implements the lazy initialization pattern for the browser:
   * - First call: Launches a new Chromium browser with optimized settings
   * - Subsequent calls: Returns the existing browser instance
   * - During shutdown: Throws an error to prevent new operations
   *
   * Browser Launch Options:
   * - headless: true (no GUI)
   * - --no-sandbox: Required for Docker containers
   * - --disable-setuid-sandbox: Required for Docker containers
   * - --disable-dev-shm-usage: Prevents /dev/shm overflow in Docker
   * - --disable-gpu: Not needed for PDF generation
   * - --disable-software-rasterizer: Performance optimization
   * - --single-process: Reduces memory footprint
   *
   * @returns Promise resolving to the Puppeteer Browser instance
   * @throws Error if the service is shutting down
   * @private
   */
  private async getBrowser(): Promise<Browser> {
    // Reject new requests during shutdown
    if (this.isShuttingDown) {
      throw new Error('Renderer service is shutting down - cannot accept new requests');
    }

    // Return existing browser if available
    if (this.browser) {
      return this.browser;
    }

    // Launch new browser instance with Docker-compatible options
    const launchOptions: PuppeteerLaunchOptions = {
      // Run in headless mode (no GUI)
      headless: true,
      // Chrome flags optimized for Docker container environment
      args: [
        // SECURITY: Required for running as root in containers
        '--no-sandbox',
        // SECURITY: Required for running as root in containers
        '--disable-setuid-sandbox',
        // PERFORMANCE: Prevents /dev/shm overflow in Docker (uses /tmp instead)
        '--disable-dev-shm-usage',
        // PERFORMANCE: GPU not needed for PDF generation
        '--disable-gpu',
        // PERFORMANCE: Software rasterizer not needed
        '--disable-software-rasterizer',
        // PERFORMANCE: Reduces memory footprint for container environments
        '--single-process',
        // PERFORMANCE: Disable unnecessary extensions
        '--disable-extensions',
        // PERFORMANCE: Disable background networking
        '--disable-background-networking',
        // PERFORMANCE: Disable sync
        '--disable-sync',
        // PERFORMANCE: Disable translate
        '--disable-translate',
        // STABILITY: Disable crash reporter
        '--disable-breakpad',
      ],
    };

    logger.info('Launching Puppeteer browser instance');
    const startTime = Date.now();

    try {
      this.browser = await puppeteer.launch(launchOptions);

      const launchDuration = Date.now() - startTime;
      logger.info({ launchDuration }, 'Puppeteer browser launched successfully');

      // Handle unexpected browser disconnection (crash, OOM, etc.)
      this.browser.on('disconnected', () => {
        logger.warn('Browser disconnected unexpectedly - will reinitialize on next request');
        this.browser = null;
      });

      return this.browser;
    } catch (error) {
      logger.error({ error, launchDuration: Date.now() - startTime }, 'Failed to launch Puppeteer browser');
      throw error;
    }
  }

  /**
   * Generates a PDF from HTML content using Puppeteer.
   *
   * This method:
   * 1. Obtains or creates a browser instance
   * 2. Creates a new page within the browser
   * 3. Sets the viewport for consistent rendering
   * 4. Loads the HTML content and waits for network idle
   * 5. Generates the PDF with specified options
   * 6. Closes the page to free resources
   * 7. Returns the PDF buffer
   *
   * Performance Characteristics:
   * - First request: ~500ms browser startup + page creation + rendering
   * - Subsequent requests: Page creation + rendering (no browser startup)
   * - Target P95 latency: Under 5 seconds for standard documents
   *
   * @param html - Complete HTML document to render as PDF
   * @param options - PDF rendering options (pageSize, landscape, printBackground, margin)
   * @param requestId - Optional request ID for log correlation (distributed tracing)
   * @returns Promise resolving to Buffer containing the generated PDF
   * @throws Error if browser is shutting down
   * @throws Error if HTML content cannot be loaded
   * @throws Error if PDF generation fails
   *
   * @example
   * ```typescript
   * // Basic usage with default options
   * const html = '<html><body><h1>Hello World</h1></body></html>';
   * const pdf = await rendererService.generatePdf(html);
   *
   * // With custom options and request correlation
   * const pdf = await rendererService.generatePdf(html, {
   *   pageSize: 'Letter',
   *   landscape: true,
   *   printBackground: true,
   *   margin: { top: '0.5in', right: '0.5in', bottom: '0.5in', left: '0.5in' },
   * }, 'req-123-abc');
   * ```
   */
  async generatePdf(
    html: string,
    options: RenderPdfOptions = {},
    requestId?: string
  ): Promise<Buffer> {
    // Create request-scoped logger for distributed tracing
    const log = requestId ? createRequestLogger(requestId) : logger;
    const startTime = Date.now();
    let page: Page | null = null;

    try {
      // Get or create browser instance
      const browser = await this.getBrowser();

      // Track active page for graceful shutdown
      this.activePages++;

      // Create new page for this request (isolated context)
      page = await browser.newPage();
      log.debug('Created new browser page for PDF generation');

      // Set viewport for consistent rendering across requests
      // Wide viewport ensures proper layout for most document templates
      await page.setViewport(DEFAULT_VIEWPORT);

      // Load HTML content and wait for all network activity to complete
      // networkidle0 ensures fonts, images, and other resources are fully loaded
      await page.setContent(html, {
        waitUntil: 'networkidle0',
        timeout: SET_CONTENT_TIMEOUT_MS,
      });
      log.debug({ contentLength: html.length }, 'HTML content loaded, network idle');

      // Resolve page size dimensions
      const pageSize = options.pageSize || 'A4';
      const dimensions = PAGE_DIMENSIONS[pageSize];

      // Build PDF options from provided options with defaults
      const pdfOptions: PDFOptions = {
        // Page dimensions
        width: dimensions.width,
        height: dimensions.height,
        // Print CSS backgrounds (colors, images) - important for styled documents
        printBackground: options.printBackground ?? true,
        // Page margins - use provided or defaults
        margin: {
          top: options.margin?.top ?? DEFAULT_MARGINS.top,
          right: options.margin?.right ?? DEFAULT_MARGINS.right,
          bottom: options.margin?.bottom ?? DEFAULT_MARGINS.bottom,
          left: options.margin?.left ?? DEFAULT_MARGINS.left,
        },
        // Orientation
        landscape: options.landscape ?? false,
      };

      log.debug({ pageSize, landscape: pdfOptions.landscape }, 'Generating PDF with options');

      // Generate PDF - this is the core rendering operation
      const pdfBuffer = await page.pdf(pdfOptions);

      // Calculate total duration for performance monitoring
      const duration = Date.now() - startTime;
      log.info(
        { duration, pageSize, pdfSizeBytes: pdfBuffer.length },
        'PDF generated successfully'
      );

      // Return as Node.js Buffer for consistent handling
      return Buffer.from(pdfBuffer);
    } catch (error) {
      // Log error with duration for debugging
      const duration = Date.now() - startTime;
      log.error(
        { error, duration },
        'PDF generation failed'
      );
      throw error;
    } finally {
      // Always clean up the page to prevent resource leaks
      if (page) {
        try {
          await page.close();
          log.debug('Browser page closed');
        } catch (closeError) {
          // Log but don't throw - page might already be closed due to browser crash
          log.warn({ error: closeError }, 'Failed to close browser page');
        }
      }
      // Decrement active pages counter
      this.activePages--;
    }
  }

  /**
   * Gracefully shuts down the renderer service.
   *
   * This method implements graceful shutdown by:
   * 1. Setting a flag to reject new requests
   * 2. Waiting for in-flight PDF generations to complete
   * 3. Closing the browser instance
   *
   * Timeout Behavior:
   * - Waits up to SHUTDOWN_TIMEOUT_MS (30 seconds) for active pages
   * - If timeout is reached, forces shutdown with warning
   * - Ensures browser is always closed, even if pages are still active
   *
   * This method should be called during process shutdown to ensure
   * clean resource cleanup and completion of in-flight requests.
   *
   * @returns Promise that resolves when shutdown is complete
   *
   * @example
   * ```typescript
   * // Handle graceful shutdown on SIGTERM
   * process.on('SIGTERM', async () => {
   *   console.log('Received SIGTERM, initiating graceful shutdown');
   *   await rendererService.shutdown();
   *   process.exit(0);
   * });
   *
   * // Handle Ctrl+C (SIGINT)
   * process.on('SIGINT', async () => {
   *   console.log('Received SIGINT, initiating graceful shutdown');
   *   await rendererService.shutdown();
   *   process.exit(0);
   * });
   * ```
   */
  async shutdown(): Promise<void> {
    logger.info('Initiating renderer service shutdown');

    // Set shutdown flag to reject new requests
    this.isShuttingDown = true;

    // Wait for active pages to complete with timeout
    const startTime = Date.now();

    while (this.activePages > 0 && Date.now() - startTime < SHUTDOWN_TIMEOUT_MS) {
      logger.info(
        { activePages: this.activePages, elapsedMs: Date.now() - startTime },
        'Waiting for active pages to complete'
      );
      // Poll every SHUTDOWN_POLL_INTERVAL_MS
      await new Promise((resolve) => setTimeout(resolve, SHUTDOWN_POLL_INTERVAL_MS));
    }

    // Log warning if we're forcing shutdown with active pages
    if (this.activePages > 0) {
      logger.warn(
        { activePages: this.activePages, timeoutMs: SHUTDOWN_TIMEOUT_MS },
        'Forcing shutdown with active pages still in progress'
      );
    }

    // Close browser if it exists
    if (this.browser) {
      try {
        await this.browser.close();
        this.browser = null;
        logger.info('Puppeteer browser closed successfully');
      } catch (error) {
        // Log but don't throw - browser might already be disconnected
        logger.warn({ error }, 'Error closing browser during shutdown');
        this.browser = null;
      }
    } else {
      logger.info('No browser instance to close');
    }

    logger.info('Renderer service shutdown complete');
  }
}

// =============================================================================
// SINGLETON INSTANCE EXPORT
// =============================================================================

/**
 * Singleton instance of the RendererService.
 *
 * This instance is shared across the application for efficient browser reuse.
 * Import this constant to use the PDF rendering capabilities.
 *
 * @constant
 * @type {RendererService}
 *
 * @example
 * ```typescript
 * import { rendererService } from './services/renderer.service.js';
 *
 * // Generate PDF
 * const pdfBuffer = await rendererService.generatePdf(html, { pageSize: 'A4' });
 *
 * // Shutdown during process exit
 * await rendererService.shutdown();
 * ```
 */
export const rendererService = new RendererService();
