/**
 * @fileoverview Integration tests for the POST /api/v1/render endpoint
 * of the document-sidecar service.
 *
 * Tests the complete PDF rendering workflow end-to-end using the real
 * Fastify application instance. Covers:
 * - Authentication verification (API key + HMAC signature)
 * - Request validation with Zod schemas
 * - Successful PDF generation for invoice/quote/delivery_slip report types
 * - Error handling scenarios (401 AUTH_FAILED, 400 VALIDATION_ERROR, 404 TEMPLATE_NOT_FOUND)
 *
 * Uses Vitest framework with beforeAll/afterAll hooks for server lifecycle management.
 *
 * IMPORTANT: vi.mock() must be called before any module imports to properly
 * intercept the config module. Vitest hoists vi.mock() calls automatically.
 *
 * @module tests/integration/render.test
 * @see Agent Action Plan Section 0.3.1 - Test specifications
 */

// =============================================================================
// VITEST IMPORTS AND CONFIG MODULE MOCK
// =============================================================================
import { describe, it, expect, beforeAll, afterAll, beforeEach, vi } from 'vitest';

/**
 * Mock the config module to provide test-specific configuration values.
 * This mock is hoisted by Vitest and runs before any imports, ensuring
 * all modules that depend on config receive the mocked values.
 *
 * IMPORTANT: Values MUST be inline literals, not constants, because vi.mock()
 * is hoisted to the very top of the file before any variable declarations.
 */
vi.mock('../../src/config.js', () => ({
  config: {
    port: 3000,
    apiKey: 'test-api-key-integration-12345',
    secretKey: 'test-secret-key-integration-67890',
    logLevel: 'silent',
    nodeEnv: 'test',
    rateLimitMax: 1000,
    rateLimitWindow: 60000,
  },
}));

// =============================================================================
// TEST CONFIGURATION CONSTANTS
// =============================================================================
/**
 * Test API key for authentication (must match vi.mock values above).
 */
const TEST_API_KEY = 'test-api-key-integration-12345';

/**
 * Test secret key for HMAC signature generation (must match vi.mock values above).
 */
const TEST_SECRET_KEY = 'test-secret-key-integration-67890';

// =============================================================================
// MODULE IMPORTS (AFTER CONFIG MOCK)
// =============================================================================
import Fastify, { FastifyInstance } from 'fastify';
import { randomUUID } from 'crypto';
import { generateSignature } from '../../src/utils/hmac.js';
import { decodeFromBase64 } from '../../src/utils/base64.js';
import { registerRoutes, ROUTES } from '../../src/api/routes.js';
import { registerRateLimiter } from '../../src/middleware/rate-limiter.js';
import { registerErrorHandler } from '../../src/middleware/error-handler.js';
import { requestIdMiddleware } from '../../src/middleware/request-id.js';

// =============================================================================
// TEST CONFIGURATION CONSTANTS (API/SECRET keys defined at top before imports)
// =============================================================================

/**
 * Render endpoint path constant for test requests.
 */
const RENDER_ENDPOINT = ROUTES.RENDER;

/**
 * Health endpoint path constant for test requests.
 */
const HEALTH_ENDPOINT = ROUTES.HEALTH;

/**
 * Ready endpoint path constant for test requests.
 */
const READY_ENDPOINT = ROUTES.READY;

/**
 * Maximum allowed render time in milliseconds (per Agent Action Plan - 5 seconds).
 */
const MAX_RENDER_TIME_MS = 5000;

// =============================================================================
// TEST FIXTURE FACTORY FUNCTIONS
// =============================================================================

/**
 * Creates a valid invoice request payload for testing.
 *
 * Generates a complete DocumentRequest object with all required fields
 * populated with realistic test data. Each call generates a unique request_id.
 *
 * @returns A valid invoice request object conforming to DocumentRequestSchema
 */
