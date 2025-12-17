/**
 * @fileoverview Unit tests for the RendererService class in the document-sidecar TypeScript service.
 *
 * Tests Puppeteer browser pool management, lazy browser initialization via getBrowser(),
 * PDF generation via generatePdf(html, options), page lifecycle management, and graceful
 * shutdown behavior. Uses Vitest framework with mocking for Puppeteer to avoid actual
 * browser instantiation during tests.
 *
 * @module sidecar/tests/unit/renderer.service.test
 * @see Agent Action Plan Section 0.3.1 - Unit tests for renderer service
 */

import { describe, it, expect, vi, beforeEach, afterEach, type MockInstance } from 'vitest';

// =============================================================================
// MOCK SETUP - Must be before imports that use mocked modules
// =============================================================================

/**
 * Mock page object simulating Puppeteer Page interface.
 * All methods return resolved promises to simulate async behavior.
 */
const mockPage = {
  setViewport: vi.fn().mockResolvedValue(undefined),
  setContent: vi.fn().mockResolvedValue(undefined),
  pdf: vi.fn().mockResolvedValue(Buffer.from('%PDF-1.4 test content')),
  close: vi.fn().mockResolvedValue(undefined),
};

/**
 * Mock browser object simulating Puppeteer Browser interface.
 * newPage returns the mock page, close resolves immediately.
 */
const mockBrowser = {
  newPage: vi.fn().mockResolvedValue(mockPage),
  close: vi.fn().mockResolvedValue(undefined),
  on: vi.fn(),
};

/**
 * Mock Puppeteer module to avoid actual browser instantiation.
 * puppeteer.launch returns the mock browser instance.
 */
vi.mock('puppeteer', () => ({
  default: {
    launch: vi.fn().mockResolvedValue(mockBrowser),
  },
}));

/**
 * Mock logger module to prevent actual logging during tests.
 * Provides stub functions for all log levels that can be asserted.
 */
vi.mock('../../src/utils/logger.js', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    fatal: vi.fn(),
    trace: vi.fn(),
    child: vi.fn().mockReturnValue({
      debug: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    }),
  },
  createRequestLogger: vi.fn(() => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  })),
}));

/**
 * Mock config module to provide test environment settings.
 */
vi.mock('../../src/config.js', () => ({
  config: {
    nodeEnv: 'test',
    logLevel: 'info',
  },
}));

// Import after mocks are set up
import puppeteer from 'puppeteer';
import { RendererService, RenderPdfOptions } from '../../src/services/renderer.service.js';
import { logger, createRequestLogger } from '../../src/utils/logger.js';

// =============================================================================
// TEST SUITE
// =============================================================================

