# Technical Specification

# 0. Agent Action Plan

## 0.1 Intent Clarification

### 0.1.1 Core Objective

Based on the provided requirements, the Blitzy platform understands that the objective is to:

- **Extract PDF document generation** from Odoo's Python ecosystem into a standalone TypeScript sidecar service that operates independently while maintaining Odoo as the system of record
- **Demonstrate clean service boundary patterns** by establishing well-defined HTTP-based communication between Python (Odoo) and TypeScript (sidecar), proving this architecture for future language migration initiatives
- **Achieve type safety and contract enforcement** through Zod schema validation in TypeScript and JSON/OpenAPI contracts shared between services
- **Enable independent scalability** by allowing the PDF rendering service to scale horizontally without affecting Odoo's core infrastructure
- **Maintain zero-disruption compatibility** with automatic fallback to native QWeb rendering when the sidecar is unavailable

The following specific requirements have been surfaced with enhanced clarity:

| Requirement | Technical Interpretation | Success Criteria |
|-------------|-------------------------|------------------|
| PDF rendering extraction | Create Fastify 4.x TypeScript service with Puppeteer for invoice, quote, and delivery slip generation | Service generates valid PDFs matching QWeb layout |
| Odoo integration | Extend `ir.actions.report` to intercept supported report types and route to sidecar | Zero changes to Odoo core ORM or database schema |
| Fallback mechanism | Implement automatic QWeb fallback when sidecar unavailable/errors | 100% backward compatibility on sidecar failure |
| Performance target | Process standard documents within 5 seconds | P95 latency under 5s for standard documents |
| Authentication | API key + HMAC-SHA256 request signature validation | All requests authenticated and tamper-proof |
| Template parity | Handlebars templates matching existing QWeb report layouts | Visual consistency with native Odoo reports |

**Implicit Requirements Detected:**

- Browser pool management for Puppeteer to handle concurrent requests efficiently
- Structured logging with request correlation for distributed tracing across Odoo → Sidecar
- Health and readiness endpoints for container orchestration
- Rate limiting to protect the sidecar from overwhelming concurrent requests
- Graceful shutdown handling to complete in-flight PDF generations
- Template caching to avoid repeated filesystem reads

### 0.1.2 Task Categorization

**Primary Task Type:** Mixed (New Feature + Infrastructure)

This implementation combines:
- **New Feature Development:** Creating a greenfield TypeScript sidecar service
- **Integration Development:** Building the Odoo bridge module
- **Infrastructure Configuration:** Docker, Docker Compose, environment configuration

**Secondary Aspects:**
- API Contract Design (OpenAPI/JSON Schema)
- Template Development (Handlebars HTML templates)
- Security Implementation (HMAC authentication, rate limiting)
- Testing Infrastructure (Unit and integration tests with Vitest)

**Scope Classification:** Cross-cutting change

This change spans:
- New standalone TypeScript service (`sidecar/`)
- New Odoo addon module (`addons/document_sidecar_bridge/`)
- Shared contract definitions (`contracts/`)
- Docker infrastructure (`docker-compose.yml`, `Dockerfile`)

### 0.1.3 Special Instructions and Constraints

**CRITICAL Directives from User:**

- **MUST NOT modify** `odoo/` core source code under any circumstances
- **MUST NOT modify** PostgreSQL database schema
- **MUST preserve** all existing document generation workflows unchanged
- **MUST implement** automatic fallback to native QWeb when sidecar is unavailable
- **MUST support** single-record rendering only (batch rendering explicitly OUT OF SCOPE)
- **MUST support** `en_US` language only (i18n explicitly OUT OF SCOPE)

**Methodological Requirements:**

- Follow Odoo standard addon extension patterns
- Use Zod schemas as the source of truth for TypeScript contracts
- Implement contract-first design with OpenAPI specification
- Maintain stateless processing in the sidecar (no business data persistence)

**User-Provided Examples (Preserved Verbatim):**

User Example - Zod Schema for Document Request:
```typescript
export const DocumentRequestSchema = z.object({
  request_id: z.string().uuid(),
  report_type: z.enum(['invoice', 'quote', 'delivery_slip']),
  record_ids: z.array(z.number()).min(1),
  data: z.object({ /* company, partner, lines, totals, metadata */ }),
  options: z.object({ /* page_size, language, copies */ }).optional(),
});
```

User Example - Odoo Report Type Mapping:
```python
SIDECAR_REPORT_TYPES = {
    'account.report_invoice': 'invoice',
    'sale.report_saleorder': 'quote',
    'stock.report_deliveryslip': 'delivery_slip',
}
```

**Web Search Research Requirements:**
- ✅ Fastify 4.x TypeScript best practices (researched)
- ✅ Puppeteer PDF generation optimization patterns (researched)
- ✅ Node.js 20 LTS compatibility considerations (researched)

### 0.1.4 Technical Interpretation

These requirements translate to the following technical implementation strategy:

**To achieve PDF extraction**, we will CREATE a standalone TypeScript service (`sidecar/`) implementing:
- Fastify 4.x HTTP server with typed route handlers
- Puppeteer-based PDF renderer with browser pool management
- Handlebars template engine for HTML generation
- Zod validation for request/response contracts

**To achieve Odoo integration**, we will CREATE an Odoo addon module (`addons/document_sidecar_bridge/`) implementing:
- Extension of `ir.actions.report` model via `_inherit`
- Override of `_render_qweb_pdf` method to intercept supported reports
- HTTP client wrapper using Python `requests` library
- Data serialization from Odoo ORM objects to JSON payloads

**To achieve automatic fallback**, we will IMPLEMENT error handling that:
- Catches `SidecarUnavailable` exceptions (connection errors, timeouts)
- Catches any unexpected sidecar errors
- Delegates to `super()._render_qweb_pdf()` for native QWeb rendering
- Logs fallback events for monitoring

**To achieve template parity**, we will CREATE Handlebars templates by:
- Analyzing existing QWeb templates in `addons/account/report/`, `addons/sale/report/`, and `addons/stock/report/`
- Reproducing layout structure, headers, line item tables, and totals sections
- Implementing print-optimized CSS for consistent PDF output

**To achieve security**, we will IMPLEMENT:
- API key validation via `X-API-Key` header
- HMAC-SHA256 signature verification via `X-HMAC-Signature` header
- Rate limiting (100 requests/minute per API key by default)
- Request ID correlation via `X-Request-ID` header

## 0.2 Repository Scope Discovery

### 0.2.1 Comprehensive File Analysis

**Repository Structure Discovered:**

The repository is a standard Odoo 17 installation with the following relevant structure:

```
project-root/
├── addons/                     # Addon modules (300+ modules)
│   ├── account/               # Accounting module (invoice reports)
│   ├── sale/                  # Sales module (quotation reports)
│   ├── stock/                 # Stock module (delivery slip reports)
│   └── [other modules]
├── odoo/                      # Core Odoo package (READ-ONLY)
│   └── addons/base/
│       └── models/
│           └── ir_actions_report.py  # Core report rendering
├── requirements.txt           # Python dependencies
├── setup.py                   # Package configuration
└── docker-compose.yml         # (TO BE CREATED)
```

**Critical Files Identified for Reference:**