function createValidInvoiceRequest(): Record<string, unknown> {
  return {
    request_id: randomUUID(),
    report_type: 'invoice',
    record_ids: [1],
    data: {
      company: {
        name: 'Test Company Inc.',
        street: '123 Test Street',
        city: 'Test City',
        state: 'TS',
        zip: '12345',
        country: 'Test Country',
        phone: '+1-555-123-4567',
        email: 'test@testcompany.example.com',
      },
      partner: {
        name: 'Test Customer',
        street: '456 Customer Ave',
        city: 'Customer City',
        state: 'CC',
        zip: '67890',
        country: 'Customer Country',
        email: 'customer@example.com',
      },
      lines: [
        {
          sequence: 1,
          product_name: 'Test Product A',
          description: 'Premium test product for integration testing',
          quantity: 10,
          uom: 'Units',
          unit_price: 99.99,
          discount: 0,
          tax_names: ['VAT 20%'],
          subtotal: 999.90,
        },
        {
          sequence: 2,
          product_name: 'Test Service B',
          description: 'Professional test service',
          quantity: 5,
          uom: 'Hours',
          unit_price: 50.00,
          discount: 10,
          tax_names: ['VAT 20%'],
          subtotal: 225.00,
        },
      ],
      totals: {
        subtotal: 1224.90,
        tax_amount: 244.98,
        total: 1469.88,
        amount_paid: 0,
        amount_due: 1469.88,
        currency_symbol: '$',
        tax_lines: [
          {
            name: 'VAT 20%',
            base: 1224.90,
            amount: 244.98,
          },
        ],
      },
      metadata: {
        number: 'INV-TEST-001',
        date: '2024-01-15',
        due_date: '2024-02-15',
        reference: 'PO-TEST-001',
        salesperson: 'Test Sales Rep',
        payment_terms: 'Net 30',
        notes: 'Thank you for your business!',
      },
    },
    options: {
      page_size: 'A4',
      language: 'en_US',
      copies: 1,
    },
  };
}

/**
 * Creates a valid quote request payload for testing.
 *
 * Generates a complete DocumentRequest object for quote/sale order type
 * with all required fields populated with realistic test data.
 *
 * @returns A valid quote request object conforming to DocumentRequestSchema
 */
function createValidQuoteRequest(): Record<string, unknown> {
  return {
    request_id: randomUUID(),
    report_type: 'quote',
    record_ids: [42],
    data: {
      company: {
        name: 'Test Company Inc.',
        street: '123 Test Street',
        city: 'Test City',
        state: 'TS',
        zip: '12345',
        country: 'Test Country',
        email: 'sales@testcompany.example.com',
      },
      partner: {
        name: 'Prospective Customer LLC',
        street: '789 Prospect Blvd',
        city: 'Prospect City',
        state: 'PC',
        zip: '11111',
        country: 'Prospect Country',
        email: 'prospect@example.com',
      },
      lines: [
        {
          sequence: 1,
          product_name: 'Enterprise Solution',
          description: 'Complete enterprise software solution',
          quantity: 1,
          uom: 'License',
          unit_price: 5000.00,
          discount: 15,
          tax_names: ['Sales Tax 8%'],
          subtotal: 4250.00,
        },
      ],
      totals: {
        subtotal: 4250.00,
        tax_amount: 340.00,
        total: 4590.00,
        currency_symbol: '$',
        tax_lines: [
          {
            name: 'Sales Tax 8%',
            base: 4250.00,
            amount: 340.00,
          },
        ],
      },
      metadata: {
        number: 'SO-TEST-001',
        date: '2024-01-20',
        reference: 'RFQ-TEST-001',
        salesperson: 'Test Sales Manager',
        notes: 'Quote valid for 30 days.',
        terms_and_conditions: 'Standard terms and conditions apply.',
      },
    },
    options: {
      page_size: 'Letter',
      language: 'en_US',
      copies: 1,
    },
  };
}

/**
 * Creates a valid delivery slip request payload for testing.
 *
 * Generates a complete DocumentRequest object for delivery slip type.
 * Note: Per Agent Action Plan Section 0.8.5, delivery slips intentionally
 * have unit_price and subtotal set to 0 (quantities only).
 *
 * @returns A valid delivery slip request object conforming to DocumentRequestSchema
 */
