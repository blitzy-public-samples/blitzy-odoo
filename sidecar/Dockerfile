# =============================================================================
# Document Sidecar Service - Multi-Stage Dockerfile
# =============================================================================
# This Dockerfile builds and deploys the TypeScript PDF generation sidecar
# service. It uses a multi-stage build for optimal production image size.
#
# Features:
# - Node.js 20 LTS runtime
# - Puppeteer with system Chromium for PDF generation
# - Non-root user for enhanced security
# - Health check for container orchestration
# - Optimized layer caching
#
# Build: docker build -t document-sidecar ./sidecar
# Run:   docker run -p 3000:3000 --env-file .env document-sidecar
# =============================================================================

# =============================================================================
# Stage 1: Builder
# =============================================================================
# This stage compiles TypeScript to JavaScript and prepares the application
# for production. Dev dependencies are installed here for the build process
# but are not included in the final production image.
# =============================================================================
FROM node:20-slim AS builder

# Set working directory for the build
WORKDIR /app

# Copy package files first for better layer caching
# If package files haven't changed, npm ci can use cached layers
COPY package*.json ./

# Install all dependencies (including dev dependencies for TypeScript compilation)
# Using npm ci for reproducible builds from package-lock.json
RUN npm ci

# Copy TypeScript configuration
COPY tsconfig.json ./

# Copy source files
COPY src ./src

# Build TypeScript to JavaScript
# Output will be in the dist/ directory as configured in tsconfig.json
RUN npm run build

# =============================================================================
# Stage 2: Production
# =============================================================================
# This stage creates the minimal production image with only runtime dependencies.
# It includes Chromium and all required libraries for Puppeteer PDF generation.
# =============================================================================
FROM node:20-slim AS production

# Set working directory
WORKDIR /app

# -----------------------------------------------------------------------------
# Install Chromium and its dependencies for Puppeteer
# -----------------------------------------------------------------------------
# DEBIAN_FRONTEND=noninteractive prevents apt from prompting for user input
# --no-install-recommends reduces image size by not installing suggested packages
# rm -rf /var/lib/apt/lists/* cleans up apt cache to reduce final image size
#
# Note: libasound2t64 is the modern package name in Debian Bookworm (time_t 64-bit)
# Some older documentation may reference libasound2
# -----------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    # Chromium browser (used by Puppeteer for PDF rendering)
    chromium \
    # Font package for proper text rendering
    fonts-liberation \
    # Audio library (required by Chromium)
    libasound2t64 \
    # Accessibility toolkit bridge
    libatk-bridge2.0-0 \
    # Accessibility toolkit core
    libatk1.0-0 \
    # CUPS printing library
    libcups2 \
    # D-Bus message bus library
    libdbus-1-3 \
    # Direct Rendering Manager library
    libdrm2 \
    # Generic Buffer Management library
    libgbm1 \
    # GTK+ 3 library
    libgtk-3-0 \
    # Netscape Portable Runtime library
    libnspr4 \
    # Network Security Services library
    libnss3 \
    # X11-XCB bridge library
    libx11-xcb1 \
    # X11 Composite extension library
    libxcomposite1 \
    # X11 Damage extension library
    libxdamage1 \
    # X11 Xfixes extension library
    libxfixes3 \
    # X11 RandR extension library
    libxrandr2 \
    # X11 Screen Saver extension library
    libxss1 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# Puppeteer Configuration
# -----------------------------------------------------------------------------
# PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true prevents Puppeteer from downloading
# its bundled Chromium, since we're using the system-installed version
#
# PUPPETEER_EXECUTABLE_PATH tells Puppeteer where to find Chromium
#
# Note: When running Puppeteer in Docker, the renderer service should use
# these additional flags: --no-sandbox, --disable-setuid-sandbox, --disable-dev-shm-usage
# These are configured in the renderer service, not here in the Dockerfile
# -----------------------------------------------------------------------------
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# Set Node.js to production mode for optimizations
ENV NODE_ENV=production

# -----------------------------------------------------------------------------
# Copy Build Artifacts
# -----------------------------------------------------------------------------
# Copy only the necessary files from the builder stage:
# - dist/: Compiled JavaScript
# - node_modules/: Runtime dependencies (dev deps excluded via npm ci --omit=dev below)
# - package*.json: Required for npm and runtime metadata
# -----------------------------------------------------------------------------

# First, install only production dependencies to reduce node_modules size
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

# Copy compiled JavaScript from builder stage
COPY --from=builder /app/dist ./dist

# Copy templates directory (required at runtime for Handlebars rendering)
# Templates are not compiled and need to be copied from source
COPY src/templates ./dist/templates

# -----------------------------------------------------------------------------
# Security: Non-root User
# -----------------------------------------------------------------------------
# Running containers as root is a security risk. We create a dedicated user
# 'sidecar' with minimal permissions to run the application.
#
# The -r flag creates a system user/group (no home directory, no login shell)
# -----------------------------------------------------------------------------
RUN groupadd -r sidecar && useradd -r -g sidecar sidecar

# Change ownership of application files to the sidecar user
RUN chown -R sidecar:sidecar /app

# Switch to non-root user
USER sidecar

# -----------------------------------------------------------------------------
# Container Configuration
# -----------------------------------------------------------------------------

# Expose the application port (configurable via PORT env var, defaults to 3000)
EXPOSE 3000

# -----------------------------------------------------------------------------
# Health Check
# -----------------------------------------------------------------------------
# Docker and orchestration systems (Kubernetes, Docker Compose) use this to
# determine if the container is healthy and ready to receive traffic.
#
# Parameters:
# --interval=30s   Check every 30 seconds
# --timeout=10s    Consider unhealthy if check takes longer than 10s
# --start-period=5s  Grace period for container startup
# --retries=3      Mark unhealthy after 3 consecutive failures
#
# The health check calls the /health endpoint which returns 200 if healthy
# -----------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/health', r => process.exit(r.statusCode === 200 ? 0 : 1))"

# -----------------------------------------------------------------------------
# Container Labels
# -----------------------------------------------------------------------------
# OCI standard labels for container metadata
# These help with container management and documentation
# -----------------------------------------------------------------------------
LABEL org.opencontainers.image.title="Document Sidecar Service" \
      org.opencontainers.image.description="TypeScript PDF generation service using Puppeteer" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.vendor="Odoo Document Services" \
      org.opencontainers.image.source="https://github.com/odoo/odoo"

# -----------------------------------------------------------------------------
# Start Command
# -----------------------------------------------------------------------------
# Run the compiled JavaScript application
# The entry point is dist/index.js which starts the Fastify server
# -----------------------------------------------------------------------------
CMD ["node", "dist/index.js"]