| File Path | Purpose | Action |
|-----------|---------|--------|
| `odoo/addons/base/models/ir_actions_report.py` | Core report rendering logic with `_render_qweb_pdf` method | REFERENCE - Understand interception point |
| `addons/account/models/ir_actions_report.py` | Invoice-specific report extensions | REFERENCE - Pattern for extension |
| `addons/account/report/account_invoice_report.xml` | Invoice QWeb template structure | REFERENCE - Template layout |
| `addons/account/views/report_templates.xml` | Additional invoice report templates | REFERENCE - Template components |
| `addons/sale/report/ir_actions_report_templates.xml` | Sale order QWeb templates | REFERENCE - Quote template layout |
| `addons/sale/models/ir_actions_report.py` | Sale-specific report handling | REFERENCE - Extension pattern |
| `addons/stock/report/report_deliveryslip.xml` | Delivery slip QWeb template | REFERENCE - Delivery slip layout |
| `requirements.txt` | Python dependency manifest | REFERENCE - Existing dependencies |

**New Files and Directories to Create:**

Based on the user-specified project structure, the following must be created:

```
project-root/
├── sidecar/                          # NEW: TypeScript service
│   ├── src/
│   │   ├── index.ts
│   │   ├── config.ts
│   │   ├── api/
│   │   │   ├── routes.ts
│   │   │   ├── render.handler.ts
│   │   │   └── health.handler.ts
│   │   ├── middleware/
│   │   │   ├── auth.ts
│   │   │   ├── rate-limiter.ts
│   │   │   ├── request-id.ts
│   │   │   └── error-handler.ts
│   │   ├── services/
│   │   │   ├── template.service.ts
│   │   │   ├── renderer.service.ts
│   │   │   └── pdf.service.ts
│   │   ├── templates/
│   │   │   ├── invoice.hbs
│   │   │   ├── quote.hbs
│   │   │   ├── delivery_slip.hbs
│   │   │   ├── partials/
│   │   │   │   ├── header.hbs
│   │   │   │   ├── footer.hbs
│   │   │   │   └── line-items.hbs
│   │   │   └── styles/
│   │   │       └── pdf.css
│   │   ├── contracts/
│   │   │   ├── request.schema.ts
│   │   │   ├── response.schema.ts
│   │   │   └── domain.types.ts
│   │   └── utils/
│   │       ├── logger.ts
│   │       ├── hmac.ts
│   │       └── base64.ts
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── template.service.test.ts
│   │   │   └── renderer.service.test.ts
│   │   ├── integration/
│   │   │   └── render.test.ts
│   │   └── fixtures/
│   │       ├── sample-invoice.json
│   │       ├── sample-quote.json
│   │       └── sample-delivery.json
│   ├── package.json
│   ├── tsconfig.json
│   ├── vitest.config.ts
│   └── Dockerfile
│
├── addons/
│   └── document_sidecar_bridge/      # NEW: Odoo module
│       ├── __manifest__.py
│       ├── __init__.py
│       ├── models/
│       │   ├── __init__.py
│       │   └── ir_actions_report.py
│       ├── services/
│       │   ├── __init__.py
│       │   └── sidecar_client.py
│       ├── data/
│       │   └── ir_config_parameter.xml
│       └── tests/
│           └── test_sidecar_bridge.py
│
├── contracts/                        # NEW: Shared contracts
│   ├── openapi.yaml
│   └── schemas/
│       ├── request.json
│       └── response.json
│
├── docker-compose.yml                # NEW
├── .env.example                      # NEW
└── README.md                         # UPDATE (add sidecar docs)
```

### 0.2.2 Web Search Research Conducted

**Research Area 1: Fastify + TypeScript Best Practices**
- Use `import Fastify from 'fastify'` syntax for proper type resolution
- Leverage Fastify's plugin architecture for modular code organization
- Implement generic type constraints for route handlers
- Use declaration merging for custom decorators
- Set `target: es2017` or greater in tsconfig.json

**Research Area 2: Puppeteer PDF Generation Optimization**
- Use `waitUntil: 'networkidle0'` for complete page load before PDF generation
- Reuse browser instances across requests (browser pool pattern)
- Limit concurrent PDF generations to CPU core count - 1
- Use `--no-sandbox`, `--disable-setuid-sandbox`, `--disable-dev-shm-usage` flags in Docker
- Apply print-specific CSS (`@media print`) for consistent output
- Set `printBackground: true` for proper background rendering

**Research Area 3: Security Considerations**
- HMAC-SHA256 for request integrity verification
- API key rotation procedures for production
- Rate limiting at 100 requests/minute as baseline
- TLS required in production environments

### 0.2.3 Existing Infrastructure Assessment

**Current Project Structure:**
- Standard Odoo 17 monolithic application
- Python 3.11+ runtime (based on `requirements.txt`)
- PostgreSQL database backend
- No existing TypeScript/Node.js components

**Existing Patterns and Conventions:**
- Odoo addon modules follow `__manifest__.py` + `__init__.py` pattern
- Report extensions use `_inherit = 'ir.actions.report'` pattern
- QWeb templates use XML-based declarative syntax
- Python logging via standard `logging` module

**Build and Deployment:**
- No existing Docker configuration detected at repository root
- Odoo typically deployed via `odoo-bin` CLI
- Dependencies managed via `requirements.txt`

**Testing Infrastructure:**
- Odoo uses unittest-based test framework
- Tests located in `tests/` directories within addons
- No Node.js testing infrastructure exists (to be created)

**Documentation System:**
- `doc/` directory exists for documentation
- `README.md` at repository root
- `CONTRIBUTING.md` for contributor guidelines

### 0.2.4 Core Odoo Report Infrastructure Analysis

**Key Findings from `odoo/addons/base/models/ir_actions_report.py`:**

The core report model (`IrActionsReport`) implements the following critical methods:

| Method | Purpose | Lines | Interception Point |
|--------|---------|-------|-------------------|
| `_render_qweb_pdf` | Main entry point for PDF rendering | 730-850 | ✅ Override target |
| `_render_qweb_pdf_prepare_streams` | Prepares data streams for wkhtmltopdf | 680-730 | Internal |
| `_run_wkhtmltopdf` | Executes wkhtmltopdf binary | 350-500 | Internal |
| `_merge_pdfs` | Merges multiple PDF files | 500-550 | Internal |

**Extension Point Analysis:**

The `_render_qweb_pdf` method in `IrActionsReport` follows this flow:
1. Resolve report by name/ID
2. Check for cached attachments
3. Prepare data streams via `_render_qweb_pdf_prepare_streams`
4. Execute wkhtmltopdf via `_run_wkhtmltopdf`
5. Handle post-processing (merge, save attachment)

Our extension will intercept at step 1, before any wkhtmltopdf processing:

```python
def _render_qweb_pdf(self, report_ref, res_ids, data=None):
    report = self._get_report(report_ref)
    if report.report_name in self.SIDECAR_REPORT_TYPES:
        # Route to sidecar
        return self._render_via_sidecar(report, res_ids)
    # Fall through to native implementation
    return super()._render_qweb_pdf(report_ref, res_ids, data)
```

**Existing Extension Pattern from `addons/account/models/ir_actions_report.py`:**

The account module extends `ir.actions.report` to handle invoice-specific logic:
- Attachment management for posted invoices
- Pro-forma invoice handling
- Document layout customization

This serves as a reference pattern for our bridge module extension.

## 0.3 File Transformation Mapping

### 0.3.1 File-by-File Execution Plan

**Transformation Mode Legend:**
- **CREATE** - Create a new file from scratch
- **UPDATE** - Modify an existing file
- **DELETE** - Remove an obsolete file
- **REFERENCE** - Use as a source pattern (read-only)

