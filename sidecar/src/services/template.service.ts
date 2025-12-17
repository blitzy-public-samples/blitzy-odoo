/**
 * Handlebars Template Service for Document Sidecar
 *
 * This service manages the loading, compilation, and caching of Handlebars templates
 * for generating HTML content that will be converted to PDF documents. It handles:
 *
 * - Template loading from filesystem with caching to avoid repeated reads
 * - Partial registration for shared template components (header, footer, line-items)
 * - CSS stylesheet loading for print-optimized PDF styling
 * - Custom Handlebars helpers for data formatting (currency, numbers, dates)
 * - HTML rendering by combining templates with business data
 *
 * The service is stateless in terms of business data - all document data is passed
 * in via the render() method. However, it caches compiled templates in memory for
 * performance optimization.
 *
 * @module template.service
 * @see Agent Action Plan Sections 0.3.2, 0.5.1, 0.5.4
 */

import Handlebars from 'handlebars';
import { readFile } from 'fs/promises';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { logger } from '../utils/logger.js';
import type { ReportType } from '../contracts/request.schema.js';
import type { BaseDocumentData } from '../contracts/domain.types.js';

// =============================================================================
// DIRECTORY PATH CONFIGURATION (ES Module Compatible)
// =============================================================================

/**
 * Get the current file path from import.meta.url for ES module compatibility.
 * This replaces the CommonJS __filename global that is not available in ES modules.
 */
const __filename = fileURLToPath(import.meta.url);

/**
 * Get the directory name from the current file path.
 * This replaces the CommonJS __dirname global that is not available in ES modules.
 */
const __dirname = dirname(__filename);

/**
 * Base directory for all template files.
 * Located at sidecar/src/templates relative to this service file.
 */
const TEMPLATE_DIR = join(__dirname, '..', 'templates');

/**
 * Directory containing shared partial templates.
 * Partials are reusable template fragments (header, footer, line-items).
 */
const PARTIALS_DIR = join(TEMPLATE_DIR, 'partials');

/**
 * Directory containing CSS stylesheets for PDF rendering.
 * Contains print-optimized CSS for consistent PDF output.
 */
const STYLES_DIR = join(TEMPLATE_DIR, 'styles');

// =============================================================================
// TEMPLATE MAPPING CONFIGURATION
// =============================================================================

/**
 * Mapping of report types to their corresponding template file names.
 * Each report type has a dedicated Handlebars template file.
 *
 * Templates are located in the TEMPLATE_DIR directory:
 * - invoice.hbs: Invoice document template (account.report_invoice)
 * - quote.hbs: Quote/Sale Order template (sale.report_saleorder)
 * - delivery_slip.hbs: Delivery slip template (stock.report_deliveryslip)
 */
const TEMPLATE_FILES: Record<ReportType, string> = {
  invoice: 'invoice.hbs',
  quote: 'quote.hbs',
  delivery_slip: 'delivery_slip.hbs',
};

/**
 * List of partial template names to be registered with Handlebars.
 * These partials are shared across all document templates.
 *
 * Partials are located in the PARTIALS_DIR directory:
 * - header.hbs: Document header with company logo and information
 * - footer.hbs: Document footer with notes and terms
 * - line-items.hbs: Table of product/service line items
 */
const PARTIAL_FILES = ['header', 'footer', 'line-items'] as const;

// =============================================================================
// TEMPLATE SERVICE CLASS
// =============================================================================

/**
 * Handlebars template service for HTML generation.
 *
 * Manages the complete template lifecycle including:
 * - Loading and compiling templates from the filesystem
 * - Caching compiled templates for performance
 * - Registering shared partials (header, footer, line-items)
 * - Registering custom Handlebars helpers
 * - Loading CSS stylesheets for PDF styling
 * - Rendering HTML output from templates and data
 *
 * @example
 * ```typescript
 * import { templateService } from './services/template.service.js';
 *
 * const html = await templateService.render('invoice', invoiceData, 'en_US');
 * // html contains complete HTML document ready for PDF conversion
 * ```
 */
export class TemplateService {
  /**
   * Cache for compiled Handlebars templates.
   * Key: report type string (e.g., 'invoice')
   * Value: Compiled Handlebars template delegate function
   */
  private templateCache: Map<string, Handlebars.TemplateDelegate> = new Map();