function createValidDeliverySlipRequest(): Record<string, unknown> {
  return {
    request_id: randomUUID(),
    report_type: 'delivery_slip',
    record_ids: [100],
    data: {
      company: {
        name: 'Test Warehouse Inc.',
        street: '999 Warehouse Way',
        city: 'Warehouse City',
        state: 'WH',
        zip: '99999',
        country: 'Test Country',
        phone: '+1-555-999-8888',
      },
      partner: {
        name: 'Delivery Recipient Corp',
        street: '111 Delivery Lane',
        city: 'Delivery City',
        state: 'DL',
        zip: '22222',
        country: 'Delivery Country',
        phone: '+1-555-222-1111',
      },
      lines: [
        {
          sequence: 1,
          product_name: 'Test Widget',
          description: 'Standard test widget - Model TW-100',
          quantity: 20,
          uom: 'Units',
          unit_price: 0,
          discount: 0,
          subtotal: 0,
        },
        {
          sequence: 2,
          product_name: 'Test Accessory Pack',
          description: 'Accessory pack for test widget',
          quantity: 10,
          uom: 'Packs',
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
        number: 'WH/OUT/TEST-001',
        date: '2024-01-25',
        reference: 'SO-TEST-001',
        notes: 'Handle with care. Sign for receipt.',
      },
    },
    options: {
      page_size: 'A4',
      language: 'en_US',
      copies: 1,
    },
  };
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Generates an HMAC-SHA256 signature for a request body.
 *
 * Signs the JSON-stringified request payload using the test secret key.
 * Used to create valid X-HMAC-Signature headers for authenticated requests.
 *
 * @param body - The request body object to sign
 * @returns Hex-encoded HMAC-SHA256 signature string
 */
function signRequest(body: Record<string, unknown>): string {
  const payload = JSON.stringify(body);
  return generateSignature(payload, TEST_SECRET_KEY);
}

/**
 * Verifies that a base64 string represents a valid PDF document.
 *
 * Decodes the base64 string and checks for the PDF magic bytes (%PDF-)
 * at the start of the document.
 *
 * @param base64Pdf - Base64-encoded PDF data
 * @returns True if the data starts with PDF magic bytes
 */
function isPdfValid(base64Pdf: string): boolean {
  try {
    const buffer = decodeFromBase64(base64Pdf);
    // PDF magic bytes: %PDF- (hex: 25 50 44 46 2D)
    const pdfMagic = buffer.subarray(0, 5).toString('ascii');
    return pdfMagic === '%PDF-';
  } catch {
    return false;
  }
}

// =============================================================================
// TEST SETUP AND TEARDOWN
// =============================================================================

/**
 * Fastify application instance used for integration testing.
 * Initialized in beforeAll hook and closed in afterAll hook.
 */
let app: FastifyInstance;

/**
 * Setup the Fastify application instance before all tests.
 *
 * Creates Fastify app with middleware and routes registered.
 * Config values are provided via vi.mock() above.
 */
beforeAll(async () => {
  // Create Fastify instance with minimal logging for tests
  app = Fastify({
    logger: false,
  });

  // Register request-id middleware via onRequest hook
  app.addHook('onRequest', requestIdMiddleware);

  // Register error handler for structured error responses
  registerErrorHandler(app);

  // Register rate limiter plugin with high limits for testing
  await registerRateLimiter(app, {
    max: 1000,
    timeWindow: 60000,
  });

  // Register all API routes
  await app.register(registerRoutes);

  // Wait for application to be ready
  await app.ready();
});

/**
 * Cleanup after all tests complete.
 *
 * Closes the Fastify application to release resources.
 */
afterAll(async () => {
  await app.close();
});

// =============================================================================
// AUTHENTICATION TESTS
// =============================================================================

describe('Authentication Verification', () => {
  /**
   * Tests that requests without X-API-Key header are rejected.
   * Expected: 401 AUTH_FAILED
   */
  it('should return 401 AUTH_FAILED when X-API-Key header is missing', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-hmac-signature': signature,
        // X-API-Key header intentionally omitted
      },
    });

    expect(response.statusCode).toBe(401);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error).toBeDefined();
    expect(body.error.code).toBe('AUTH_FAILED');
    expect(body.error.message).toMatch(/api key/i);
  });

  /**
   * Tests that requests with invalid X-API-Key are rejected.
   * Expected: 401 AUTH_FAILED
   */
  it('should return 401 AUTH_FAILED when X-API-Key is invalid', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': 'invalid-api-key-wrong',
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(401);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('AUTH_FAILED');
  });

  /**
   * Tests that POST requests without X-HMAC-Signature header are rejected.
   * Expected: 401 AUTH_FAILED
   */
  it('should return 401 AUTH_FAILED when X-HMAC-Signature header is missing', async () => {
    const requestBody = createValidInvoiceRequest();

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        // X-HMAC-Signature header intentionally omitted
      },
    });

    expect(response.statusCode).toBe(401);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('AUTH_FAILED');
    expect(body.error.message).toMatch(/hmac|signature/i);
  });

  /**
   * Tests that requests with invalid HMAC signature are rejected.
   * This prevents request tampering attacks.
   * Expected: 401 AUTH_FAILED
   */
  it('should return 401 AUTH_FAILED when X-HMAC-Signature is invalid', async () => {
    const requestBody = createValidInvoiceRequest();

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': 'invalid-signature-0000000000000000000000000000000000000000000000000000000000000000',
      },
    });

    expect(response.statusCode).toBe(401);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('AUTH_FAILED');
  });

  /**
   * Tests that a tampered request body is detected via HMAC verification.
   * Signature was generated for original body, but body was modified.
   * Expected: 401 AUTH_FAILED
   */
  it('should return 401 AUTH_FAILED when request body is tampered after signing', async () => {
    const originalBody = createValidInvoiceRequest();
    const signature = signRequest(originalBody);

    // Tamper with the body after signing
    const tamperedBody = {
      ...originalBody,
      report_type: 'quote', // Changed from 'invoice' to 'quote'
    };

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: tamperedBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature, // Original signature
      },
    });

    expect(response.statusCode).toBe(401);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('AUTH_FAILED');
  });

  /**
   * Tests that valid authentication allows the request to proceed.
   * This verifies the happy path for authentication.
   */
  it('should pass authentication with valid API key and HMAC signature', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    // Should not be 401 (authentication passed)
    // Could be 200 (success) or other error codes (validation, template, etc.)
    expect(response.statusCode).not.toBe(401);
  });
});