| Target File | Transformation | Source File/Reference | Purpose/Changes |
|-------------|----------------|----------------------|-----------------|
| `sidecar/package.json` | CREATE | N/A | Node.js project manifest with all TypeScript/Fastify dependencies |
| `sidecar/tsconfig.json` | CREATE | N/A | TypeScript compiler configuration with strict mode |
| `sidecar/vitest.config.ts` | CREATE | N/A | Vitest test runner configuration |
| `sidecar/Dockerfile` | CREATE | N/A | Multi-stage Docker build for production deployment |
| `sidecar/src/index.ts` | CREATE | User-provided spec | Fastify server entry point with plugin registration |
| `sidecar/src/config.ts` | CREATE | N/A | Environment variable configuration with defaults |
| `sidecar/src/api/routes.ts` | CREATE | N/A | Route registration for /api/v1/render and health endpoints |
| `sidecar/src/api/render.handler.ts` | CREATE | User-provided spec | POST /api/v1/render handler with validation and rendering |
| `sidecar/src/api/health.handler.ts` | CREATE | N/A | GET /health and GET /ready endpoint handlers |
| `sidecar/src/middleware/auth.ts` | CREATE | User-provided spec | API key and HMAC signature validation |
| `sidecar/src/middleware/rate-limiter.ts` | CREATE | User-provided spec | Request rate limiting using @fastify/rate-limit |
| `sidecar/src/middleware/request-id.ts` | CREATE | N/A | X-Request-ID correlation ID injection |
| `sidecar/src/middleware/error-handler.ts` | CREATE | N/A | Structured error response formatting |
| `sidecar/src/services/template.service.ts` | CREATE | N/A | Handlebars template loading, caching, and compilation |
| `sidecar/src/services/renderer.service.ts` | CREATE | User-provided spec | Puppeteer browser pool and PDF generation |
| `sidecar/src/services/pdf.service.ts` | CREATE | N/A | PDF utilities using pdf-lib (page count, metadata) |
| `sidecar/src/templates/invoice.hbs` | CREATE | `addons/account/report/account_invoice_report.xml` | Invoice HTML template matching QWeb layout |
| `sidecar/src/templates/quote.hbs` | CREATE | `addons/sale/report/ir_actions_report_templates.xml` | Quote/Sale Order HTML template matching QWeb layout |
| `sidecar/src/templates/delivery_slip.hbs` | CREATE | `addons/stock/report/report_deliveryslip.xml` | Delivery slip HTML template matching QWeb layout |
| `sidecar/src/templates/partials/header.hbs` | CREATE | N/A | Shared document header partial (company info, logo) |
| `sidecar/src/templates/partials/footer.hbs` | CREATE | N/A | Shared document footer partial (notes, terms) |
| `sidecar/src/templates/partials/line-items.hbs` | CREATE | N/A | Shared line items table partial |
| `sidecar/src/templates/styles/pdf.css` | CREATE | N/A | Print-optimized CSS for PDF rendering |
| `sidecar/src/contracts/request.schema.ts` | CREATE | User-provided spec | Zod request validation schemas |
| `sidecar/src/contracts/response.schema.ts` | CREATE | User-provided spec | Response type definitions and error codes |
| `sidecar/src/contracts/domain.types.ts` | CREATE | N/A | Business domain type definitions |
| `sidecar/src/utils/logger.ts` | CREATE | N/A | Pino structured logging configuration |
| `sidecar/src/utils/hmac.ts` | CREATE | N/A | HMAC-SHA256 signature utilities |
| `sidecar/src/utils/base64.ts` | CREATE | N/A | Base64 encoding/decoding utilities |
| `sidecar/tests/unit/template.service.test.ts` | CREATE | N/A | Unit tests for template service |
| `sidecar/tests/unit/renderer.service.test.ts` | CREATE | N/A | Unit tests for renderer service |
| `sidecar/tests/integration/render.test.ts` | CREATE | N/A | Integration tests for render endpoint |
| `sidecar/tests/fixtures/sample-invoice.json` | CREATE | N/A | Test fixture for invoice rendering |
| `sidecar/tests/fixtures/sample-quote.json` | CREATE | N/A | Test fixture for quote rendering |
| `sidecar/tests/fixtures/sample-delivery.json` | CREATE | N/A | Test fixture for delivery slip rendering |
| `addons/document_sidecar_bridge/__manifest__.py` | CREATE | User-provided spec | Odoo addon manifest |
| `addons/document_sidecar_bridge/__init__.py` | CREATE | N/A | Package initializer |
| `addons/document_sidecar_bridge/models/__init__.py` | CREATE | N/A | Models package initializer |
| `addons/document_sidecar_bridge/models/ir_actions_report.py` | CREATE | User-provided spec | ir.actions.report extension |
| `addons/document_sidecar_bridge/services/__init__.py` | CREATE | N/A | Services package initializer |
| `addons/document_sidecar_bridge/services/sidecar_client.py` | CREATE | User-provided spec | HTTP client for sidecar communication |
| `addons/document_sidecar_bridge/data/ir_config_parameter.xml` | CREATE | N/A | Default configuration parameters |
| `addons/document_sidecar_bridge/tests/__init__.py` | CREATE | N/A | Tests package initializer |
| `addons/document_sidecar_bridge/tests/test_sidecar_bridge.py` | CREATE | N/A | Unit tests for bridge module |
| `contracts/openapi.yaml` | CREATE | N/A | OpenAPI 3.0 specification for sidecar API |
| `contracts/schemas/request.json` | CREATE | N/A | JSON Schema for request validation |
| `contracts/schemas/response.json` | CREATE | N/A | JSON Schema for response validation |
| `docker-compose.yml` | CREATE | User-provided spec | Docker Compose for local development |
| `.env.example` | CREATE | User-provided spec | Environment variable template |
| `README.md` | UPDATE | `README.md` | Add documentation for sidecar service |

### 0.3.2 New Files Detail

**TypeScript Sidecar Service (`sidecar/`)**

`sidecar/src/index.ts` - Fastify Server Entry Point
- Content type: source code
- Based on: User-provided specification
- Key sections/functions:
  - Fastify instance creation with logger configuration
  - Error handler registration via `setErrorHandler`
  - Request ID hook via `addHook('onRequest')`
  - Rate limiter plugin registration
  - Route registration
  - Server startup with graceful shutdown handling

`sidecar/src/services/renderer.service.ts` - PDF Renderer Service
- Content type: source code
- Based on: User-provided specification
- Key sections/functions:
  - `RendererService` class with browser pool management
  - `getBrowser()` - Lazy browser initialization
  - `generatePdf(html, options)` - Puppeteer PDF generation
  - `getPageCount(pdfBuffer)` - Page count using pdf-lib
  - `shutdown()` - Browser cleanup for graceful shutdown

`sidecar/src/services/template.service.ts` - Template Service
- Content type: source code
- Based on: N/A (new implementation)
- Key sections/functions:
  - `TemplateService` class with template caching
  - `loadTemplate(reportType)` - Load Handlebars template
  - `registerPartials()` - Register shared partials
  - `render(reportType, data, language)` - Compile and render HTML

`sidecar/src/templates/invoice.hbs` - Invoice Template
- Content type: Handlebars template
- Based on: `addons/account/report/account_invoice_report.xml`
- Key sections:
  - Header with company logo and info
  - Customer/partner address block
  - Invoice metadata (number, date, due date)
  - Line items table with quantities, prices, taxes
  - Totals section with tax breakdown
  - Payment terms and notes

`sidecar/src/templates/quote.hbs` - Quote Template
- Content type: Handlebars template
- Based on: `addons/sale/report/ir_actions_report_templates.xml`
- Key sections:
  - Header with company branding
  - Customer address block
  - Quote metadata (reference, date, salesperson)
  - Line items table with quantities and prices
  - Totals section
  - Terms and conditions