  /**
   * Flag indicating whether partials have been registered.
   * Partials are registered once on first use to avoid duplicate registration.
   */
  private partialsRegistered = false;

  /**
   * Cached CSS content for PDF styling.
   * Loaded once and reused for all template renders.
   * null indicates CSS has not been loaded yet.
   */
  private cssContent: string | null = null;

  /**
   * Creates a new TemplateService instance.
   * Registers custom Handlebars helpers during construction.
   */
  constructor() {
    this.registerHelpers();
  }

  // ===========================================================================
  // HELPER REGISTRATION
  // ===========================================================================

  /**
   * Registers custom Handlebars helpers for template rendering.
   *
   * Available helpers:
   * - formatCurrency: Format a number as currency with symbol
   * - formatNumber: Format a number with specified decimal places
   * - formatDate: Pass through pre-formatted date string from Odoo
   * - eq: Equality comparison helper for conditionals
   * - neq: Not equal comparison helper for conditionals
   * - inc: Increment a number by 1 (for line numbering)
   * - gt: Greater than comparison helper
   * - lt: Less than comparison helper
   * - and: Logical AND helper
   * - or: Logical OR helper
   * - join: Join array elements with separator
   * - default: Return default value if first value is falsy
   *
   * @private
   */
  private registerHelpers(): void {
    /**
     * Format a number as currency with the given symbol.
     * @example {{formatCurrency totalAmount "$"}} -> "$1,234.56"
     */
    Handlebars.registerHelper(
      'formatCurrency',
      (amount: number | undefined | null, symbol: string): string => {
        if (amount === undefined || amount === null || isNaN(amount)) {
          return `${symbol}0.00`;
        }
        // Format with 2 decimal places and thousand separators
        const formatted = amount.toLocaleString('en-US', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        });
        return `${symbol}${formatted}`;
      }
    );

    /**
     * Format a number with specified decimal places.
     * @example {{formatNumber quantity 2}} -> "10.50"
     */
    Handlebars.registerHelper(
      'formatNumber',
      (value: number | undefined | null, decimals: number = 2): string => {
        if (value === undefined || value === null || isNaN(value)) {
          return '0';
        }
        const decimalPlaces = typeof decimals === 'number' ? decimals : 2;
        return value.toFixed(decimalPlaces);
      }
    );

    /**
     * Format a date string (pass-through since Odoo pre-formats dates).
     * @example {{formatDate invoice_date}} -> "2024-01-15"
     */
    Handlebars.registerHelper(
      'formatDate',
      (dateStr: string | undefined | null): string => {
        if (!dateStr) {
          return '';
        }
        // Dates are pre-formatted by Odoo, just return as-is
        return dateStr;
      }
    );

    /**
     * Equality comparison helper for conditional rendering.
     * @example {{#if (eq status "paid")}}Paid{{/if}}
     */
    Handlebars.registerHelper(
      'eq',
      (a: unknown, b: unknown): boolean => {
        return a === b;
      }
    );

    /**
     * Not equal comparison helper for conditional rendering.
     * @example {{#if (neq status "draft")}}Not Draft{{/if}}
     */
    Handlebars.registerHelper(
      'neq',
      (a: unknown, b: unknown): boolean => {
        return a !== b;
      }
    );

    /**
     * Increment a number by 1 (useful for line numbering starting from 1).
     * @example {{inc @index}} -> "1" when @index is 0
     */
    Handlebars.registerHelper(
      'inc',
      (value: number): number => {
        if (typeof value !== 'number' || isNaN(value)) {
          return 1;
        }
        return value + 1;
      }
    );

    /**
     * Greater than comparison helper.
     * @example {{#if (gt amount 0)}}Has Amount{{/if}}
     */
    Handlebars.registerHelper(
      'gt',
      (a: number | undefined | null, b: number): boolean => {
        if (a === undefined || a === null) {
          return false;
        }
        return a > b;
      }
    );

    /**
     * Less than comparison helper.
     * @example {{#if (lt remaining 10)}}Low Stock{{/if}}
     */
    Handlebars.registerHelper(
      'lt',
      (a: number | undefined | null, b: number): boolean => {
        if (a === undefined || a === null) {
          return false;
        }
        return a < b;
      }
    );