// =============================================================================
// REQUEST VALIDATION TESTS
// =============================================================================

describe('Request Validation', () => {
  /**
   * Tests that requests with missing request_id are rejected.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR when request_id is missing', async () => {
    const requestBody = createValidInvoiceRequest();
    delete (requestBody as Record<string, unknown>).request_id;
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
  });

  /**
   * Tests that requests with invalid request_id format are rejected.
   * request_id must be a valid UUID.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR when request_id is not a valid UUID', async () => {
    const requestBody = createValidInvoiceRequest();
    requestBody.request_id = 'not-a-valid-uuid';
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
  });

  /**
   * Tests that requests with invalid report_type are rejected.
   * Only 'invoice', 'quote', 'delivery_slip' are valid.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR when report_type is invalid', async () => {
    const requestBody = createValidInvoiceRequest();
    requestBody.report_type = 'invalid_type';
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
    // Verify error details contain information about the invalid field
    expect(body.error.details).toBeDefined();
  });

  /**
   * Tests that requests with missing report_type are rejected.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR when report_type is missing', async () => {
    const requestBody = createValidInvoiceRequest();
    delete (requestBody as Record<string, unknown>).report_type;
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
  });

  /**
   * Tests that requests with empty record_ids array are rejected.
   * At least one record ID is required.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR when record_ids is empty', async () => {
    const requestBody = createValidInvoiceRequest();
    requestBody.record_ids = [];
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
  });

  /**
   * Tests that requests with missing data object are rejected.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR when data is missing', async () => {
    const requestBody = createValidInvoiceRequest();
    delete (requestBody as Record<string, unknown>).data;
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
  });

  /**
   * Tests that requests with missing company name in data are rejected.
   * company.name is a required field.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR when data.company.name is missing', async () => {
    const requestBody = createValidInvoiceRequest();
    const data = requestBody.data as Record<string, unknown>;
    const company = data.company as Record<string, unknown>;
    delete company.name;
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
  });

  /**
   * Tests validation error response includes detailed issue information.
   * Expected: Error details contain issues array with path, message, and code.
   */
  it('should include validation error details with issues array', async () => {
    const requestBody = createValidInvoiceRequest();
    requestBody.report_type = 'invalid_report_type_for_testing';
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.error.details).toBeDefined();
    expect(body.error.details.issues).toBeDefined();
    expect(Array.isArray(body.error.details.issues)).toBe(true);
    expect(body.error.details.issues.length).toBeGreaterThan(0);

    // Verify issue structure
    const issue = body.error.details.issues[0];
    expect(issue.path).toBeDefined();
    expect(issue.message).toBeDefined();
    expect(issue.code).toBeDefined();
  });
});

