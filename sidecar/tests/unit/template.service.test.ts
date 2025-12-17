/**
 * Unit Tests for TemplateService
 *
 * Comprehensive unit tests for the Handlebars template service that handles:
 * - Template loading from filesystem with caching
 * - Partial registration (header, footer, line-items)
 * - CSS stylesheet loading
 * - HTML rendering from templates and business data
 *
 * Uses Vitest with mocking for filesystem operations and logger dependencies
 * to enable true unit testing in isolation from external resources.
 *
 * @module tests/unit/template.service.test
 * @see sidecar/src/services/template.service.ts
 * @see Agent Action Plan Section 0.3.1, 0.3.2
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { ReportType } from '../../src/contracts/request.schema.js';
import type { BaseDocumentData } from '../../src/contracts/domain.types.js';

// =============================================================================
// MOCK DECLARATIONS (MUST BE BEFORE IMPORTS)
// =============================================================================

/**
 * Mock for fs/promises module.
 * Controls template file loading behavior in tests.
 * Using vi.hoisted() to ensure the mock is available before hoisting.
 */
const { mockReadFile } = vi.hoisted(() => {
  return {
    mockReadFile: vi.fn(),
  };
});

vi.mock('fs/promises', () => ({
  readFile: mockReadFile,
}));

/**
 * Mock for Pino logger.
 * Prevents actual console output during tests and enables log assertion verification.
 */
vi.mock('../../src/utils/logger.js', () => ({
  logger: {
    trace: vi.fn(),
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    fatal: vi.fn(),
    child: vi.fn(() => ({
      trace: vi.fn(),
      debug: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
      fatal: vi.fn(),
    })),
  },
}));

/**
 * Mock for config module.
 * Provides test configuration values.
 */
vi.mock('../../src/config.js', () => ({
  config: {
    nodeEnv: 'test',
    logLevel: 'info',
    port: 3000,
    apiKey: 'test-api-key',
    secretKey: 'test-secret-key',
    rateLimitMax: 100,
    rateLimitWindow: 60000,
  },
}));

// =============================================================================
// IMPORT AFTER MOCKS
// =============================================================================

// Import TemplateService after mocks are set up
import { TemplateService } from '../../src/services/template.service.js';
import { logger } from '../../src/utils/logger.js';

// =============================================================================
// MOCK TEMPLATE CONTENT
// =============================================================================

/**
 * Mock invoice template content (Handlebars format).
 * Simplified template for testing template loading and rendering.
 */
const MOCK_INVOICE_TEMPLATE = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Invoice - {{data.metadata.number}}</title>
  <style>{{{css}}}</style>
</head>
<body>
  <div class="header">
    {{> header}}
  </div>
  <h1>Invoice</h1>
  <div class="company">{{data.company.name}}</div>
  <div class="partner">{{data.partner.name}}</div>
  <div class="document-number">{{data.metadata.number}}</div>
  <div class="document-date">{{formatDate data.metadata.date}}</div>
  <table class="line-items">
    {{> line-items}}
  </table>
  <div class="totals">
    <div class="subtotal">{{formatCurrency data.totals.subtotal data.totals.currency_symbol}}</div>
    <div class="tax">{{formatCurrency data.totals.tax_amount data.totals.currency_symbol}}</div>
    <div class="total">{{formatCurrency data.totals.total data.totals.currency_symbol}}</div>
  </div>
  <div class="footer">
    {{> footer}}
  </div>
  <div class="language">{{language}}</div>
</body>
</html>`;

/**
 * Mock quote template content (Handlebars format).
 */
const MOCK_QUOTE_TEMPLATE = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Quote - {{data.metadata.number}}</title>
  <style>{{{css}}}</style>
</head>
<body>
  <div class="header">
    {{> header}}
  </div>
  <h1>Quote</h1>
  <div class="company">{{data.company.name}}</div>
  <div class="partner">{{data.partner.name}}</div>
  <div class="document-number">{{data.metadata.number}}</div>
  <div class="document-date">{{formatDate data.metadata.date}}</div>
  {{#if data.metadata.salesperson}}
  <div class="salesperson">{{data.metadata.salesperson}}</div>
  {{/if}}
  <table class="line-items">
    {{> line-items}}
  </table>
  <div class="totals">
    <div class="subtotal">{{formatCurrency data.totals.subtotal data.totals.currency_symbol}}</div>
    <div class="total">{{formatCurrency data.totals.total data.totals.currency_symbol}}</div>
  </div>
  <div class="footer">
    {{> footer}}
  </div>
  <div class="language">{{language}}</div>
</body>
</html>`;