    /**
     * Logical AND helper.
     * @example {{#if (and hasDiscount isActive)}}Apply Discount{{/if}}
     */
    Handlebars.registerHelper(
      'and',
      (...args: unknown[]): boolean => {
        // Remove the Handlebars options object (last argument)
        const values = args.slice(0, -1);
        return values.every(Boolean);
      }
    );

    /**
     * Logical OR helper.
     * @example {{#if (or hasPhone hasEmail)}}Has Contact{{/if}}
     */
    Handlebars.registerHelper(
      'or',
      (...args: unknown[]): boolean => {
        // Remove the Handlebars options object (last argument)
        const values = args.slice(0, -1);
        return values.some(Boolean);
      }
    );

    /**
     * Join array elements with a separator.
     * @example {{join taxNames ", "}} -> "VAT 20%, Local Tax 2%"
     */
    Handlebars.registerHelper(
      'join',
      (array: string[] | undefined | null, separator: string): string => {
        if (!array || !Array.isArray(array)) {
          return '';
        }
        const sep = typeof separator === 'string' ? separator : ', ';
        return array.join(sep);
      }
    );

    /**
     * Return default value if first value is falsy.
     * @example {{default description "No description"}}
     */
    Handlebars.registerHelper(
      'default',
      (value: unknown, defaultValue: unknown): unknown => {
        return value || defaultValue;
      }
    );

    /**
     * Calculate colspan for section rows in line items table.
     * Base columns: Description, Quantity, Unit Price, Amount = 4
     * Plus optional: Discount, Taxes
     * @example {{calculateSectionColspan hasDiscount hasTaxes}} -> 4, 5, or 6
     */
    Handlebars.registerHelper(
      'calculateSectionColspan',
      (hasDiscount: boolean | undefined, hasTaxes: boolean | undefined): number => {
        // Base columns: Description, Quantity, Unit Price, Amount
        let colspan = 4;
        if (hasDiscount) {
          colspan += 1;
        }
        if (hasTaxes) {
          colspan += 1;
        }
        return colspan;
      }
    );

    /**
     * Get document title based on invoice metadata (move_type, state, proforma).
     * Returns appropriate title for Invoice, Credit Note, Vendor Bill, etc.
     * @example {{getDocumentTitle data.metadata}} -> "Invoice" or "Draft Credit Note"
     */
    Handlebars.registerHelper(
      'getDocumentTitle',
      (metadata: Record<string, unknown> | undefined): string => {
        if (!metadata) {
          return 'Invoice';
        }

        const moveType = metadata.move_type as string | undefined;
        const state = metadata.state as string | undefined;
        const proforma = metadata.proforma as boolean | undefined;

        // Default title if move_type is not set
        if (!moveType) {
          return 'Invoice';
        }

        // Build title based on move_type, state, and proforma flag
        let title = '';

        if (proforma) {
          // Proforma documents
          switch (moveType) {
            case 'out_invoice':
              title = state === 'draft' ? 'Draft Proforma Invoice' :
                      state === 'cancel' ? 'Cancelled Proforma Invoice' : 'Proforma Invoice';
              break;
            case 'out_refund':
              title = state === 'draft' ? 'Draft Proforma Credit Note' :
                      state === 'cancel' ? 'Cancelled Proforma Credit Note' : 'Proforma Credit Note';
              break;
            case 'in_invoice':
              title = 'Proforma Vendor Bill';
              break;
            case 'in_refund':
              title = 'Proforma Vendor Credit Note';
              break;
            default:
              title = 'Proforma Invoice';
          }
        } else {
          // Regular documents
          switch (moveType) {
            case 'out_invoice':
              title = state === 'draft' ? 'Draft Invoice' :
                      state === 'cancel' ? 'Cancelled Invoice' : 'Invoice';
              break;
            case 'out_refund':
              title = state === 'draft' ? 'Draft Credit Note' :
                      state === 'cancel' ? 'Cancelled Credit Note' : 'Credit Note';
              break;
            case 'in_invoice':
              title = 'Vendor Bill';
              break;
            case 'in_refund':
              title = 'Vendor Credit Note';
              break;
            default:
              title = 'Invoice';
          }
        }

        return title;
      }
    );