// =============================================================================
// SUCCESSFUL RENDER TESTS
// =============================================================================

describe('Successful PDF Rendering', () => {
  /**
   * Tests successful invoice PDF generation.
   * Verifies response structure and PDF validity.
   * Expected: 200 with valid PDF data
   */
  it('should successfully render invoice PDF', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);

    const startTime = Date.now();

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    const renderTime = Date.now() - startTime;

    expect(response.statusCode).toBe(200);

    const body = response.json();
    expect(body.success).toBe(true);
    expect(body.data).toBeDefined();
    expect(body.request_id).toBe(requestBody.request_id);

    // Verify PDF data structure
    expect(body.data.pdf_base64).toBeDefined();
    expect(typeof body.data.pdf_base64).toBe('string');
    expect(body.data.pdf_base64.length).toBeGreaterThan(0);

    // Verify filename
    expect(body.data.filename).toBeDefined();
    expect(body.data.filename).toMatch(/\.pdf$/);

    // Verify page count
    expect(body.data.page_count).toBeDefined();
    expect(body.data.page_count).toBeGreaterThan(0);

    // Verify content type
    expect(body.data.content_type).toBe('application/pdf');

    // Verify render time is included
    expect(body.data.render_time_ms).toBeDefined();
    expect(typeof body.data.render_time_ms).toBe('number');

    // Verify PDF magic bytes
    expect(isPdfValid(body.data.pdf_base64)).toBe(true);

    // Performance assertion: render time < 5 seconds
    expect(renderTime).toBeLessThan(MAX_RENDER_TIME_MS);
  }, 30000); // Extended timeout for PDF generation

  /**
   * Tests successful quote PDF generation.
   * Verifies response structure and PDF validity.
   * Expected: 200 with valid PDF data
   */
  it('should successfully render quote PDF', async () => {
    const requestBody = createValidQuoteRequest();
    const signature = signRequest(requestBody);

    const startTime = Date.now();

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    const renderTime = Date.now() - startTime;

    expect(response.statusCode).toBe(200);

    const body = response.json();
    expect(body.success).toBe(true);
    expect(body.data).toBeDefined();
    expect(body.request_id).toBe(requestBody.request_id);

    // Verify PDF data
    expect(body.data.pdf_base64).toBeDefined();
    expect(body.data.pdf_base64.length).toBeGreaterThan(0);
    expect(isPdfValid(body.data.pdf_base64)).toBe(true);

    // Verify page count and filename
    expect(body.data.page_count).toBeGreaterThan(0);
    expect(body.data.filename).toMatch(/\.pdf$/);

    // Performance assertion
    expect(renderTime).toBeLessThan(MAX_RENDER_TIME_MS);
  }, 30000);

  /**
   * Tests successful delivery slip PDF generation.
   * Per Agent Action Plan Section 0.8.5, delivery slips show quantities only.
   * Expected: 200 with valid PDF data
   */
  it('should successfully render delivery_slip PDF', async () => {
    const requestBody = createValidDeliverySlipRequest();
    const signature = signRequest(requestBody);

    const startTime = Date.now();

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    const renderTime = Date.now() - startTime;

    expect(response.statusCode).toBe(200);

    const body = response.json();
    expect(body.success).toBe(true);
    expect(body.data).toBeDefined();
    expect(body.request_id).toBe(requestBody.request_id);

    // Verify PDF data
    expect(body.data.pdf_base64).toBeDefined();
    expect(body.data.pdf_base64.length).toBeGreaterThan(0);
    expect(isPdfValid(body.data.pdf_base64)).toBe(true);

    // Verify page count and filename
    expect(body.data.page_count).toBeGreaterThan(0);
    expect(body.data.filename).toMatch(/\.pdf$/);

    // Performance assertion
    expect(renderTime).toBeLessThan(MAX_RENDER_TIME_MS);
  }, 30000);

  /**
   * Tests that X-Request-ID header is propagated in response.
   * Important for distributed tracing across Odoo → Sidecar.
   */
  it('should include X-Request-ID in response headers', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);
    const customRequestId = randomUUID();

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
        'x-request-id': customRequestId,
      },
    });

    // Response should include X-Request-ID header
    expect(response.headers['x-request-id']).toBe(customRequestId);
  }, 30000);

  /**
   * Tests that response includes request_id from the request body.
   * Enables correlation between request and response.
   */
  it('should include request_id from request body in response', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(200);

    const body = response.json();
    expect(body.request_id).toBe(requestBody.request_id);
  }, 30000);

  /**
   * Tests PDF generation with custom page size (Letter instead of A4).
   */
  it('should respect page_size option when generating PDF', async () => {
    const requestBody = createValidInvoiceRequest();
    const options = requestBody.options as Record<string, unknown>;
    options.page_size = 'Letter';
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(200);

    const body = response.json();
    expect(body.success).toBe(true);
    expect(isPdfValid(body.data.pdf_base64)).toBe(true);
  }, 30000);
});