`sidecar/src/templates/delivery_slip.hbs` - Delivery Slip Template
- Content type: Handlebars template
- Based on: `addons/stock/report/report_deliveryslip.xml`
- Key sections:
  - Header with company info
  - Delivery address block
  - Picking metadata (reference, scheduled date)
  - Line items table (quantities only, no pricing)
  - Notes section

**Odoo Bridge Module (`addons/document_sidecar_bridge/`)**

`addons/document_sidecar_bridge/models/ir_actions_report.py` - Report Extension
- Content type: Python source
- Based on: User-provided specification
- Key sections/functions:
  - `IrActionsReport` class with `_inherit = 'ir.actions.report'`
  - `SIDECAR_REPORT_TYPES` mapping dict
  - `_render_qweb_pdf()` override with sidecar routing
  - Fallback logic for `SidecarUnavailable` exceptions

`addons/document_sidecar_bridge/services/sidecar_client.py` - HTTP Client
- Content type: Python source
- Based on: User-provided specification
- Key sections/functions:
  - `SidecarClient` class with configuration
  - `_sign_request(payload)` - HMAC signature generation
  - `_serialize_invoice_data(invoice)` - Invoice serialization
  - `_serialize_sale_order_data(order)` - Sale order serialization
  - `_serialize_picking_data(picking)` - Delivery slip serialization
  - `render_report(report_type, res_ids, report)` - Main render method

### 0.3.3 Configuration and Documentation Updates

**Configuration Changes:**

`docker-compose.yml`:
- Services: sidecar (port 3000), odoo (port 8069), db (PostgreSQL)
- Networks: odoo-network (bridge)
- Health checks for sidecar service
- Volume mounts for addons directory

`.env.example`:
- `PORT=3000` - Sidecar server port
- `API_KEY=your-api-key-here` - API authentication key
- `SECRET_KEY=your-hmac-secret-here` - HMAC signing secret
- `LOG_LEVEL=info` - Logging verbosity
- `NODE_ENV=production` - Environment mode
- `RATE_LIMIT_MAX=100` - Rate limit ceiling
- `RATE_LIMIT_WINDOW=60000` - Rate limit window (ms)

**Odoo Configuration Parameters:**

`addons/document_sidecar_bridge/data/ir_config_parameter.xml`:
- `document_sidecar.enabled` - Feature toggle (True/False)
- `document_sidecar.url` - Sidecar base URL
- `document_sidecar.api_key` - API authentication key
- `document_sidecar.secret_key` - HMAC signing secret
- `document_sidecar.timeout` - Request timeout (seconds)

**Documentation Updates:**

`README.md`:
- Add "Document Sidecar Service" section
- Include architecture diagram reference
- Add build and run instructions for sidecar
- Document environment variable configuration
- Add troubleshooting section for common issues

### 0.3.4 Cross-File Dependencies

**Import/Reference Updates Required:**

| Source File | Imports From | Relationship |
|-------------|--------------|--------------|
| `sidecar/src/index.ts` | `./config.ts`, `./api/routes.ts`, `./middleware/*`, `./utils/logger.ts` | Configuration and route setup |
| `sidecar/src/api/render.handler.ts` | `../contracts/request.schema.ts`, `../services/template.service.ts`, `../services/renderer.service.ts`, `../middleware/auth.ts` | Request handling dependencies |
| `sidecar/src/services/template.service.ts` | `../contracts/domain.types.ts`, `../utils/logger.ts` | Data types and logging |
| `sidecar/src/services/renderer.service.ts` | `../config.ts`, `../utils/logger.ts` | Configuration access |
| `sidecar/tests/*` | `../src/**/*` | Test imports from source |
| `addons/document_sidecar_bridge/models/ir_actions_report.py` | `..services.sidecar_client` | Client service import |
| `addons/document_sidecar_bridge/__init__.py` | `.models` | Model import for Odoo loading |

**Configuration Sync Requirements:**

- API key must match between `.env` (sidecar) and `ir.config_parameter` (Odoo)
- Secret key must match between `.env` (sidecar) and `ir.config_parameter` (Odoo)
- Sidecar URL in Odoo must point to correct sidecar host/port

**Template Consistency Requirements:**

- All three main templates must include the shared partials
- CSS file must be loaded by all templates
- Template data structures must match Zod schema definitions

## 0.4 Dependency Inventory

### 0.4.1 Key Private and Public Packages

**TypeScript Sidecar Dependencies (`sidecar/package.json`):**

| Registry | Package Name | Version | Purpose |
|----------|--------------|---------|---------|
| npm | fastify | ^4.28.0 | High-performance HTTP server framework |
| npm | @fastify/rate-limit | ^9.1.0 | Request rate limiting middleware |
| npm | puppeteer | ^23.6.0 | Headless Chrome for PDF rendering |
| npm | handlebars | ^4.7.8 | HTML templating engine |
| npm | zod | ^3.23.8 | Runtime type validation and schema definition |
| npm | pdf-lib | ^1.17.1 | PDF manipulation (page count, metadata) |
| npm | pino | ^9.4.0 | Fast structured logging |
| npm | pino-pretty | ^11.2.2 | Pretty-print logs for development |
| npm | typescript | ^5.6.3 | TypeScript compiler (dev dependency) |
| npm | @types/node | ^22.7.6 | Node.js type definitions (dev dependency) |
| npm | vitest | ^2.1.2 | Fast unit testing framework (dev dependency) |
| npm | @vitest/coverage-v8 | ^2.1.2 | Code coverage reporting (dev dependency) |
| npm | tsx | ^4.19.1 | TypeScript execution for development (dev dependency) |

**Odoo Bridge Module Dependencies:**

| Registry | Package Name | Version | Purpose |
|----------|--------------|---------|---------|
| pip | requests | 2.31.0 | HTTP client for sidecar communication |

Note: The `requests` library is already included in Odoo's `requirements.txt`, so no new Python dependencies need to be added.

**Runtime Requirements:**

| Component | Version | Purpose |
|-----------|---------|---------|
| Node.js | 20 LTS (20.18.x) | TypeScript sidecar runtime |
| Chromium | (bundled with Puppeteer) | Headless browser for PDF rendering |
| Python | 3.11+ | Odoo runtime |
| PostgreSQL | 15.x | Database (existing Odoo dependency) |

### 0.4.2 Dependency Updates

**New Dependencies to Add (TypeScript Sidecar):**

All dependencies are new since the sidecar is a greenfield service. The complete `package.json` structure:

```json
{
  "name": "document-sidecar",
  "version": "1.0.0",
  "type": "module",
  "engines": {
    "node": ">=20.0.0"
  },
  "dependencies": {
    "fastify": "^4.28.0",
    "@fastify/rate-limit": "^9.1.0",
    "puppeteer": "^23.6.0",
    "handlebars": "^4.7.8",
    "zod": "^3.23.8",
    "pdf-lib": "^1.17.1",
    "pino": "^9.4.0"
  },
  "devDependencies": {
    "typescript": "^5.6.3",
    "@types/node": "^22.7.6",
    "vitest": "^2.1.2",
    "@vitest/coverage-v8": "^2.1.2",
    "tsx": "^4.19.1",
    "pino-pretty": "^11.2.2"
  }
}
```

**Dependencies to Update:**

No existing dependencies require updates. The Odoo codebase uses `requests` library which is already available.

**Dependencies to Remove:**

None. This is a new service with no pre-existing dependencies to clean up.

### 0.4.3 Import/Reference Updates

**TypeScript Module Imports Pattern:**

All TypeScript files use ES module syntax with relative imports:

```typescript
// Absolute imports from node_modules
import Fastify from 'fastify';
import { z } from 'zod';
import puppeteer from 'puppeteer';
import Handlebars from 'handlebars';

// Relative imports within project
import { config } from './config.js';
import { DocumentRequestSchema } from '../contracts/request.schema.js';
```

**Python Module Imports Pattern:**

Odoo bridge module uses standard Python imports:

```python
# Standard library
import json
import logging
import hashlib
import hmac
import uuid
import base64

#### Third-party
import requests

#### Odoo framework
from odoo import models, api
from odoo.exceptions import UserError

#### Local module imports
from ..services.sidecar_client import SidecarClient
```

**Cross-Service Data Flow:**

```
Odoo (Python)                    Sidecar (TypeScript)
──────────────                   ────────────────────
account.move ─┐
sale.order   ─┼─▶ Serialize to   ─▶ Zod Validation
stock.picking─┘   JSON payload       DocumentRequestSchema
                       │                    │
                       ▼                    ▼
              requests.post()    Fastify Route Handler
                       │                    │
                       │                    ▼
                       │            Template Service
                       │            (Handlebars)
                       │                    │
                       │                    ▼
                       │            Renderer Service
                       │            (Puppeteer)
                       │                    │
                       ◀────────────────────┘
              Base64 PDF Response
```

### 0.4.4 Version Compatibility Matrix

| Component | Minimum | Recommended | Maximum |
|-----------|---------|-------------|---------|
| Node.js | 20.0.0 | 20.18.0 | 22.x (untested) |
| TypeScript | 5.0.0 | 5.6.3 | 5.x |
| Fastify | 4.0.0 | 4.28.0 | 4.x |
| Puppeteer | 23.0.0 | 23.6.0 | 23.x |
| Python | 3.10 | 3.11+ | 3.12 |
| Odoo | 17.0 | 17.0 | 17.x |
| PostgreSQL | 14.0 | 15.x | 16.x |

**Known Compatibility Notes:**

- Puppeteer 23.x requires Node.js 18+ (we use Node.js 20 LTS)
- Fastify 4.x requires Node.js 14+ (compatible)
- Odoo 17 supports Python 3.10-3.12
- The `requests` library version in `requirements.txt` (2.31.0) is compatible

## 0.5 Implementation Design

### 0.5.1 Technical Approach

**Primary Objectives with Implementation Approach:**

1. **Achieve PDF extraction** by CREATING a standalone TypeScript Fastify service that accepts JSON document data and returns base64-encoded PDFs generated via Puppeteer headless Chrome
   - Rationale: Puppeteer provides Chrome's rendering engine for pixel-perfect PDF output without wkhtmltopdf limitations

2. **Achieve Odoo integration** by CREATING an Odoo addon module that intercepts `_render_qweb_pdf` calls for supported report types and routes them to the sidecar
   - Rationale: `_inherit` extension pattern ensures zero modification to Odoo core while providing interception capability

3. **Achieve type safety** by CREATING Zod schemas as the single source of truth for request/response contracts, with JSON Schema exports for documentation
   - Rationale: Zod provides runtime validation plus TypeScript type inference from a single definition

4. **Achieve fallback reliability** by IMPLEMENTING exception handling that catches all sidecar failures and delegates to native QWeb rendering
   - Rationale: Zero-disruption requirement mandates graceful degradation

**Logical Implementation Flow:**

**First, establish the TypeScript foundation** by:
- Setting up the Node.js 20 project with TypeScript strict mode
- Configuring Fastify server with essential middleware (rate limiting, error handling, request ID)
- Implementing Zod contracts for request/response validation
- Creating the Pino logging infrastructure for structured logging

**Next, build the rendering pipeline** by:
- Implementing the TemplateService for Handlebars template management
- Creating Handlebars templates matching existing QWeb report layouts
- Implementing the RendererService with Puppeteer browser pool
- Building the PDF generation flow: JSON → HTML → PDF → Base64

**Then, implement security layer** by:
- Creating API key validation middleware
- Implementing HMAC-SHA256 signature verification
- Configuring rate limiting with configurable thresholds

**Next, create the Odoo bridge** by:
- Implementing the `document_sidecar_bridge` addon module structure
- Creating the `SidecarClient` HTTP client with serialization logic
- Extending `ir.actions.report` to intercept and route supported reports
- Implementing fallback mechanism for error scenarios

**Finally, establish operational readiness** by:
- Creating Docker configuration for containerized deployment
- Implementing health and readiness endpoints
- Writing unit and integration tests
- Documenting environment configuration

### 0.5.2 Component Impact Analysis

**Direct Modifications Required:**

| Component | Modification | Capability Enabled |
|-----------|--------------|-------------------|
| `ir.actions.report` | Extend via `_inherit` to intercept `_render_qweb_pdf` | Route supported reports to sidecar |
| New `SidecarClient` | Create HTTP client wrapper | Communicate with TypeScript service |
| New `TemplateService` | Create template management | Load, cache, and render Handlebars templates |
| New `RendererService` | Create PDF generator | Puppeteer-based PDF generation |

**Indirect Impacts and Dependencies:**

| Component | Required Update | Reason |
|-----------|----------------|--------|
| Docker Infrastructure | Create `docker-compose.yml` | Local development environment |
| Project Configuration | Create `.env.example` | Document required environment variables |
| Documentation | Update `README.md` | Explain sidecar architecture and usage |
| Test Infrastructure | Create Vitest configuration | Enable automated testing |

**New Components Introduction:**

| Component | Type | Responsibility | Rationale |
|-----------|------|----------------|-----------|
| `document-sidecar` | TypeScript Service | PDF document generation | Extract rendering from Python to enable independent scaling and type safety |
| `document_sidecar_bridge` | Odoo Addon | Integration layer | Bridge Odoo reports to sidecar without modifying core |
| `contracts/` | Shared Definitions | API contract documentation | Single source of truth for cross-service communication |

### 0.5.3 User-Provided Examples Integration

**Request Schema Implementation:**

The user's example Zod schema will be implemented in `sidecar/src/contracts/request.schema.ts`:
```typescript
export const DocumentRequestSchema = z.object({
  request_id: z.string().uuid(),
  report_type: z.enum(['invoice', 'quote', 'delivery_slip']),
  // ... (as specified by user)
});
```

**Report Type Mapping Implementation:**

The user's example mapping will be implemented in `addons/document_sidecar_bridge/models/ir_actions_report.py`:
```python
SIDECAR_REPORT_TYPES = {
    'account.report_invoice': 'invoice',
    'sale.report_saleorder': 'quote',
    'stock.report_deliveryslip': 'delivery_slip',
}
```

**Serialization Examples:**

The user's detailed serialization functions (`_serialize_invoice_data`, `_serialize_sale_order_data`, `_serialize_picking_data`) will be implemented exactly as specified in `sidecar_client.py`.

### 0.5.4 Critical Implementation Details

**Design Patterns Employed:**

| Pattern | Application | Benefit |
|---------|-------------|---------|
| Service Layer | `TemplateService`, `RendererService` | Separation of concerns, testability |
| Factory | Browser pool in `RendererService` | Lazy initialization, resource management |
| Adapter | `SidecarClient` | Encapsulate HTTP communication details |
| Strategy | Report type → Template mapping | Extensible document type support |
| Decorator | Fastify hooks and middleware | Cross-cutting concerns without coupling |

**Key Algorithms and Approaches:**

1. **Browser Pool Management:**
   - Single Puppeteer browser instance reused across requests
   - New page created per request, closed after use
   - Graceful shutdown ensures browser cleanup

2. **Template Caching:**
   - Templates loaded from filesystem on first use
   - Compiled Handlebars templates cached in memory
   - Partials registered once at service startup