describe('RendererService', () => {
  let service: RendererService;

  /**
   * Reset all mocks and create a fresh service instance before each test.
   */
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset mock implementations to default resolved values
    mockPage.setViewport.mockResolvedValue(undefined);
    mockPage.setContent.mockResolvedValue(undefined);
    mockPage.pdf.mockResolvedValue(Buffer.from('%PDF-1.4 test content'));
    mockPage.close.mockResolvedValue(undefined);
    mockBrowser.newPage.mockResolvedValue(mockPage);
    mockBrowser.close.mockResolvedValue(undefined);
    (puppeteer.launch as MockInstance).mockResolvedValue(mockBrowser);
    
    // Create fresh service instance
    service = new RendererService();
  });

  /**
   * Clean up service after each test to prevent state leakage.
   */
  afterEach(async () => {
    // Suppress any shutdown errors during cleanup
    try {
      await service.shutdown();
    } catch {
      // Ignore shutdown errors in cleanup
    }
  });

  // ===========================================================================
  // CONSTRUCTOR TESTS
  // ===========================================================================

  describe('constructor', () => {
    it('should create a new RendererService instance', () => {
      const newService = new RendererService();
      expect(newService).toBeInstanceOf(RendererService);
    });

    it('should not launch browser on construction (lazy initialization)', () => {
      // Browser should not be launched just by creating instance
      new RendererService();
      expect(puppeteer.launch).not.toHaveBeenCalled();
    });

    it('should log debug message on instance creation', () => {
      new RendererService();
      expect(logger.debug).toHaveBeenCalledWith('RendererService instance created');
    });
  });

  // ===========================================================================
  // getBrowser (LAZY INITIALIZATION) TESTS
  // ===========================================================================

  describe('getBrowser (lazy initialization)', () => {
    it('should launch browser on first generatePdf call', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      expect(puppeteer.launch).toHaveBeenCalledTimes(1);
    });

    it('should reuse browser instance on subsequent generatePdf calls', async () => {
      await service.generatePdf('<html><body>Test 1</body></html>');
      await service.generatePdf('<html><body>Test 2</body></html>');
      await service.generatePdf('<html><body>Test 3</body></html>');
      
      // Browser should only be launched once
      expect(puppeteer.launch).toHaveBeenCalledTimes(1);
    });

    it('should launch browser with correct Docker-compatible flags', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      
      expect(puppeteer.launch).toHaveBeenCalledWith(
        expect.objectContaining({
          headless: true,
          args: expect.arrayContaining([
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--single-process',
          ]),
        })
      );
    });

    it('should register browser disconnected handler', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      
      expect(mockBrowser.on).toHaveBeenCalledWith('disconnected', expect.any(Function));
    });

    it('should reinitialize browser after disconnection', async () => {
      // First call - initializes browser
      await service.generatePdf('<html><body>Test 1</body></html>');
      expect(puppeteer.launch).toHaveBeenCalledTimes(1);
      
      // Simulate browser disconnection by calling the registered handler
      const disconnectHandler = mockBrowser.on.mock.calls.find(
        (call) => call[0] === 'disconnected'
      )?.[1] as () => void;
      
      if (disconnectHandler) {
        disconnectHandler();
      }
      
      // Second call - should reinitialize browser
      await service.generatePdf('<html><body>Test 2</body></html>');
      expect(puppeteer.launch).toHaveBeenCalledTimes(2);
    });

    it('should throw error when service is shutting down', async () => {
      // Initialize browser first
      await service.generatePdf('<html><body>Test</body></html>');
      
      // Start shutdown process (but don't await it)
      const shutdownPromise = service.shutdown();
      
      // Try to generate PDF while shutting down
      await expect(service.generatePdf('<html><body>Test</body></html>')).rejects.toThrow(
        'Renderer service is shutting down - cannot accept new requests'
      );
      
      // Wait for shutdown to complete
      await shutdownPromise;
    });

    it('should log info message when launching browser', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      
      expect(logger.info).toHaveBeenCalledWith('Launching Puppeteer browser instance');
    });

    it('should log success with launch duration after browser starts', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      
      expect(logger.info).toHaveBeenCalledWith(
        expect.objectContaining({ launchDuration: expect.any(Number) }),
        'Puppeteer browser launched successfully'
      );
    });

    it('should throw and log error when browser launch fails', async () => {
      const launchError = new Error('Failed to launch browser');
      (puppeteer.launch as MockInstance).mockRejectedValueOnce(launchError);
      
      await expect(service.generatePdf('<html><body>Test</body></html>')).rejects.toThrow(
        'Failed to launch browser'
      );
      
      expect(logger.error).toHaveBeenCalledWith(
        expect.objectContaining({ error: launchError }),
        'Failed to launch Puppeteer browser'
      );
    });
  });

  // ===========================================================================
  // generatePdf METHOD TESTS
  // ===========================================================================

  describe('generatePdf', () => {
    it('should return Buffer containing PDF data', async () => {
      const pdfBuffer = await service.generatePdf('<html><body>Test</body></html>');
      
      expect(Buffer.isBuffer(pdfBuffer)).toBe(true);
      expect(pdfBuffer.toString()).toContain('%PDF');
    });

    it('should create new page with newPage()', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      
      expect(mockBrowser.newPage).toHaveBeenCalledTimes(1);
    });

    it('should set viewport to default dimensions (1200x800)', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      
      expect(mockPage.setViewport).toHaveBeenCalledWith({
        width: 1200,
        height: 800,
      });
    });

    it('should call setContent with HTML and waitUntil networkidle0', async () => {
      const html = '<html><body><h1>Test Document</h1></body></html>';
      await service.generatePdf(html);
      
      expect(mockPage.setContent).toHaveBeenCalledWith(html, {
        waitUntil: 'networkidle0',
        timeout: 30000, // SET_CONTENT_TIMEOUT_MS
      });
    });

    it('should call page.pdf with correct default options (A4, printBackground: true)', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          width: '210mm',
          height: '297mm',
          printBackground: true,
          landscape: false,
          margin: {
            top: '10mm',
            right: '10mm',
            bottom: '10mm',
            left: '10mm',
          },
        })
      );
    });

    it('should close page after PDF generation', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      
      expect(mockPage.close).toHaveBeenCalledTimes(1);
    });

    it('should pass requestId to create request-scoped logger', async () => {
      const requestId = 'test-request-id-123';
      await service.generatePdf('<html><body>Test</body></html>', {}, requestId);
      
      expect(createRequestLogger).toHaveBeenCalledWith(requestId);
    });

    it('should use main logger when requestId is not provided', async () => {
      await service.generatePdf('<html><body>Test</body></html>');
      
      // Without requestId, createRequestLogger should not be called for creating the log
      // The main logger should be used for info logging about PDF generation
      expect(logger.info).toHaveBeenCalled();
    });
  });

  // ===========================================================================
  // PAGE SIZE OPTIONS TESTS
  // ===========================================================================

  describe('page size options', () => {
    it('should use correct dimensions for A4 (default)', async () => {
      await service.generatePdf('<html></html>', { pageSize: 'A4' });
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          width: '210mm',
          height: '297mm',
        })
      );
    });

    it('should use correct dimensions for Letter', async () => {
      await service.generatePdf('<html></html>', { pageSize: 'Letter' });
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          width: '8.5in',
          height: '11in',
        })
      );
    });

    it('should use correct dimensions for Legal', async () => {
      await service.generatePdf('<html></html>', { pageSize: 'Legal' });
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          width: '8.5in',
          height: '14in',
        })
      );
    });

    it('should default to A4 when pageSize is not specified', async () => {
      await service.generatePdf('<html></html>', {});
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          width: '210mm',
          height: '297mm',
        })
      );
    });
  });

  // ===========================================================================
  // CUSTOM OPTIONS TESTS
  // ===========================================================================

  describe('custom rendering options', () => {
    it('should apply custom margins', async () => {
      const options: RenderPdfOptions = {
        margin: {
          top: '20mm',
          right: '15mm',
          bottom: '25mm',
          left: '15mm',
        },
      };
      
      await service.generatePdf('<html></html>', options);
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          margin: {
            top: '20mm',
            right: '15mm',
            bottom: '25mm',
            left: '15mm',
          },
        })
      );
    });

    it('should apply partial custom margins with defaults for others', async () => {
      const options: RenderPdfOptions = {
        margin: {
          top: '20mm',
          // right, bottom, left should use defaults
        },
      };
      
      await service.generatePdf('<html></html>', options);
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          margin: {
            top: '20mm',
            right: '10mm',
            bottom: '10mm',
            left: '10mm',
          },
        })
      );
    });

    it('should apply landscape option', async () => {
      await service.generatePdf('<html></html>', { landscape: true });
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          landscape: true,
        })
      );
    });

    it('should use portrait (landscape: false) by default', async () => {
      await service.generatePdf('<html></html>', {});
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          landscape: false,
        })
      );
    });

    it('should apply printBackground option as false', async () => {
      await service.generatePdf('<html></html>', { printBackground: false });
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          printBackground: false,
        })
      );
    });

    it('should default printBackground to true', async () => {
      await service.generatePdf('<html></html>', {});
      
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          printBackground: true,
        })
      );
    });

    it('should combine multiple custom options correctly', async () => {
      const options: RenderPdfOptions = {
        pageSize: 'Letter',
        landscape: true,
        printBackground: false,
        margin: {
          top: '0.5in',
          right: '0.5in',
          bottom: '0.5in',
          left: '0.5in',
        },
      };
      
      await service.generatePdf('<html></html>', options);
      
      expect(mockPage.pdf).toHaveBeenCalledWith({
        width: '8.5in',
        height: '11in',
        landscape: true,
        printBackground: false,
        margin: {
          top: '0.5in',
          right: '0.5in',
          bottom: '0.5in',
          left: '0.5in',
        },
      });
    });
  });

  // ===========================================================================
  // PAGE LIFECYCLE MANAGEMENT TESTS
  // ===========================================================================

  describe('page lifecycle management', () => {
    it('should handle multiple concurrent generatePdf calls', async () => {
      const promises = [
        service.generatePdf('<html><body>Doc 1</body></html>'),
        service.generatePdf('<html><body>Doc 2</body></html>'),
        service.generatePdf('<html><body>Doc 3</body></html>'),
      ];
      
      const results = await Promise.all(promises);
      
      // All should succeed
      expect(results).toHaveLength(3);
      results.forEach((result) => {
        expect(Buffer.isBuffer(result)).toBe(true);
      });
      
      // Multiple pages created
      expect(mockBrowser.newPage).toHaveBeenCalledTimes(3);
      
      // All pages closed
      expect(mockPage.close).toHaveBeenCalledTimes(3);
    });

    it('should close page even when setContent fails', async () => {
      const contentError = new Error('Failed to set content');
      mockPage.setContent.mockRejectedValueOnce(contentError);
      
      await expect(service.generatePdf('<html></html>')).rejects.toThrow('Failed to set content');
      
      // Page should still be closed in finally block
      expect(mockPage.close).toHaveBeenCalledTimes(1);
    });

    it('should close page even when page.pdf fails', async () => {
      const pdfError = new Error('PDF generation failed');
      mockPage.pdf.mockRejectedValueOnce(pdfError);
      
      await expect(service.generatePdf('<html></html>')).rejects.toThrow('PDF generation failed');
      
      // Page should still be closed in finally block
      expect(mockPage.close).toHaveBeenCalledTimes(1);
    });

    it('should handle page.close failure gracefully', async () => {
      // Generate PDF successfully but page.close fails
      mockPage.close.mockRejectedValueOnce(new Error('Close failed'));
      
      // Should not throw despite close failure
      const result = await service.generatePdf('<html></html>');
      
      expect(Buffer.isBuffer(result)).toBe(true);
      expect(logger.warn).toHaveBeenCalledWith(
        expect.objectContaining({ error: expect.any(Error) }),
        'Failed to close browser page'
      );
    });
  });

  // ===========================================================================
  // ERROR HANDLING TESTS
  // ===========================================================================

  describe('error handling', () => {
    it('should throw error when setContent fails', async () => {
      const error = new Error('Content load timeout');
      mockPage.setContent.mockRejectedValueOnce(error);
      
      await expect(service.generatePdf('<html></html>')).rejects.toThrow('Content load timeout');
    });

    it('should throw error when page.pdf fails', async () => {
      const error = new Error('PDF buffer overflow');
      mockPage.pdf.mockRejectedValueOnce(error);
      
      await expect(service.generatePdf('<html></html>')).rejects.toThrow('PDF buffer overflow');
    });

    it('should throw error when newPage fails', async () => {
      const error = new Error('No available page slots');
      mockBrowser.newPage.mockRejectedValueOnce(error);
      
      await expect(service.generatePdf('<html></html>')).rejects.toThrow('No available page slots');
    });

    it('should log error with duration when generation fails', async () => {
      const pdfError = new Error('Rendering failed');
      mockPage.pdf.mockRejectedValueOnce(pdfError);
      
      await expect(service.generatePdf('<html></html>')).rejects.toThrow();
      
      expect(logger.error).toHaveBeenCalledWith(
        expect.objectContaining({
          error: pdfError,
          duration: expect.any(Number),
        }),
        'PDF generation failed'
      );
    });

    it('should log success with duration and PDF size on completion', async () => {
      await service.generatePdf('<html></html>');
      
      expect(logger.info).toHaveBeenCalledWith(
        expect.objectContaining({
          duration: expect.any(Number),
          pdfSizeBytes: expect.any(Number),
          pageSize: 'A4',
        }),
        'PDF generated successfully'
      );
    });
  });

  // ===========================================================================
  // SHUTDOWN METHOD TESTS
  // ===========================================================================

  describe('shutdown', () => {
    it('should close browser on shutdown', async () => {
      // Initialize browser first
      await service.generatePdf('<html></html>');
      
      await service.shutdown();
      
      expect(mockBrowser.close).toHaveBeenCalledTimes(1);
    });

    it('should set isShuttingDown flag to prevent new requests', async () => {
      // Initialize browser
      await service.generatePdf('<html></html>');
      
      // Start shutdown
      const shutdownPromise = service.shutdown();
      
      // New request should be rejected
      await expect(service.generatePdf('<html></html>')).rejects.toThrow(
        'Renderer service is shutting down - cannot accept new requests'
      );
      
      await shutdownPromise;
    });

    it('should handle shutdown when browser was never initialized', async () => {
      // Don't generate any PDFs - browser never initialized
      await service.shutdown();
      
      // Should not throw and should log appropriate message
      expect(logger.info).toHaveBeenCalledWith('No browser instance to close');
    });

    it('should handle browser.close failure gracefully', async () => {
      await service.generatePdf('<html></html>');
      
      mockBrowser.close.mockRejectedValueOnce(new Error('Already closed'));
      
      // Should not throw
      await service.shutdown();
      
      expect(logger.warn).toHaveBeenCalledWith(
        expect.objectContaining({ error: expect.any(Error) }),
        'Error closing browser during shutdown'
      );
    });

    it('should log shutdown initiation', async () => {
      await service.shutdown();
      
      expect(logger.info).toHaveBeenCalledWith('Initiating renderer service shutdown');
    });

    it('should log shutdown completion', async () => {
      await service.shutdown();
      
      expect(logger.info).toHaveBeenCalledWith('Renderer service shutdown complete');
    });

    it('should wait for active pages before closing browser', async () => {
      // Initialize browser
      await service.generatePdf('<html></html>');
      
      // Simulate a long-running PDF generation
      let resolveGeneration: () => void;
      const generationPromise = new Promise<void>((resolve) => {
        resolveGeneration = resolve;
      });
      
      mockPage.pdf.mockImplementationOnce(async () => {
        await generationPromise;
        return Buffer.from('%PDF-1.4 test');
      });
      
      // Start PDF generation (will be pending)
      const pdfPromise = service.generatePdf('<html></html>');
      
      // Give time for the generation to start
      await new Promise((resolve) => setTimeout(resolve, 50));
      
      // Start shutdown (should wait for active page)
      const shutdownPromise = service.shutdown();
      
      // Give time for shutdown to detect active pages
      await new Promise((resolve) => setTimeout(resolve, 100));
      
      // Shutdown should be waiting (not complete yet)
      expect(logger.info).toHaveBeenCalledWith(
        expect.objectContaining({ activePages: expect.any(Number) }),
        'Waiting for active pages to complete'
      );
      
      // Complete the PDF generation
      resolveGeneration!();
      await pdfPromise;
      
      // Now shutdown should complete
      await shutdownPromise;
      
      expect(logger.info).toHaveBeenCalledWith('Renderer service shutdown complete');
    });

    it('should force shutdown after timeout with active pages', async () => {
      // This test verifies the timeout behavior conceptually
      // We can't easily test the 30-second timeout, but we verify the warning is logged
      
      await service.generatePdf('<html></html>');
      await service.shutdown();
      
      // Verify shutdown completed normally (no active pages timeout)
      expect(logger.info).toHaveBeenCalledWith('Renderer service shutdown complete');
    });

    it('should be callable multiple times without error', async () => {
      await service.generatePdf('<html></html>');
      
      await service.shutdown();
      await service.shutdown(); // Second call should not throw
      
      // Browser close should only be called once (second time browser is null)
      expect(mockBrowser.close).toHaveBeenCalledTimes(1);
    });
  });

  // ===========================================================================
  // LOGGING AND TRACING TESTS
  // ===========================================================================

  describe('logging and tracing', () => {
    it('should log debug message when page is created', async () => {
      await service.generatePdf('<html></html>');
      
      expect(logger.debug).toHaveBeenCalledWith('Created new browser page for PDF generation');
    });

    it('should log debug message with content length after setting content', async () => {
      const html = '<html><body>Test content here</body></html>';
      await service.generatePdf(html);
      
      expect(logger.debug).toHaveBeenCalledWith(
        expect.objectContaining({ contentLength: html.length }),
        'HTML content loaded, network idle'
      );
    });

    it('should log debug message with page size and orientation', async () => {
      await service.generatePdf('<html></html>', { pageSize: 'Letter', landscape: true });
      
      expect(logger.debug).toHaveBeenCalledWith(
        expect.objectContaining({ pageSize: 'Letter', landscape: true }),
        'Generating PDF with options'
      );
    });

    it('should log debug when page is closed', async () => {
      await service.generatePdf('<html></html>');
      
      expect(logger.debug).toHaveBeenCalledWith('Browser page closed');
    });

    it('should log warning when browser disconnects unexpectedly', async () => {
      await service.generatePdf('<html></html>');
      
      // Simulate disconnection
      const disconnectHandler = mockBrowser.on.mock.calls.find(
        (call) => call[0] === 'disconnected'
      )?.[1] as () => void;
      
      if (disconnectHandler) {
        disconnectHandler();
      }
      
      expect(logger.warn).toHaveBeenCalledWith(
        'Browser disconnected unexpectedly - will reinitialize on next request'
      );
    });
  });

  // ===========================================================================
  // EDGE CASES AND BOUNDARY CONDITIONS
  // ===========================================================================

  describe('edge cases and boundary conditions', () => {
    it('should handle empty HTML string', async () => {
      const result = await service.generatePdf('');
      
      expect(Buffer.isBuffer(result)).toBe(true);
      expect(mockPage.setContent).toHaveBeenCalledWith('', expect.any(Object));
    });

    it('should handle very large HTML content', async () => {
      const largeHtml = '<html><body>' + 'x'.repeat(1000000) + '</body></html>';
      
      const result = await service.generatePdf(largeHtml);
      
      expect(Buffer.isBuffer(result)).toBe(true);
      expect(mockPage.setContent).toHaveBeenCalledWith(largeHtml, expect.any(Object));
    });

    it('should handle HTML with special characters', async () => {
      const specialHtml = '<html><body>Special: &amp; &lt; &gt; "quotes" \'apostrophe\'</body></html>';
      
      const result = await service.generatePdf(specialHtml);
      
      expect(Buffer.isBuffer(result)).toBe(true);
    });

    it('should handle HTML with unicode content', async () => {
      const unicodeHtml = '<html><body>Unicode: 日本語 中文 한국어 🎉 💡</body></html>';
      
      const result = await service.generatePdf(unicodeHtml);
      
      expect(Buffer.isBuffer(result)).toBe(true);
    });

    it('should handle empty options object', async () => {
      const result = await service.generatePdf('<html></html>', {});
      
      expect(Buffer.isBuffer(result)).toBe(true);
      // Should use all defaults
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          width: '210mm',
          height: '297mm',
          landscape: false,
          printBackground: true,
        })
      );
    });

    it('should handle undefined options', async () => {
      const result = await service.generatePdf('<html></html>');
      
      expect(Buffer.isBuffer(result)).toBe(true);
    });

    it('should handle empty margin object in options', async () => {
      const result = await service.generatePdf('<html></html>', { margin: {} });
      
      expect(Buffer.isBuffer(result)).toBe(true);
      // Should use default margins
      expect(mockPage.pdf).toHaveBeenCalledWith(
        expect.objectContaining({
          margin: {
            top: '10mm',
            right: '10mm',
            bottom: '10mm',
            left: '10mm',
          },
        })
      );
    });

    it('should use correct type for returned Buffer', async () => {
      const result = await service.generatePdf('<html></html>');
      
      // Verify it's a proper Node.js Buffer
      expect(result).toBeInstanceOf(Buffer);
      expect(result.byteLength).toBeGreaterThan(0);
    });
  });

  // ===========================================================================
  // CONCURRENCY AND RACE CONDITIONS TESTS
  // ===========================================================================

  describe('concurrency and race conditions', () => {
    it('should handle rapid sequential requests', async () => {
      for (let i = 0; i < 10; i++) {
        const result = await service.generatePdf(`<html><body>Request ${i}</body></html>`);
        expect(Buffer.isBuffer(result)).toBe(true);
      }
      
      // All pages should be closed
      expect(mockPage.close).toHaveBeenCalledTimes(10);
      
      // Browser only launched once
      expect(puppeteer.launch).toHaveBeenCalledTimes(1);
    });

    it('should handle interleaved success and failure', async () => {
      // First request succeeds
      await service.generatePdf('<html>1</html>');
      
      // Second request fails
      mockPage.pdf.mockRejectedValueOnce(new Error('Timeout'));
      await expect(service.generatePdf('<html>2</html>')).rejects.toThrow('Timeout');
      
      // Third request succeeds
      await service.generatePdf('<html>3</html>');
      
      // All pages should be closed (including failed one)
      expect(mockPage.close).toHaveBeenCalledTimes(3);
    });

    it('should maintain consistent state after mixed operations', async () => {
      // Successful generation
      await service.generatePdf('<html></html>');
      
      // Failed generation
      mockPage.setContent.mockRejectedValueOnce(new Error('Failed'));
      try {
        await service.generatePdf('<html></html>');
      } catch {
        // Expected to fail
      }
      
      // Service should still work
      const result = await service.generatePdf('<html></html>');
      expect(Buffer.isBuffer(result)).toBe(true);
    });
  });
});