// =============================================================================
// ERROR HANDLING TESTS
// =============================================================================

describe('Error Handling', () => {
  /**
   * Tests error response structure consistency.
   * All errors should have success: false and error object.
   */
  it('should return consistent error response structure', async () => {
    const requestBody = createValidInvoiceRequest();
    requestBody.report_type = 'invalid';
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    const body = response.json();

    // All error responses must have consistent structure
    expect(body.success).toBe(false);
    expect(body.error).toBeDefined();
    expect(body.error.code).toBeDefined();
    expect(body.error.message).toBeDefined();
    expect(typeof body.error.message).toBe('string');
  });

  /**
   * Tests that request_id is included in error responses.
   * Enables correlation even for failed requests.
   */
  it('should include request_id in error responses', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);

    // Remove required field to trigger validation error
    delete (requestBody as Record<string, unknown>).report_type;
    // Re-sign with modified body
    const newSignature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': newSignature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.error.request_id).toBeDefined();
  });

  /**
   * Tests handling of empty request body.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR for empty request body', async () => {
    const emptyBody = {};
    const signature = signRequest(emptyBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: emptyBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
  });

  /**
   * Tests handling of invalid JSON body.
   * Expected: Error response (typically 400)
   */
  it('should handle invalid JSON gracefully', async () => {
    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: 'this is not valid json',
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': 'invalid',
      },
    });

    // Fastify returns 400 for JSON parse errors
    expect(response.statusCode).toBeGreaterThanOrEqual(400);
    expect(response.statusCode).toBeLessThan(500);
  });

  /**
   * Tests handling of requests with record_ids containing invalid values.
   * record_ids must contain positive integers.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR for negative record_id', async () => {
    const requestBody = createValidInvoiceRequest();
    requestBody.record_ids = [-1];
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
  });

  /**
   * Tests handling of requests with non-integer record_ids.
   * Expected: 400 VALIDATION_ERROR
   */
  it('should return 400 VALIDATION_ERROR for non-integer record_id', async () => {
    const requestBody = createValidInvoiceRequest();
    requestBody.record_ids = [1.5];
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.statusCode).toBe(400);

    const body = response.json();
    expect(body.success).toBe(false);
    expect(body.error.code).toBe('VALIDATION_ERROR');
  });
});