    logger.debug('Handlebars helpers registered');
  }

  // ===========================================================================
  // PARTIAL REGISTRATION
  // ===========================================================================

  /**
   * Registers shared partial templates with Handlebars.
   *
   * Partials are loaded from the partials directory and registered once.
   * Subsequent calls to this method are no-ops if partials are already registered.
   *
   * Registered partials:
   * - header: Document header with company logo and information
   * - footer: Document footer with notes, terms, and page numbers
   * - line-items: Product/service line items table
   *
   * @throws Error if a partial file cannot be read from the filesystem
   * @private
   */
  private async registerPartials(): Promise<void> {
    // Skip if partials are already registered
    if (this.partialsRegistered) {
      return;
    }

    logger.info('Registering Handlebars partials');

    for (const partialName of PARTIAL_FILES) {
      const partialPath = join(PARTIALS_DIR, `${partialName}.hbs`);

      try {
        const content = await readFile(partialPath, 'utf-8');
        Handlebars.registerPartial(partialName, content);
        logger.debug({ partialName, partialPath }, 'Partial registered');
      } catch (error) {
        logger.error(
          { error, partialName, partialPath },
          'Failed to load partial template'
        );
        throw new Error(`Failed to load partial: ${partialName}`);
      }
    }

    this.partialsRegistered = true;
    logger.info(
      { partialCount: PARTIAL_FILES.length },
      'All partials registered successfully'
    );
  }

  // ===========================================================================
  // CSS LOADING
  // ===========================================================================

  /**
   * Loads and caches the CSS stylesheet for PDF rendering.
   *
   * The CSS is loaded from the styles directory and cached in memory.
   * Subsequent calls return the cached content without filesystem access.
   *
   * If the CSS file cannot be loaded, an empty string is returned and
   * a warning is logged. This allows templates to render even without
   * styling (graceful degradation).
   *
   * @returns Promise resolving to CSS content string
   * @private
   */
  private async loadStyles(): Promise<string> {
    // Return cached CSS if already loaded
    if (this.cssContent !== null) {
      return this.cssContent;
    }

    const cssPath = join(STYLES_DIR, 'pdf.css');

    try {
      this.cssContent = await readFile(cssPath, 'utf-8');
      logger.debug({ cssPath, cssLength: this.cssContent.length }, 'CSS styles loaded');
      return this.cssContent;
    } catch (error) {
      // Log warning but continue - templates can render without styles
      logger.warn(
        { error, cssPath },
        'Failed to load CSS styles, using empty stylesheet'
      );
      this.cssContent = '';
      return this.cssContent;
    }
  }

  // ===========================================================================
  // TEMPLATE LOADING
  // ===========================================================================

  /**
   * Loads and compiles a Handlebars template for the specified report type.
   *
   * Templates are loaded from the filesystem on first use and compiled into
   * Handlebars template delegate functions. Compiled templates are cached
   * in memory for performance - subsequent calls return the cached template.
   *
   * @param reportType - The type of report template to load ('invoice', 'quote', 'delivery_slip')
   * @returns Promise resolving to compiled Handlebars template delegate
   * @throws Error if the report type is unknown or template file cannot be read
   * @private
   */
  private async loadTemplate(
    reportType: ReportType
  ): Promise<Handlebars.TemplateDelegate> {
    // Check cache first
    const cached = this.templateCache.get(reportType);
    if (cached) {
      logger.debug({ reportType }, 'Using cached template');
      return cached;
    }

    // Validate report type
    const templateFile = TEMPLATE_FILES[reportType];
    if (!templateFile) {
      logger.error({ reportType }, 'Unknown report type requested');
      throw new Error(`Unknown report type: ${reportType}`);
    }

    const templatePath = join(TEMPLATE_DIR, templateFile);

    try {
      // Read template file from filesystem
      const content = await readFile(templatePath, 'utf-8');

      // Compile template with Handlebars
      const compiled = Handlebars.compile(content);

      // Cache compiled template
      this.templateCache.set(reportType, compiled);

      logger.info(
        { reportType, templatePath, templateLength: content.length },
        'Template loaded and compiled'
      );

      return compiled;
    } catch (error) {
      logger.error(
        { error, reportType, templatePath },
        'Failed to load template file'
      );
      throw new Error(`Template not found: ${reportType}`);
    }
  }

  // ===========================================================================
  // PUBLIC API
  // ===========================================================================

  /**
   * Renders an HTML document from a template and business data.
   *
   * This is the main entry point for template rendering. It:
   * 1. Ensures partials are registered (header, footer, line-items)
   * 2. Loads and compiles the appropriate template for the report type
   * 3. Loads the CSS stylesheet for PDF styling
   * 4. Combines template with data to produce final HTML output
   *
   * The rendered HTML is a complete document ready for PDF conversion
   * via Puppeteer, including inline CSS styles.
   *
   * @param reportType - Type of document to render ('invoice', 'quote', 'delivery_slip')
   * @param data - Business data payload containing company, partner, lines, totals, metadata
   * @param language - Language code for rendering (currently only 'en_US' supported)
   * @returns Promise resolving to complete HTML document string
   * @throws Error if template cannot be loaded or partials fail to register
   *
   * @example
   * ```typescript
   * const html = await templateService.render('invoice', {
   *   company: { name: 'Acme Corp', ... },
   *   partner: { name: 'John Doe', ... },
   *   lines: [{ sequence: 1, product_name: 'Widget', ... }],
   *   totals: { subtotal: 100, total: 120, ... },
   *   metadata: { number: 'INV-001', date: '2024-01-15', ... }
   * }, 'en_US');
   * ```
   */
  async render(
    reportType: ReportType,
    data: BaseDocumentData,
    language: string = 'en_US'
  ): Promise<string> {
    logger.debug(
      { reportType, language, documentNumber: data.metadata?.number },
      'Rendering template'
    );

    // Ensure partials are registered (idempotent operation)
    await this.registerPartials();

    // Load and compile template (uses cache if available)
    const template = await this.loadTemplate(reportType);

    // Load CSS styles (uses cache if available)
    const css = await this.loadStyles();

    // Prepare template context with all necessary data
    // NOTE: Templates expect data to be nested under a 'data' key
    // e.g., {{data.company.name}}, {{data.metadata.number}}
    // This matches the JSON fixture structure: { request_id, report_type, data: {...} }
    const context = {
      // Keep business data nested under 'data' key as templates expect
      data,
      // Include CSS for inline styling in HTML
      css,
      // Language code (for future i18n support)
      language,
      // Report type (useful for conditional rendering in templates)
      reportType,
      // Current year for copyright notices
      currentYear: new Date().getFullYear(),
    };

    // Render HTML using compiled template and context
    const html = template(context);

    logger.debug(
      { reportType, htmlLength: html.length, documentNumber: data.metadata?.number },
      'Template rendered successfully'
    );

    return html;
  }

  /**
   * Checks if a template exists for the given report type.
   *
   * This method performs a synchronous check against the known template
   * mappings. It does not verify filesystem access - only that the
   * report type is recognized.
   *
   * @param reportType - Report type string to check
   * @returns true if a template exists for this report type, false otherwise
   *
   * @example
   * ```typescript
   * if (templateService.hasTemplate('invoice')) {
   *   // Safe to call render('invoice', ...)
   * }
   *
   * if (!templateService.hasTemplate('unknown')) {
   *   // Return 404 error
   * }
   * ```
   */
  hasTemplate(reportType: string): boolean {
    return reportType in TEMPLATE_FILES;
  }

  /**
   * Clears all cached templates and CSS.
   *
   * Useful for:
   * - Development: Force reload of templates after changes
   * - Testing: Reset state between test cases
   * - Memory management: Release cached content if needed
   *
   * Note: This does NOT unregister Handlebars partials or helpers.
   * Partials will be re-registered on the next render() call.
   *
   * @example
   * ```typescript
   * // Force template reload in development
   * templateService.clearCache();
   * const html = await templateService.render('invoice', data);
   * ```
   */
  clearCache(): void {
    const templateCount = this.templateCache.size;
    this.templateCache.clear();
    this.cssContent = null;
    this.partialsRegistered = false;

    logger.info(
      { clearedTemplates: templateCount },
      'Template cache cleared'
    );
  }
}

// =============================================================================
// SINGLETON INSTANCE
// =============================================================================

/**
 * Singleton instance of the TemplateService.
 *
 * Use this pre-configured instance throughout the application for
 * consistent template caching and helper registration.
 *
 * @example
 * ```typescript
 * import { templateService } from './services/template.service.js';
 *
 * // Render invoice HTML
 * const html = await templateService.render('invoice', invoiceData);
 *
 * // Check template availability
 * const exists = templateService.hasTemplate('quote');
 *
 * // Clear cache (development only)
 * templateService.clearCache();
 * ```
 */
export const templateService = new TemplateService();