3. **HMAC Signature Verification:**
   - Request body JSON stringified
   - HMAC-SHA256 computed with shared secret
   - Constant-time comparison prevents timing attacks

**Data Flow:**

```
┌─────────────────────────────────────────────────────────────────┐
│                         ODOO REQUEST FLOW                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User clicks "Print Invoice"                                    │
│         │                                                       │
│         ▼                                                       │
│  ir.actions.report._render_qweb_pdf()                          │
│         │                                                       │
│         ▼                                                       │
│  document_sidecar_bridge intercepts                            │
│         │                                                       │
│         ├─── Is sidecar enabled? ─── No ───▶ QWeb fallback     │
│         │                                                       │
│         Yes                                                     │
│         │                                                       │
│         ▼                                                       │
│  SidecarClient.render_report()                                 │
│         │                                                       │
│         ├─── _serialize_*_data() ───▶ JSON payload             │
│         │                                                       │
│         ├─── _sign_request() ───▶ HMAC signature               │
│         │                                                       │
│         ▼                                                       │
│  HTTP POST /api/v1/render                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SIDECAR REQUEST FLOW                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Fastify receives POST /api/v1/render                          │
│         │                                                       │
│         ▼                                                       │
│  Rate Limiter Check ─── Exceeded? ───▶ 429 RATE_LIMITED        │
│         │                                                       │
│         ▼                                                       │
│  API Key Validation ─── Invalid? ───▶ 401 AUTH_FAILED          │
│         │                                                       │
│         ▼                                                       │
│  HMAC Signature Check ─── Invalid? ───▶ 401 AUTH_FAILED        │
│         │                                                       │
│         ▼                                                       │
│  Zod Request Validation ─── Failed? ───▶ 400 VALIDATION_ERROR  │
│         │                                                       │
│         ▼                                                       │
│  TemplateService.render(reportType, data)                      │
│         │                                                       │
│         ├─── Load template ─── Not found? ───▶ 404 NOT_FOUND   │
│         │                                                       │
│         ├─── Compile with Handlebars                           │
│         │                                                       │
│         ▼                                                       │
│  RendererService.generatePdf(html, options)                    │
│         │                                                       │
│         ├─── Get/create browser instance                       │
│         │                                                       │
│         ├─── Create new page                                   │
│         │                                                       │
│         ├─── setContent(html)                                  │
│         │                                                       │
│         ├─── page.pdf() ───▶ PDF buffer                        │
│         │                                                       │
│         ├─── Close page                                        │
│         │                                                       │
│         ▼                                                       │
│  Return {pdf_base64, filename, page_count, ...}                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Error Handling and Edge Cases:**

| Scenario | Handling | Response |
|----------|----------|----------|
| Sidecar unreachable | `SidecarUnavailable` caught, fallback to QWeb | Native PDF generated |
| Sidecar timeout | `requests.Timeout` caught, fallback to QWeb | Native PDF generated |
| Invalid HMAC signature | Return 401 immediately | `AUTH_FAILED` error |
| Invalid request payload | Zod validation fails, return 400 | `VALIDATION_ERROR` with details |
| Unknown report type | Template not found, return 404 | `TEMPLATE_NOT_FOUND` error |
| Puppeteer crash | Catch exception, return 500 | `RENDER_FAILED` error |
| Rate limit exceeded | Return 429 with retry-after | `RATE_LIMITED` error |

**Performance Considerations:**

- Browser instance reuse eliminates ~500ms startup per request
- Template caching eliminates filesystem reads after first load
- `waitUntil: 'networkidle0'` ensures fonts and resources loaded
- PDF buffer returned directly (no disk I/O)
- Connection pooling via keep-alive for HTTP client

**Security Considerations:**

- API key validates client identity
- HMAC signature prevents request tampering
- Rate limiting prevents DoS attacks
- No business data persisted in sidecar
- TLS encryption required in production
- Puppeteer sandboxing flags for container security

## 0.6 Scope Boundaries

### 0.6.1 Exhaustively In Scope

**TypeScript Sidecar Service:**

| Category | File Patterns | Specific Items |
|----------|---------------|----------------|
| Source Code | `sidecar/src/**/*.ts` | All TypeScript source files |
| Templates | `sidecar/src/templates/**/*.hbs` | invoice.hbs, quote.hbs, delivery_slip.hbs, partials/*.hbs |
| Styles | `sidecar/src/templates/styles/**/*.css` | pdf.css |
| Tests | `sidecar/tests/**/*.ts` | Unit tests, integration tests |
| Fixtures | `sidecar/tests/fixtures/**/*.json` | Sample invoice, quote, delivery JSON |
| Configuration | `sidecar/package.json` | Node.js project manifest |
| Configuration | `sidecar/tsconfig.json` | TypeScript compiler options |
| Configuration | `sidecar/vitest.config.ts` | Test runner configuration |
| Infrastructure | `sidecar/Dockerfile` | Container build definition |

**Odoo Bridge Module:**

| Category | File Patterns | Specific Items |
|----------|---------------|----------------|
| Source Code | `addons/document_sidecar_bridge/**/*.py` | All Python source files |
| Data | `addons/document_sidecar_bridge/data/**/*.xml` | ir_config_parameter.xml |
| Manifest | `addons/document_sidecar_bridge/__manifest__.py` | Odoo addon manifest |
| Tests | `addons/document_sidecar_bridge/tests/**/*.py` | Bridge module tests |

**Shared Contracts:**

| Category | File Patterns | Specific Items |
|----------|---------------|----------------|
| OpenAPI | `contracts/openapi.yaml` | API specification |
| JSON Schema | `contracts/schemas/**/*.json` | request.json, response.json |

**Project Infrastructure:**

| Category | File Patterns | Specific Items |
|----------|---------------|----------------|
| Docker | `docker-compose.yml` | Development orchestration |
| Environment | `.env.example` | Environment variable template |
| Documentation | `README.md` | Project documentation updates |

**Supported Report Types (Explicit):**

| Report Name | Sidecar Type | Model |
|-------------|--------------|-------|
| `account.report_invoice` | `invoice` | `account.move` |
| `sale.report_saleorder` | `quote` | `sale.order` |
| `stock.report_deliveryslip` | `delivery_slip` | `stock.picking` |

**Supported Languages:**

| Language Code | Status |
|---------------|--------|
| `en_US` | ✅ Supported |
| All others | ❌ Out of scope |

### 0.6.2 Explicitly Out of Scope

**MUST NOT TOUCH (Per User Specification):**

| Category | Specific Exclusions | Rationale |
|----------|---------------------|-----------|
| Odoo Core | `odoo/**/*` | "Zero modifications to Odoo core" requirement |
| Database Schema | PostgreSQL DDL | "No database schema changes" requirement |
| Core Report Base | Native `ir.actions.report` implementation | Only extend via `_inherit`, never modify |
| Native QWeb Engine | QWeb template processing | Preserved as fallback mechanism |
| User Authentication | `res.users`, `ir.rules` | Outside security scope |
| Existing Report XML | `addons/*/report/*.xml` | Reference only, no modifications |

**Related Features NOT Specified:**

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-record batch printing | ❌ Out of scope | "Single-record rendering only" per spec |
| Template customization UI | ❌ Out of scope | Templates are developer-managed |
| Dynamic template selection | ❌ Out of scope | Fixed template-per-report-type mapping |
| PDF digital signatures | ❌ Out of scope | Not in requirements |
| PDF/A compliance | ❌ Out of scope | Not in requirements |
| Watermarks | ❌ Out of scope | Not in requirements |

**Internationalization:**

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-language templates | ❌ Out of scope | "en_US only" per spec |
| RTL language support | ❌ Out of scope | Not in requirements |
| Currency formatting | ⚠️ Passed through | Data serialized from Odoo includes formatted values |
| Date formatting | ⚠️ Passed through | Data serialized from Odoo includes formatted values |

**Performance Optimizations Beyond Requirements:**

| Feature | Status | Notes |
|---------|--------|-------|
| PDF caching layer | ❌ Out of scope | Not in requirements |
| CDN integration | ❌ Out of scope | Not in requirements |
| Horizontal auto-scaling | ❌ Out of scope | Manual scaling assumed |
| Database read replicas | ❌ Out of scope | Odoo manages data access |

**Refactoring Unrelated to Core Objectives:**

| Area | Status | Notes |
|------|--------|-------|
| Existing Odoo modules | ❌ Out of scope | No changes to account, sale, stock modules |
| Existing report templates | ❌ Out of scope | QWeb templates preserved unchanged |
| Odoo web client | ❌ Out of scope | Print button behavior unchanged |
| Legacy compatibility | ❌ Out of scope | Odoo 17+ only |

**Additional Tooling NOT Mentioned:**

| Tool/Feature | Status | Notes |
|--------------|--------|-------|
| Admin dashboard | ❌ Out of scope | Not in requirements |
| Metrics visualization | ❌ Out of scope | Structured logging only |
| Alerting integration | ❌ Out of scope | Not in requirements |
| CI/CD pipeline | ❌ Out of scope | Manual deployment assumed |

**Future Enhancements Explicitly Deferred:**

| Enhancement | Status | Migration Path |
|-------------|--------|----------------|
| Batch rendering | Deferred | Contract changes required for multi-PDF response |
| i18n support | Deferred | Add translation JSON files, modify TemplateService |
| Additional report types | Deferred | Extend SIDECAR_REPORT_TYPES mapping |
| Template versioning | Deferred | Add version field to request schema |
| A/B testing for layouts | Deferred | Add variant selection logic |

### 0.6.3 Boundary Enforcement

**Code Modification Boundaries:**

```
✅ ALLOWED TO MODIFY/CREATE              ❌ NEVER MODIFY
─────────────────────────────────────    ─────────────────────────────────────
sidecar/**/*                             odoo/**/*
addons/document_sidecar_bridge/**/*      addons/account/**/*
contracts/**/*                           addons/sale/**/*
docker-compose.yml                       addons/stock/**/*
.env.example                             PostgreSQL schema
README.md                                Existing ir.actions.report behavior
```

**Runtime Boundary Enforcement:**

The sidecar service enforces boundaries through:
- Zod schema validation rejects unknown report types
- Only three report types accepted: `invoice`, `quote`, `delivery_slip`
- No database connectivity (stateless by design)
- No Odoo ORM access (receives pre-serialized JSON)

The Odoo bridge enforces boundaries through:
- `SIDECAR_REPORT_TYPES` whitelist limits intercepted reports
- Fallback to `super()` for all non-whitelisted reports
- Feature toggle via `document_sidecar.enabled` parameter

## 0.7 Execution Parameters

### 0.7.1 Special Execution Instructions

**Process-Specific Requirements:**

| Requirement | Implementation Detail |
|-------------|----------------------|
| Non-interactive Docker builds | Use `DEBIAN_FRONTEND=noninteractive` for apt-get |
| Test execution without watch mode | `CI=true npm test` or `vitest run` |
| No user input prompts | All configurations via environment variables |
| Puppeteer containerization | Use `--no-sandbox` flags in Docker |

**Tools and Platforms:**

| Tool | Usage | Notes |
|------|-------|-------|
| Node.js 20 LTS | Sidecar runtime | Use official node:20 Docker image |
| Docker | Container deployment | Multi-stage builds for production |
| Docker Compose | Local development | Orchestrate sidecar, Odoo, PostgreSQL |
| npm | Package management | Use `npm ci` for reproducible builds |
| Vitest | Test runner | Fast, Vite-native testing |
| Pino | Logging | JSON structured logging |

**Quality Requirements:**

| Aspect | Requirement | Enforcement |
|--------|-------------|-------------|
| TypeScript strict mode | Enabled | `tsconfig.json` with `"strict": true` |
| Type coverage | All exports typed | No `any` types in public interfaces |
| Test coverage | Unit tests for services | Vitest with coverage reporting |
| Linting | No runtime errors | TypeScript compiler validation |
| Logging | Structured JSON | Pino logger throughout |

**Code Style Requirements:**

- ES modules (`"type": "module"` in package.json)
- Named exports preferred over default exports
- Async/await over callbacks
- Zod for runtime validation
- Descriptive error messages with context

**Deployment Considerations:**

| Environment | Deployment Method |
|-------------|-------------------|
| Development | `docker-compose up` |
| Production | Separate sidecar container with orchestration |
| Staging | Mirror production with separate config |

### 0.7.2 Constraints and Boundaries

**Technical Constraints:**

| Constraint | Impact | Mitigation |
|------------|--------|------------|
| Node.js 20 LTS only | Limits language features | Use stable ES2022+ features |
| Puppeteer bundled Chromium | Large container size (~400MB) | Multi-stage Docker builds |
| Single-record rendering | No batch support | Log warning, render first record |
| en_US language only | No localization | Pass language parameter for future |
| 5-second response target | Limits document complexity | Optimize templates and CSS |

**Process Constraints:**

| Constraint | Description |
|------------|-------------|
| No Odoo core modifications | All integration via addon extension |
| Contract-first development | Zod schemas define interface |
| Stateless sidecar | No persistent storage in TypeScript service |
| Feature toggle required | `document_sidecar.enabled` controls routing |

**Output Constraints:**

| Output | Format | Size Limit |
|--------|--------|------------|
| PDF response | Base64-encoded | Practical limit ~50MB (base64 overhead) |
| Error responses | JSON with error code | Standard structure |
| Logs | JSON (Pino format) | Structured for aggregation |

**Compatibility Requirements:**

| System | Version | Notes |
|--------|---------|-------|
| Odoo | 17.0+ | Uses `_inherit` extension pattern |
| Python | 3.10+ | Match Odoo requirements |
| Node.js | 20.x LTS | Long-term support version |
| PostgreSQL | 14+ | Existing Odoo database |
| Docker | 24+ | Multi-stage build support |

### 0.7.3 Environment Configuration

**Required Environment Variables (Sidecar):**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | No | 3000 | HTTP server port |
| `API_KEY` | Yes | - | API authentication key |
| `SECRET_KEY` | Yes | - | HMAC signing secret |
| `LOG_LEVEL` | No | info | Logging verbosity (trace/debug/info/warn/error) |
| `NODE_ENV` | No | development | Environment mode |
| `RATE_LIMIT_MAX` | No | 100 | Max requests per window |
| `RATE_LIMIT_WINDOW` | No | 60000 | Rate limit window in ms |

**Required Odoo Configuration Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `document_sidecar.enabled` | No | False | Feature toggle |
| `document_sidecar.url` | Yes* | http://localhost:3000 | Sidecar base URL |
| `document_sidecar.api_key` | Yes* | - | API authentication key |
| `document_sidecar.secret_key` | Yes* | - | HMAC signing secret |
| `document_sidecar.timeout` | No | 30 | Request timeout (seconds) |

*Required when `document_sidecar.enabled` is True

### 0.7.4 Build Commands

**TypeScript Sidecar:**

```bash
# Install dependencies
cd sidecar && npm ci