/**
 * Mock delivery slip template content (Handlebars format).
 * Note: Delivery slips show quantities only, no pricing (per Section 0.8.5).
 */
const MOCK_DELIVERY_SLIP_TEMPLATE = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Delivery Slip - {{data.metadata.number}}</title>
  <style>{{{css}}}</style>
</head>
<body>
  <div class="header">
    {{> header}}
  </div>
  <h1>Delivery Slip</h1>
  <div class="company">{{data.company.name}}</div>
  <div class="partner">{{data.partner.name}}</div>
  <div class="document-number">{{data.metadata.number}}</div>
  <div class="document-date">{{formatDate data.metadata.date}}</div>
  <table class="line-items">
    {{#each data.lines}}
    <tr>
      <td>{{this.product_name}}</td>
      <td>{{formatNumber this.quantity 0}}</td>
    </tr>
    {{/each}}
  </table>
  <div class="footer">
    {{> footer}}
  </div>
  <div class="language">{{language}}</div>
</body>
</html>`;

/**
 * Mock header partial content.
 */
const MOCK_HEADER_PARTIAL = `<header class="document-header">
  <div class="company-info">
    <h2>{{data.company.name}}</h2>
    {{#if data.company.street}}<p>{{data.company.street}}</p>{{/if}}
    {{#if data.company.city}}<p>{{data.company.city}}{{#if data.company.zip}}, {{data.company.zip}}{{/if}}</p>{{/if}}
  </div>
</header>`;

/**
 * Mock footer partial content.
 */
const MOCK_FOOTER_PARTIAL = `<footer class="document-footer">
  <div class="footer-content">
    {{#if data.metadata.notes}}<p class="notes">{{data.metadata.notes}}</p>{{/if}}
    <p class="copyright">© {{currentYear}} {{data.company.name}}</p>
  </div>
</footer>`;

/**
 * Mock line-items partial content.
 */
const MOCK_LINE_ITEMS_PARTIAL = `<tbody>
  {{#each data.lines}}
  <tr class="line-item" data-sequence="{{this.sequence}}">
    <td class="product-name">{{this.product_name}}</td>
    {{#if this.description}}<td class="description">{{this.description}}</td>{{/if}}
    <td class="quantity">{{formatNumber this.quantity 2}}</td>
    <td class="uom">{{this.uom}}</td>
    <td class="unit-price">{{formatCurrency this.unit_price ../data.totals.currency_symbol}}</td>
    <td class="subtotal">{{formatCurrency this.subtotal ../data.totals.currency_symbol}}</td>
  </tr>
  {{/each}}
</tbody>`;

/**
 * Mock CSS content for PDF styling.
 */
const MOCK_CSS_CONTENT = `
/* PDF Styles */
body {
  font-family: Arial, sans-serif;
  margin: 0;
  padding: 20px;
}
.header { margin-bottom: 20px; }
.footer { margin-top: 20px; border-top: 1px solid #ccc; padding-top: 10px; }
table { width: 100%; border-collapse: collapse; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
@media print {
  body { margin: 0; }
  .page-break { page-break-after: always; }
}
`;

// =============================================================================
// MOCK DOCUMENT DATA FIXTURES
// =============================================================================

/**
 * Creates mock invoice document data for testing.
 * Includes all required fields for BaseDocumentData.
 */
const createMockInvoiceData = (): BaseDocumentData => ({
  company: {
    name: 'Test Company Inc.',
    street: '123 Business Ave',
    city: 'San Francisco',
    state: 'CA',
    zip: '94102',
    country: 'United States',
    email: 'info@testcompany.com',
    phone: '+1 (555) 123-4567',
    vat: 'US123456789',
  },
  partner: {
    name: 'Test Customer LLC',
    street: '456 Customer Lane',
    city: 'Los Angeles',
    state: 'CA',
    zip: '90001',
    country: 'United States',
    email: 'buyer@testcustomer.com',
  },
  lines: [
    {
      sequence: 1,
      product_name: 'Widget Pro',
      description: 'Professional grade widget with extended warranty',
      quantity: 10,
      uom: 'Units',
      unit_price: 99.99,
      discount: 5,
      tax_names: ['VAT 20%'],
      subtotal: 949.91,
    },
    {
      sequence: 2,
      product_name: 'Gadget Plus',
      description: 'Enhanced gadget with premium features',
      quantity: 5,
      uom: 'Units',
      unit_price: 149.99,
      discount: 0,
      subtotal: 749.95,
    },
  ],
  totals: {
    subtotal: 1699.86,
    tax_amount: 339.97,
    total: 2039.83,
    amount_paid: 0,
    amount_due: 2039.83,
    currency_symbol: '$',
    tax_lines: [
      { name: 'VAT 20%', base: 1699.86, amount: 339.97 },
    ],
  },
  metadata: {
    number: 'INV-2024-001234',
    date: '2024-01-15',
    due_date: '2024-02-15',
    reference: 'PO-CUST-5678',
    salesperson: 'Jane Smith',
    payment_terms: 'Net 30',
    notes: 'Thank you for your business!',
  },
});

/**
 * Creates mock quote document data for testing.
 */
const createMockQuoteData = (): BaseDocumentData => ({
  company: {
    name: 'Quote Provider Corp',
    street: '789 Sales Blvd',
    city: 'New York',
    state: 'NY',
    zip: '10001',
    country: 'United States',
  },
  partner: {
    name: 'Potential Client Inc',
    street: '321 Prospect Ave',
    city: 'Chicago',
    state: 'IL',
    zip: '60601',
    country: 'United States',
  },
  lines: [
    {
      sequence: 1,
      product_name: 'Consulting Service',
      description: 'Professional consulting - 8 hours',
      quantity: 8,
      uom: 'Hours',
      unit_price: 150.00,
      discount: 0,
      subtotal: 1200.00,
    },
  ],
  totals: {
    subtotal: 1200.00,
    tax_amount: 0,
    total: 1200.00,
    currency_symbol: '$',
  },
  metadata: {
    number: 'QT-2024-000123',
    date: '2024-01-10',
    salesperson: 'John Doe',
    notes: 'Quote valid for 30 days',
  },
});

/**
 * Creates mock delivery slip document data for testing.
 * Note: unit_price and subtotal are 0 per Section 0.8.5.
 */
const createMockDeliverySlipData = (): BaseDocumentData => ({
  company: {
    name: 'Warehouse Corp',
    street: '999 Logistics Way',
    city: 'Dallas',
    state: 'TX',
    zip: '75201',
    country: 'United States',
  },
  partner: {
    name: 'Delivery Recipient Co',
    street: '555 Receiving Dock',
    city: 'Houston',
    state: 'TX',
    zip: '77001',
    country: 'United States',
  },
  lines: [
    {
      sequence: 1,
      product_name: 'Shipped Item A',
      quantity: 100,
      uom: 'Units',
      unit_price: 0, // Delivery slips don't show pricing
      discount: 0,
      subtotal: 0, // Delivery slips don't show pricing
    },
    {
      sequence: 2,
      product_name: 'Shipped Item B',
      quantity: 50,
      uom: 'Boxes',
      unit_price: 0,
      discount: 0,
      subtotal: 0,
    },
  ],
  totals: {
    subtotal: 0,
    tax_amount: 0,
    total: 0,
    currency_symbol: '$',
  },
  metadata: {
    number: 'WH/OUT/00001',
    date: '2024-01-20',
    reference: 'SO-2024-001',
    notes: 'Handle with care',
  },
});

// =============================================================================
// FILESYSTEM MOCK HELPERS
// =============================================================================

/**
 * Sets up mock filesystem responses for template and partial files.
 * Maps file paths to their mock content.
 */
const setupFilesystemMocks = () => {
  mockReadFile.mockImplementation((filePath: string) => {
    // Normalize path separators for cross-platform compatibility
    const normalizedPath = filePath.replace(/\\/g, '/');

    // Template files
    if (normalizedPath.endsWith('invoice.hbs')) {
      return Promise.resolve(MOCK_INVOICE_TEMPLATE);
    }
    if (normalizedPath.endsWith('quote.hbs')) {
      return Promise.resolve(MOCK_QUOTE_TEMPLATE);
    }
    if (normalizedPath.endsWith('delivery_slip.hbs')) {
      return Promise.resolve(MOCK_DELIVERY_SLIP_TEMPLATE);
    }

    // Partial files
    if (normalizedPath.endsWith('partials/header.hbs')) {
      return Promise.resolve(MOCK_HEADER_PARTIAL);
    }
    if (normalizedPath.endsWith('partials/footer.hbs')) {
      return Promise.resolve(MOCK_FOOTER_PARTIAL);
    }
    if (normalizedPath.endsWith('partials/line-items.hbs')) {
      return Promise.resolve(MOCK_LINE_ITEMS_PARTIAL);
    }

    // CSS file
    if (normalizedPath.endsWith('pdf.css')) {
      return Promise.resolve(MOCK_CSS_CONTENT);
    }

    // Unknown file - reject with ENOENT error
    const error = new Error(`ENOENT: no such file or directory, open '${filePath}'`);
    (error as NodeJS.ErrnoException).code = 'ENOENT';
    return Promise.reject(error);
  });
};

// =============================================================================
// TEST SUITES
// =============================================================================

describe('TemplateService', () => {
  let service: TemplateService;

  beforeEach(() => {
    // Clear all mocks before each test
    vi.clearAllMocks();

    // Set up default filesystem mocks
    setupFilesystemMocks();

    // Create fresh service instance for test isolation
    service = new TemplateService();
  });

  afterEach(() => {
    // Reset mocks after each test
    vi.resetAllMocks();
  });

  // ===========================================================================
  // INSTANTIATION TESTS
  // ===========================================================================

  describe('instantiation', () => {
    it('should create a TemplateService instance', () => {
      expect(service).toBeDefined();
      expect(service).toBeInstanceOf(TemplateService);
    });

    it('should expose render method', () => {
      expect(typeof service.render).toBe('function');
    });

    it('should expose hasTemplate method', () => {
      expect(typeof service.hasTemplate).toBe('function');
    });

    it('should expose clearCache method', () => {
      expect(typeof service.clearCache).toBe('function');
    });

    it('should register Handlebars helpers during construction', () => {
      // Verify helpers are registered by checking logger was called
      expect(logger.debug).toHaveBeenCalledWith('Handlebars helpers registered');
    });
  });

  // ===========================================================================
  // LOAD TEMPLATE TESTS
  // ===========================================================================

  describe('loadTemplate (via render)', () => {
    it('should successfully load invoice template', async () => {
      const data = createMockInvoiceData();
      const html = await service.render('invoice', data, 'en_US');

      expect(html).toBeDefined();
      expect(html).toContain('<!DOCTYPE html>');
      expect(html).toContain('Invoice');
    });

    it('should successfully load quote template', async () => {
      const data = createMockQuoteData();
      const html = await service.render('quote', data, 'en_US');

      expect(html).toBeDefined();
      expect(html).toContain('<!DOCTYPE html>');
      expect(html).toContain('Quote');
    });

    it('should successfully load delivery_slip template', async () => {
      const data = createMockDeliverySlipData();
      const html = await service.render('delivery_slip', data, 'en_US');

      expect(html).toBeDefined();
      expect(html).toContain('<!DOCTYPE html>');
      expect(html).toContain('Delivery Slip');
    });

    it('should cache template after first load', async () => {
      const data = createMockInvoiceData();

      // First render
      await service.render('invoice', data, 'en_US');
      const firstCallCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('invoice.hbs')
      ).length;

      // Second render (should use cache)
      await service.render('invoice', data, 'en_US');
      const secondCallCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('invoice.hbs')
      ).length;

      // Template file should only be read once (cached)
      expect(secondCallCount).toBe(firstCallCount);

      // Verify cache hit logged
      expect(logger.debug).toHaveBeenCalledWith(
        expect.objectContaining({ reportType: 'invoice' }),
        'Using cached template'
      );
    });

    it('should throw error when template file not found', async () => {
      // Override mock to simulate missing template
      mockReadFile.mockImplementation((filePath: string) => {
        const normalizedPath = filePath.replace(/\\/g, '/');

        // Return partials and CSS normally
        if (normalizedPath.endsWith('partials/header.hbs')) {
          return Promise.resolve(MOCK_HEADER_PARTIAL);
        }
        if (normalizedPath.endsWith('partials/footer.hbs')) {
          return Promise.resolve(MOCK_FOOTER_PARTIAL);
        }
        if (normalizedPath.endsWith('partials/line-items.hbs')) {
          return Promise.resolve(MOCK_LINE_ITEMS_PARTIAL);
        }
        if (normalizedPath.endsWith('pdf.css')) {
          return Promise.resolve(MOCK_CSS_CONTENT);
        }

        // Reject all template files
        const error = new Error(`ENOENT: no such file or directory, open '${filePath}'`);
        (error as NodeJS.ErrnoException).code = 'ENOENT';
        return Promise.reject(error);
      });

      const data = createMockInvoiceData();

      await expect(service.render('invoice', data, 'en_US'))
        .rejects.toThrow('Template not found: invoice');
    });

    it('should throw error for unknown report type', async () => {
      const data = createMockInvoiceData();
      const unknownType = 'unknown_report' as ReportType;

      await expect(service.render(unknownType, data, 'en_US'))
        .rejects.toThrow('Unknown report type: unknown_report');

      // Verify error was logged
      expect(logger.error).toHaveBeenCalledWith(
        expect.objectContaining({ reportType: 'unknown_report' }),
        'Unknown report type requested'
      );
    });
  });

  // ===========================================================================
  // REGISTER PARTIALS TESTS
  // ===========================================================================

  describe('registerPartials (via render)', () => {
    it('should load header partial from filesystem', async () => {
      const data = createMockInvoiceData();
      await service.render('invoice', data, 'en_US');

      // Verify header partial was requested
      const headerCalls = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('header.hbs')
      );
      expect(headerCalls.length).toBeGreaterThan(0);
    });

    it('should load footer partial from filesystem', async () => {
      const data = createMockInvoiceData();
      await service.render('invoice', data, 'en_US');

      // Verify footer partial was requested
      const footerCalls = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('footer.hbs')
      );
      expect(footerCalls.length).toBeGreaterThan(0);
    });

    it('should load line-items partial from filesystem', async () => {
      const data = createMockInvoiceData();
      await service.render('invoice', data, 'en_US');

      // Verify line-items partial was requested
      const lineItemsCalls = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('line-items.hbs')
      );
      expect(lineItemsCalls.length).toBeGreaterThan(0);
    });

    it('should register partials only once (subsequent calls skip)', async () => {
      const data = createMockInvoiceData();

      // First render - should register partials
      await service.render('invoice', data, 'en_US');

      // Count partial file reads after first render
      const firstRenderPartialCalls = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('partials/')
      ).length;

      // Second render - should skip partial registration
      await service.render('quote', createMockQuoteData(), 'en_US');

      // Count partial file reads after second render
      const secondRenderPartialCalls = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('partials/')
      ).length;

      // Partials should not be loaded again (same count)
      expect(secondRenderPartialCalls).toBe(firstRenderPartialCalls);
    });

    it('should throw error when partial file not found', async () => {
      // Override mock to simulate missing partial
      mockReadFile.mockImplementation((filePath: string) => {
        const normalizedPath = filePath.replace(/\\/g, '/');

        // Return templates and CSS normally
        if (normalizedPath.endsWith('invoice.hbs')) {
          return Promise.resolve(MOCK_INVOICE_TEMPLATE);
        }
        if (normalizedPath.endsWith('pdf.css')) {
          return Promise.resolve(MOCK_CSS_CONTENT);
        }

        // Reject all partial files
        if (normalizedPath.includes('partials/')) {
          const error = new Error(`ENOENT: no such file or directory, open '${filePath}'`);
          (error as NodeJS.ErrnoException).code = 'ENOENT';
          return Promise.reject(error);
        }

        return Promise.resolve('');
      });

      const data = createMockInvoiceData();

      await expect(service.render('invoice', data, 'en_US'))
        .rejects.toThrow(/Failed to load partial/);
    });

    it('should log successful partial registration', async () => {
      const data = createMockInvoiceData();
      await service.render('invoice', data, 'en_US');

      expect(logger.info).toHaveBeenCalledWith('Registering Handlebars partials');
      expect(logger.info).toHaveBeenCalledWith(
        expect.objectContaining({ partialCount: 3 }),
        'All partials registered successfully'
      );
    });
  });

  // ===========================================================================
  // LOAD STYLES TESTS
  // ===========================================================================

  describe('loadStyles (via render)', () => {
    it('should load CSS file successfully', async () => {
      const data = createMockInvoiceData();
      const html = await service.render('invoice', data, 'en_US');

      // Verify CSS was requested
      const cssCalls = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('pdf.css')
      );
      expect(cssCalls.length).toBeGreaterThan(0);

      // Verify CSS was included in rendered HTML
      expect(html).toContain('font-family: Arial');
    });

    it('should cache CSS after first load', async () => {
      const data = createMockInvoiceData();

      // First render
      await service.render('invoice', data, 'en_US');
      const firstCssCallCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('pdf.css')
      ).length;

      // Second render
      await service.render('quote', createMockQuoteData(), 'en_US');
      const secondCssCallCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('pdf.css')
      ).length;

      // CSS should only be loaded once
      expect(secondCssCallCount).toBe(firstCssCallCount);
    });

    it('should fallback to empty string on CSS load failure', async () => {
      // Override mock to simulate CSS load failure
      mockReadFile.mockImplementation((filePath: string) => {
        const normalizedPath = filePath.replace(/\\/g, '/');

        // Return everything except CSS
        if (normalizedPath.endsWith('invoice.hbs')) {
          return Promise.resolve(MOCK_INVOICE_TEMPLATE);
        }
        if (normalizedPath.endsWith('partials/header.hbs')) {
          return Promise.resolve(MOCK_HEADER_PARTIAL);
        }
        if (normalizedPath.endsWith('partials/footer.hbs')) {
          return Promise.resolve(MOCK_FOOTER_PARTIAL);
        }
        if (normalizedPath.endsWith('partials/line-items.hbs')) {
          return Promise.resolve(MOCK_LINE_ITEMS_PARTIAL);
        }

        // Fail CSS load
        if (normalizedPath.endsWith('pdf.css')) {
          const error = new Error(`ENOENT: no such file or directory, open '${filePath}'`);
          (error as NodeJS.ErrnoException).code = 'ENOENT';
          return Promise.reject(error);
        }

        return Promise.resolve('');
      });

      const data = createMockInvoiceData();
      const html = await service.render('invoice', data, 'en_US');

      // Should still render without CSS
      expect(html).toBeDefined();
      expect(html).toContain('<!DOCTYPE html>');

      // Verify warning was logged
      expect(logger.warn).toHaveBeenCalledWith(
        expect.objectContaining({ cssPath: expect.any(String) }),
        'Failed to load CSS styles, using empty stylesheet'
      );
    });
  });

  // ===========================================================================
  // RENDER METHOD TESTS
  // ===========================================================================

  describe('render', () => {
    it('should return HTML string for valid invoice data', async () => {
      const data = createMockInvoiceData();
      const html = await service.render('invoice', data, 'en_US');

      expect(typeof html).toBe('string');
      expect(html.length).toBeGreaterThan(0);
      expect(html).toContain('<!DOCTYPE html>');
      expect(html).toContain('</html>');
    });

    it('should return HTML string for valid quote data', async () => {
      const data = createMockQuoteData();
      const html = await service.render('quote', data, 'en_US');

      expect(typeof html).toBe('string');
      expect(html.length).toBeGreaterThan(0);
      expect(html).toContain('<!DOCTYPE html>');
      expect(html).toContain('</html>');
    });

    it('should return HTML string for valid delivery_slip data', async () => {
      const data = createMockDeliverySlipData();
      const html = await service.render('delivery_slip', data, 'en_US');

      expect(typeof html).toBe('string');
      expect(html.length).toBeGreaterThan(0);
      expect(html).toContain('<!DOCTYPE html>');
      expect(html).toContain('</html>');
    });

    it('should include company name in rendered HTML', async () => {
      const data = createMockInvoiceData();
      const html = await service.render('invoice', data, 'en_US');

      expect(html).toContain(data.company.name);
    });

    it('should include partner name in rendered HTML', async () => {
      const data = createMockInvoiceData();
      const html = await service.render('invoice', data, 'en_US');

      expect(html).toContain(data.partner.name);
    });

    it('should include document number in rendered HTML', async () => {
      const data = createMockInvoiceData();
      const html = await service.render('invoice', data, 'en_US');

      expect(html).toContain(data.metadata.number);
    });

    it('should include CSS in rendered HTML', async () => {
      const data = createMockInvoiceData();
      const html = await service.render('invoice', data, 'en_US');

      expect(html).toContain('<style>');
      expect(html).toContain('font-family');
    });

    it('should include language in context', async () => {
      const data = createMockInvoiceData();
      const html = await service.render('invoice', data, 'en_US');

      expect(html).toContain('en_US');
    });

    it('should use default language when not specified', async () => {
      const data = createMockInvoiceData();
      const html = await service.render('invoice', data);

      // Default language is 'en_US'
      expect(html).toContain('en_US');
    });

    it('should throw error for unknown report type', async () => {
      const data = createMockInvoiceData();

      await expect(service.render('invalid' as ReportType, data, 'en_US'))
        .rejects.toThrow('Unknown report type');
    });

    it('should log template rendering', async () => {
      const data = createMockInvoiceData();
      await service.render('invoice', data, 'en_US');

      expect(logger.debug).toHaveBeenCalledWith(
        expect.objectContaining({
          reportType: 'invoice',
          language: 'en_US',
        }),
        'Rendering template'
      );

      expect(logger.debug).toHaveBeenCalledWith(
        expect.objectContaining({
          reportType: 'invoice',
          htmlLength: expect.any(Number),
        }),
        'Template rendered successfully'
      );
    });

    it('should render salesperson when provided', async () => {
      const data = createMockQuoteData();
      data.metadata.salesperson = 'Jane Smith';
      const html = await service.render('quote', data, 'en_US');

      expect(html).toContain('Jane Smith');
    });
  });

  // ===========================================================================
  // HAS TEMPLATE TESTS
  // ===========================================================================

  describe('hasTemplate', () => {
    it('should return true for invoice report type', () => {
      expect(service.hasTemplate('invoice')).toBe(true);
    });

    it('should return true for quote report type', () => {
      expect(service.hasTemplate('quote')).toBe(true);
    });

    it('should return true for delivery_slip report type', () => {
      expect(service.hasTemplate('delivery_slip')).toBe(true);
    });

    it('should return false for unknown report type', () => {
      expect(service.hasTemplate('unknown')).toBe(false);
    });

    it('should return false for empty string', () => {
      expect(service.hasTemplate('')).toBe(false);
    });

    it('should return false for null', () => {
      expect(service.hasTemplate(null as unknown as string)).toBe(false);
    });

    it('should return false for undefined', () => {
      expect(service.hasTemplate(undefined as unknown as string)).toBe(false);
    });

    it('should be case-sensitive', () => {
      expect(service.hasTemplate('Invoice')).toBe(false);
      expect(service.hasTemplate('INVOICE')).toBe(false);
      expect(service.hasTemplate('QUOTE')).toBe(false);
    });
  });

  // ===========================================================================
  // CLEAR CACHE TESTS
  // ===========================================================================

  describe('clearCache', () => {
    it('should clear template cache', async () => {
      const data = createMockInvoiceData();

      // First render - loads template
      await service.render('invoice', data, 'en_US');
      const initialReadCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('invoice.hbs')
      ).length;

      // Clear cache
      service.clearCache();

      // Second render - should reload template
      await service.render('invoice', data, 'en_US');
      const afterClearReadCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('invoice.hbs')
      ).length;

      // Template should be read again after cache clear
      expect(afterClearReadCount).toBeGreaterThan(initialReadCount);
    });

    it('should clear CSS cache', async () => {
      const data = createMockInvoiceData();

      // First render - loads CSS
      await service.render('invoice', data, 'en_US');
      const initialCssReadCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('pdf.css')
      ).length;

      // Clear cache
      service.clearCache();

      // Second render - should reload CSS
      await service.render('invoice', data, 'en_US');
      const afterClearCssReadCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('pdf.css')
      ).length;

      // CSS should be read again after cache clear
      expect(afterClearCssReadCount).toBeGreaterThan(initialCssReadCount);
    });

    it('should reset partials registered flag', async () => {
      const data = createMockInvoiceData();

      // First render - registers partials
      await service.render('invoice', data, 'en_US');
      const initialPartialReadCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('partials/')
      ).length;

      // Clear cache
      service.clearCache();

      // Second render - should re-register partials
      await service.render('invoice', data, 'en_US');
      const afterClearPartialReadCount = mockReadFile.mock.calls.filter(
        call => (call[0] as string).includes('partials/')
      ).length;

      // Partials should be read again after cache clear
      expect(afterClearPartialReadCount).toBeGreaterThan(initialPartialReadCount);
    });

    it('should log cache clear action', () => {
      service.clearCache();

      expect(logger.info).toHaveBeenCalledWith(
        expect.objectContaining({ clearedTemplates: 0 }),
        'Template cache cleared'
      );
    });

    it('should be callable multiple times without error', () => {
      expect(() => {
        service.clearCache();
        service.clearCache();
        service.clearCache();
      }).not.toThrow();
    });

    it('should work correctly with fresh instance', () => {
      const freshService = new TemplateService();

      // Should not throw even with empty cache
      expect(() => freshService.clearCache()).not.toThrow();
    });
  });

  // ===========================================================================
  // HANDLEBARS HELPERS TESTS
  // ===========================================================================

  describe('Handlebars helpers', () => {
    describe('formatCurrency helper', () => {
      it('should format currency values in templates', async () => {
        const data = createMockInvoiceData();
        const html = await service.render('invoice', data, 'en_US');

        // Should contain formatted currency values
        expect(html).toContain('$');
      });

      it('should handle zero values', async () => {
        const data = createMockDeliverySlipData();
        const html = await service.render('delivery_slip', data, 'en_US');

        // Should render without errors even with zero values
        expect(html).toBeDefined();
      });
    });

    describe('formatNumber helper', () => {
      it('should format quantity values in templates', async () => {
        const data = createMockDeliverySlipData();
        const html = await service.render('delivery_slip', data, 'en_US');

        // Should contain quantity from line items
        expect(html).toContain('100');
        expect(html).toContain('50');
      });
    });

    describe('formatDate helper', () => {
      it('should format date values in templates', async () => {
        const data = createMockInvoiceData();
        const html = await service.render('invoice', data, 'en_US');

        // Should contain date from metadata
        expect(html).toContain(data.metadata.date);
      });
    });

    describe('conditional helpers (eq, neq)', () => {
      it('should support conditional rendering with eq helper', async () => {
        const data = createMockQuoteData();
        data.metadata.salesperson = 'Test Salesperson';
        const html = await service.render('quote', data, 'en_US');

        // Salesperson should be rendered when present
        expect(html).toContain('Test Salesperson');
      });
    });
  });

  // ===========================================================================
  // INTEGRATION BEHAVIOR TESTS
  // ===========================================================================

  describe('integration behavior', () => {
    it('should handle multiple sequential renders', async () => {
      const invoiceData = createMockInvoiceData();
      const quoteData = createMockQuoteData();
      const deliveryData = createMockDeliverySlipData();

      const invoiceHtml = await service.render('invoice', invoiceData, 'en_US');
      const quoteHtml = await service.render('quote', quoteData, 'en_US');
      const deliveryHtml = await service.render('delivery_slip', deliveryData, 'en_US');

      expect(invoiceHtml).toContain('Invoice');
      expect(quoteHtml).toContain('Quote');
      expect(deliveryHtml).toContain('Delivery Slip');
    });

    it('should produce different output for different data', async () => {
      const data1 = createMockInvoiceData();
      data1.company.name = 'Company Alpha';

      const data2 = createMockInvoiceData();
      data2.company.name = 'Company Beta';

      const html1 = await service.render('invoice', data1, 'en_US');
      const html2 = await service.render('invoice', data2, 'en_US');

      expect(html1).toContain('Company Alpha');
      expect(html1).not.toContain('Company Beta');

      expect(html2).toContain('Company Beta');
      expect(html2).not.toContain('Company Alpha');
    });

    it('should produce consistent output for same data', async () => {
      const data = createMockInvoiceData();

      const html1 = await service.render('invoice', data, 'en_US');
      const html2 = await service.render('invoice', data, 'en_US');

      expect(html1).toBe(html2);
    });
  });
});
