# Odoo

[![Build Status](https://runbot.odoo.com/runbot/badge/flat/1/master.svg)](https://runbot.odoo.com/runbot)
[![Tech Doc](https://img.shields.io/badge/master-docs-875A7B.svg?style=flat&colorA=8F8F8F)](https://www.odoo.com/documentation/master)
[![Help](https://img.shields.io/badge/master-help-875A7B.svg?style=flat&colorA=8F8F8F)](https://www.odoo.com/forum/help-1)
[![Nightly Builds](https://img.shields.io/badge/master-nightly-875A7B.svg?style=flat&colorA=8F8F8F)](https://nightly.odoo.com/)

Odoo is a suite of web based open source business apps.

The main Odoo Apps include an [Open Source CRM](https://www.odoo.com/page/crm),
[Website Builder](https://www.odoo.com/app/website),
[eCommerce](https://www.odoo.com/app/ecommerce),
[Warehouse Management](https://www.odoo.com/app/inventory),
[Project Management](https://www.odoo.com/app/project),
[Billing &amp; Accounting](https://www.odoo.com/app/accounting),
[Point of Sale](https://www.odoo.com/app/point-of-sale-shop),
[Human Resources](https://www.odoo.com/app/employees),
[Marketing](https://www.odoo.com/app/social-marketing),
[Manufacturing](https://www.odoo.com/app/manufacturing),
[...](https://www.odoo.com/)

Odoo Apps can be used as stand-alone applications, but they also integrate seamlessly so you get
a full-featured [Open Source ERP](https://www.odoo.com) when you install several Apps.

## Getting started with Odoo

For a standard installation please follow the [Setup instructions](https://www.odoo.com/documentation/master/administration/install/install.html)
from the documentation.

To learn the software, we recommend the [Odoo eLearning](https://www.odoo.com/slides),
or [Scale-up, the business game](https://www.odoo.com/page/scale-up-business-game).
Developers can start with [the developer tutorials](https://www.odoo.com/documentation/master/developer/howtos.html).

## Security

If you believe you have found a security issue, check our [Responsible Disclosure page](https://www.odoo.com/security-report)
for details and get in touch with us via email.

---

## Document Sidecar Service

The Document Sidecar Service is a standalone TypeScript microservice that extracts PDF document generation from Odoo's native QWeb/wkhtmltopdf pipeline into an independent, scalable service using Puppeteer (headless Chrome).

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         ODOO APPLICATION                         │
│                                                                 │
│  User Action (Print Invoice/Quote/Delivery Slip)                │
│         │                                                       │
│         ▼                                                       │
│  ir.actions.report._render_qweb_pdf()                          │
│         │                                                       │
│         ▼                                                       │
│  document_sidecar_bridge (Odoo Addon)                          │
│         │                                                       │
│         ├─── Sidecar enabled? ─── No ───▶ Native QWeb (wkhtmltopdf)
│         │                                                       │
│         Yes                                                     │
│         │                                                       │
│         ▼                                                       │
│  SidecarClient.render_report()                                 │
│         │                                                       │
│         └─── HTTP POST with JSON payload ───────────────────────┼─┐
│                                                                 │ │
└─────────────────────────────────────────────────────────────────┘ │
                                                                    │
┌─────────────────────────────────────────────────────────────────┐ │
│                    DOCUMENT SIDECAR SERVICE                      │◀┘
│                      (TypeScript/Fastify)                        │
│                                                                 │
│  POST /api/v1/render                                           │
│         │                                                       │
│         ├─── Rate Limiting                                     │
│         ├─── API Key + HMAC Authentication                     │
│         ├─── Zod Schema Validation                             │
│         │                                                       │
│         ▼                                                       │
│  TemplateService (Handlebars)                                  │
│         │                                                       │
│         ▼                                                       │
│  RendererService (Puppeteer/Chrome)                            │
│         │                                                       │
│         ▼                                                       │
│  Base64 PDF Response                                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Key Benefits:**
- **Independent Scalability**: Scale PDF rendering separately from Odoo
- **Type Safety**: Full TypeScript implementation with Zod validation
- **Modern Rendering**: Chrome-based PDF generation for superior output quality
- **Zero Core Modifications**: Integrates via standard Odoo addon extension patterns
- **Automatic Fallback**: Falls back to native QWeb if sidecar is unavailable

### Supported Document Types

| Report Type | Odoo Report Name | Model | Description |
|-------------|------------------|-------|-------------|
| `invoice` | `account.report_invoice` | `account.move` | Customer invoices and credit notes |
| `quote` | `sale.report_saleorder` | `sale.order` | Sales quotations and orders |
| `delivery_slip` | `stock.report_deliveryslip` | `stock.picking` | Delivery/shipping documents |

**Note:** Only single-record rendering is supported. The sidecar processes one document per request.

### Build and Run Instructions

#### Prerequisites

- Docker 24+ and Docker Compose
- Node.js 20 LTS (for local development without Docker)
- Running Odoo instance with PostgreSQL

#### Using Docker Compose (Recommended)

1. **Configure environment variables:**

   ```bash
   cp .env.example .env
   # Edit .env with your API_KEY and SECRET_KEY
   ```

2. **Start the full development stack:**

   ```bash
   docker-compose up -d
   ```

3. **Verify services are running:**

   ```bash
   # Check sidecar health
   curl http://localhost:3000/health
   
   # Check sidecar readiness
   curl http://localhost:3000/ready
   ```

4. **View logs:**

   ```bash
   docker-compose logs -f sidecar
   ```

5. **Stop services:**

   ```bash
   docker-compose down
   ```

#### Building the Sidecar Image Manually

```bash
# Build the Docker image
docker build -t document-sidecar ./sidecar

# Run the container
docker run -d \
  --name document-sidecar \
  -p 3000:3000 \
  -e API_KEY=your-api-key \
  -e SECRET_KEY=your-hmac-secret \
  document-sidecar
```

#### Local Development (Without Docker)

```bash
cd sidecar

# Install dependencies
npm ci

# Run type checking
npm run typecheck

# Run tests
npm run test

# Start development server
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

### Environment Variable Configuration

#### Sidecar Service Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | No | `3000` | HTTP server port |
| `API_KEY` | **Yes** | - | API authentication key (must match Odoo config) |
| `SECRET_KEY` | **Yes** | - | HMAC-SHA256 signing secret (must match Odoo config) |
| `LOG_LEVEL` | No | `info` | Logging verbosity: `trace`, `debug`, `info`, `warn`, `error` |
| `NODE_ENV` | No | `development` | Environment mode: `development`, `production` |
| `RATE_LIMIT_MAX` | No | `100` | Maximum requests per rate limit window |
| `RATE_LIMIT_WINDOW` | No | `60000` | Rate limit window duration in milliseconds |

#### Odoo Configuration Parameters

Configure these in Odoo via Settings → Technical → Parameters → System Parameters:

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `document_sidecar.enabled` | No | `False` | Enable/disable sidecar routing |
| `document_sidecar.url` | Yes* | `http://localhost:3000` | Sidecar service base URL |
| `document_sidecar.api_key` | Yes* | - | API key (must match sidecar `API_KEY`) |
| `document_sidecar.secret_key` | Yes* | - | HMAC secret (must match sidecar `SECRET_KEY`) |
| `document_sidecar.timeout` | No | `30` | Request timeout in seconds |

*Required when `document_sidecar.enabled` is `True`

**Important:** The `API_KEY` and `SECRET_KEY` values must be identical in both the sidecar environment and Odoo configuration parameters.

### Odoo Integration

The sidecar integrates with Odoo through the `document_sidecar_bridge` addon module:

#### Installing the Bridge Module

```bash
# Install the module
./odoo-bin -c odoo.conf -i document_sidecar_bridge

# Update the module after changes
./odoo-bin -c odoo.conf -u document_sidecar_bridge
```

#### How It Works

1. The `document_sidecar_bridge` module extends `ir.actions.report` using Odoo's `_inherit` mechanism
2. When a user prints a supported report type (invoice, quote, delivery slip), the bridge intercepts the call
3. If `document_sidecar.enabled` is `True`, the request is routed to the sidecar service
4. The sidecar generates the PDF and returns it as a base64-encoded response
5. If the sidecar fails for any reason, the bridge automatically falls back to native QWeb rendering

#### Report Type Mapping

The bridge maps Odoo report names to sidecar report types:

```python
SIDECAR_REPORT_TYPES = {
    'account.report_invoice': 'invoice',
    'sale.report_saleorder': 'quote',
    'stock.report_deliveryslip': 'delivery_slip',
}
```

### Troubleshooting

#### Sidecar Connection Failures

**Symptom:** PDFs still generate but logs show "Sidecar unavailable, falling back to QWeb"

**Cause:** The sidecar service is unreachable or returning errors

**Solutions:**
1. Verify the sidecar container is running:
   ```bash
   docker-compose ps
   curl http://localhost:3000/health
   ```
2. Check that `document_sidecar.url` in Odoo points to the correct address
3. Ensure network connectivity between Odoo and sidecar containers
4. Review sidecar logs for errors: `docker-compose logs sidecar`

**Note:** Automatic fallback to QWeb ensures users never see an error—PDFs are always generated.

#### Authentication Errors (401)

**Symptom:** Sidecar returns 401 AUTH_FAILED

**Solutions:**
1. Verify `API_KEY` matches between sidecar `.env` and Odoo `document_sidecar.api_key`
2. Verify `SECRET_KEY` matches between sidecar `.env` and Odoo `document_sidecar.secret_key`
3. Check for trailing whitespace in configuration values

#### Rate Limiting (429)

**Symptom:** Sidecar returns 429 RATE_LIMITED

**Solutions:**
1. Wait for the rate limit window to reset (default: 60 seconds)
2. Increase `RATE_LIMIT_MAX` in sidecar environment if legitimate high traffic
3. Review for automated processes making excessive requests

#### Template Not Found (404)

**Symptom:** Sidecar returns 404 TEMPLATE_NOT_FOUND

**Cause:** Request contains an unsupported `report_type`

**Solution:** Only `invoice`, `quote`, and `delivery_slip` are supported. Other report types should not be routed to the sidecar.

#### Configuration Parameter Setup

To enable the sidecar in Odoo:

1. Navigate to **Settings → Technical → Parameters → System Parameters**
2. Create or update the following parameters:
   - `document_sidecar.enabled` = `True`
   - `document_sidecar.url` = `http://sidecar:3000` (or your sidecar URL)
   - `document_sidecar.api_key` = Your API key
   - `document_sidecar.secret_key` = Your HMAC secret
   - `document_sidecar.timeout` = `30` (optional)

3. Ensure the values match your sidecar service configuration

#### Health Check Endpoints

The sidecar exposes two health endpoints for monitoring and orchestration:

| Endpoint | Purpose | Success Response |
|----------|---------|------------------|
| `GET /health` | Liveness check - is the service running? | `200 {"status": "ok"}` |
| `GET /ready` | Readiness check - is the service ready to accept requests? | `200 {"status": "ready"}` |

Use these endpoints for:
- Docker health checks
- Kubernetes liveness/readiness probes
- Load balancer health monitoring
- Uptime monitoring services

#### Viewing Logs

**Sidecar logs (Docker):**
```bash
docker-compose logs -f sidecar
```

**Sidecar logs (local):**
Logs are output to stdout in JSON format (Pino). Use `pino-pretty` for human-readable output:
```bash
npm run dev | npx pino-pretty
```

**Odoo bridge logs:**
Check Odoo server logs for messages from `document_sidecar_bridge`:
```bash
grep "document_sidecar" /var/log/odoo/odoo-server.log
```

### API Documentation

For complete API documentation, see the OpenAPI specification:

- **File:** `contracts/openapi.yaml`
- **Format:** OpenAPI 3.0

The specification documents:
- Request/response schemas
- Authentication requirements
- Error codes and responses
- Example payloads

You can view the specification using any OpenAPI-compatible tool such as Swagger UI, Redoc, or Postman.