#### Type check
npm run typecheck

#### Run tests
npm run test

#### Build for production
npm run build

#### Start production server
npm start

#### Start development server
npm run dev
```

**Docker Commands:**

```bash
# Build sidecar image
docker build -t document-sidecar ./sidecar

#### Start full development stack
docker-compose up -d

#### View logs
docker-compose logs -f sidecar

#### Stop services
docker-compose down
```

**Odoo Module Installation:**

```bash
# Install bridge module
./odoo-bin -c odoo.conf -i document_sidecar_bridge

#### Update bridge module
./odoo-bin -c odoo.conf -u document_sidecar_bridge
```

### 0.7.5 Validation Commands

**Health Checks:**

```bash
# Sidecar health
curl http://localhost:3000/health

#### Sidecar readiness
curl http://localhost:3000/ready
```

**Smoke Test:**

```bash
# Generate test invoice PDF
curl -X POST http://localhost:3000/api/v1/render \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-HMAC-Signature: $SIGNATURE" \
  -d @tests/fixtures/sample-invoice.json \
  | jq -r '.pdf_base64' | base64 -d > test-invoice.pdf
```

**Test Execution:**

```bash
# Run all tests
npm run test

#### Run with coverage
npm run test:coverage

#### Run specific test file
npm run test -- template.service.test.ts
```

## 0.8 Special Instructions

### 0.8.1 Task-Specific Requirements

**User-Emphasized Directives (Verbatim):**

1. **"Zero modifications to Odoo core ORM, database schema, or existing report infrastructure"**
   - Implementation: All changes via standard addon `_inherit` extension
   - Files to never modify: `odoo/**/*`
   - Validation: Code review must confirm no core changes

2. **"100% backward compatibility—existing report buttons/actions work unchanged"**
   - Implementation: Fallback mechanism ensures QWeb rendering on any sidecar failure
   - Validation: Test print actions with sidecar disabled

3. **"Automatic fallback to native QWeb if sidecar is unavailable"**
   - Implementation: Try/except in `_render_qweb_pdf` catches `SidecarUnavailable` and delegates to `super()`
   - Logging: Warning logged on every fallback occurrence

4. **"Single-record rendering only. Batch printing is explicitly OUT OF SCOPE"**
   - Implementation: When `len(res_ids) > 1`, render only first record, log warning
   - Contract: `record_ids` array accepted but only first element used

5. **"Templates support en_US only. i18n is OUT OF SCOPE"**
   - Implementation: `language` parameter passed but ignored by templates
   - Future path: Add translation JSON files when needed

6. **"Zod schemas are the source of truth"**
   - Implementation: TypeScript types inferred from Zod schemas using `z.infer<>`
   - Contract sync: JSON Schema exported from Zod for documentation

7. **"Sidecar holds no business state. Each request is fully self-contained"**
   - Implementation: No database, no cache, no session state
   - Design: All data for rendering passed in request payload

8. **"Any sidecar failure results in automatic fallback—never a user-facing error"**
   - Implementation: Comprehensive exception handling in Odoo bridge
   - Coverage: Connection errors, timeouts, HTTP errors, validation errors

### 0.8.2 Pattern Adherence Requirements

**Follow Existing Patterns In:**

| Pattern Source | Pattern Type | Apply To |
|----------------|--------------|----------|
| `addons/account/models/ir_actions_report.py` | `_inherit` extension | `document_sidecar_bridge` extension |
| `addons/account/report/account_invoice_report.xml` | Invoice layout structure | `invoice.hbs` template |
| `addons/sale/report/ir_actions_report_templates.xml` | Quote layout structure | `quote.hbs` template |
| `addons/stock/report/report_deliveryslip.xml` | Delivery slip layout | `delivery_slip.hbs` template |
| Odoo addon structure | `__manifest__.py` pattern | Bridge module manifest |

**Maintain Compatibility With:**

| System | Version | Compatibility Notes |
|--------|---------|---------------------|
| Odoo 17.0 | 17.0+ | Use 17.0 API patterns |
| Python 3.11 | 3.10+ | No 3.12+ only features |
| Node.js 20 LTS | 20.x | ES2022+ features allowed |
| Fastify 4.x | 4.x | Use v4 plugin API |

**Match Existing Code Style:**

- Python: Follow Odoo coding guidelines (snake_case, docstrings)
- TypeScript: Strict mode, named exports, async/await
- Templates: Match QWeb visual output, not implementation

### 0.8.3 Quality Criteria

**Performance Requirements:**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Standard document latency | < 3 seconds | Request → Response time |
| Large document (50+ lines) | < 10 seconds | Request → Response time |
| Concurrent requests | 20 simultaneous | Load test |
| Memory per page | ~50MB | Puppeteer page overhead |
| Browser pool size | 5 pages max | Configuration limit |

**Reliability Requirements:**

| Metric | Target | Implementation |
|--------|--------|----------------|
| Fallback success rate | 100% | Comprehensive exception handling |
| Graceful shutdown | Complete in-flight | SIGTERM handler in sidecar |
| Health endpoint | Always responsive | Separate from render pipeline |

**Security Requirements:**

| Requirement | Implementation | Validation |
|-------------|----------------|------------|
| API key authentication | X-API-Key header | Reject 401 on invalid/missing |
| Request integrity | HMAC-SHA256 signature | Reject 401 on signature mismatch |
| Rate limiting | 100 req/min default | Return 429 when exceeded |
| No data persistence | Stateless design | Audit service for storage calls |
| TLS in production | HTTPS required | Deployment configuration |

### 0.8.4 Documentation Requirements

**Code Documentation:**

- TypeScript: JSDoc comments on all public functions
- Python: Docstrings on all public methods
- Complex logic: Inline comments explaining rationale

**User Documentation:**

- README.md: Architecture overview, setup instructions
- .env.example: Document all environment variables
- OpenAPI spec: Complete API documentation

**Operational Documentation:**

- Health check procedures
- Troubleshooting guide for common failures
- Key rotation procedure

### 0.8.5 Delivery Slip Special Handling

**Per User Specification:**

The delivery slip template intentionally sets `unit_price` and `subtotal` to 0 for all line items. This is documented in the code:

```python
"""
NOTE: Delivery slips intentionally set unit_price and subtotal to 0
as these documents show quantities only, not pricing information.
This is standard business practice for shipping/logistics documents.
"""
```

This is NOT a bug but intentional business logic:
- Delivery slips are shipping documents, not invoices
- Pricing information is confidential and not shown to warehouse/logistics staff
- Only quantities and product names are relevant for picking operations

### 0.8.6 Error Code Mapping

**Sidecar Error Codes to HTTP Status:**

| Error Code | HTTP Status | When Triggered |
|------------|-------------|----------------|
| `VALIDATION_ERROR` | 400 | Zod schema validation fails |
| `AUTH_FAILED` | 401 | Invalid API key or HMAC signature |
| `TEMPLATE_NOT_FOUND` | 404 | Unknown report_type in request |
| `RATE_LIMITED` | 429 | Request rate exceeds limit |
| `RENDER_FAILED` | 500 | Puppeteer rendering error |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

**Odoo Bridge Error Handling:**

| Exception Type | Action | Logging Level |
|----------------|--------|---------------|
| `SidecarUnavailable` | Fallback to QWeb | WARNING |
| `requests.ConnectionError` | Raise `SidecarUnavailable` | WARNING |
| `requests.Timeout` | Raise `SidecarUnavailable` | WARNING |
| HTTP 4xx | Log error, fallback | ERROR |
| HTTP 5xx | Log error, fallback | ERROR |
| Unexpected exception | Log error, fallback | ERROR (with traceback)