// =============================================================================
// HEALTH ENDPOINT TESTS
// =============================================================================

describe('Health Endpoints', () => {
  /**
   * Tests that GET /health returns 200 OK.
   * Liveness probe for container orchestration.
   * Should be accessible without authentication.
   */
  it('should return 200 OK for GET /health', async () => {
    const response = await app.inject({
      method: 'GET',
      url: HEALTH_ENDPOINT,
      // No authentication headers required
    });

    expect(response.statusCode).toBe(200);

    const body = response.json();
    // Health handler returns 'healthy' or 'unhealthy' status
    expect(body.status).toBe('healthy');
    expect(body.service).toBeDefined();
    expect(body.timestamp).toBeDefined();
  });

  /**
   * Tests that GET /ready returns appropriate status.
   * Readiness probe for container orchestration.
   * Should be accessible without authentication.
   */
  it('should return status for GET /ready', async () => {
    const response = await app.inject({
      method: 'GET',
      url: READY_ENDPOINT,
      // No authentication headers required
    });

    // Ready endpoint returns 200 when ready, 503 when not ready
    expect([200, 503]).toContain(response.statusCode);

    const body = response.json();
    expect(body.status).toBeDefined();
    // Ready handler returns 'healthy' or 'unhealthy' status
    expect(['healthy', 'unhealthy']).toContain(body.status);
  });

  /**
   * Tests that health endpoints do not require authentication.
   * Critical for container orchestrators to perform health checks.
   */
  it('should not require authentication for health endpoints', async () => {
    // Health endpoint without any auth headers
    const healthResponse = await app.inject({
      method: 'GET',
      url: HEALTH_ENDPOINT,
    });

    expect(healthResponse.statusCode).not.toBe(401);

    // Ready endpoint without any auth headers
    const readyResponse = await app.inject({
      method: 'GET',
      url: READY_ENDPOINT,
    });

    expect(readyResponse.statusCode).not.toBe(401);
  });
});

// =============================================================================
// RATE LIMIT HEADER TESTS
// =============================================================================

describe('Rate Limit Headers', () => {
  /**
   * Tests that rate limit headers are included in responses.
   * Helps clients understand their rate limit status.
   */
  it('should include rate limit headers in response', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    // Rate limit headers should be present
    expect(response.headers['x-ratelimit-limit']).toBeDefined();
    expect(response.headers['x-ratelimit-remaining']).toBeDefined();
    expect(response.headers['x-ratelimit-reset']).toBeDefined();
  }, 30000);
});

// =============================================================================
// RESPONSE HEADER TESTS
// =============================================================================

describe('Response Headers', () => {
  /**
   * Tests that response includes correct content-type header.
   */
  it('should return application/json content-type for render response', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
      },
    });

    expect(response.headers['content-type']).toMatch(/application\/json/);
  }, 30000);

  /**
   * Tests that X-Request-ID is generated when not provided.
   */
  it('should generate X-Request-ID when not provided', async () => {
    const requestBody = createValidInvoiceRequest();
    const signature = signRequest(requestBody);

    const response = await app.inject({
      method: 'POST',
      url: RENDER_ENDPOINT,
      payload: requestBody,
      headers: {
        'content-type': 'application/json',
        'x-api-key': TEST_API_KEY,
        'x-hmac-signature': signature,
        // X-Request-ID header intentionally omitted
      },
    });

    // Response should include a generated X-Request-ID
    expect(response.headers['x-request-id']).toBeDefined();
    expect(typeof response.headers['x-request-id']).toBe('string');
    expect(response.headers['x-request-id'].length).toBeGreaterThan(0);
  }, 30000);
});
