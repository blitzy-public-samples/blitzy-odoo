/**
 * Vitest Configuration for Document Sidecar Service
 *
 * This configuration file sets up the Vitest test runner for the TypeScript
 * sidecar service. It configures:
 * - Test environment and globals
 * - Coverage reporting via @vitest/coverage-v8
 * - Module resolution aliases
 * - Timeout settings for PDF generation tests
 * - File patterns for unit and integration tests
 *
 * @see https://vitest.dev/config/
 */

import { defineConfig } from 'vitest/config';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

// ES module workaround for __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export default defineConfig({
  /**
   * Test configuration options
   */
  test: {
    /**
     * Enable global test APIs (describe, it, expect, etc.)
     * This allows using Vitest globals without explicit imports
     */
    globals: true,

    /**
     * Use Node.js environment for testing
     * Required for Puppeteer, file system access, and Node.js APIs
     */
    environment: 'node',

    /**
     * Test file patterns to include
     * Matches all .test.ts files in tests/unit/ and tests/integration/
     */
    include: ['tests/**/*.test.ts'],

    /**
     * Paths to exclude from test discovery
     */
    exclude: ['node_modules', 'dist'],

    /**
     * Root directory for test resolution
     */
    root: __dirname,

    /**
     * Code coverage configuration using V8 coverage provider
     */
    coverage: {
      /**
       * Use V8's built-in coverage (faster than Istanbul)
       */
      provider: 'v8',

      /**
       * Coverage report formats:
       * - text: Console output for CI/local viewing
       * - json: Machine-readable format for tooling
       * - html: Interactive HTML report for detailed analysis
       */
      reporter: ['text', 'json', 'html'],

      /**
       * Source files to include in coverage analysis
       */
      include: ['src/**/*.ts'],

      /**
       * Exclude from coverage:
       * - Templates directory (Handlebars .hbs files)
       * - TypeScript declaration files
       * - Test fixtures
       */
      exclude: [
        'src/templates/**',
        'src/**/*.d.ts',
        'tests/fixtures/**',
      ],

      /**
       * Coverage thresholds (optional, can be enforced in CI)
       * Commented out for initial development, enable as coverage improves
       */
      // thresholds: {
      //   statements: 80,
      //   branches: 80,
      //   functions: 80,
      //   lines: 80,
      // },

      /**
       * Directory for coverage reports
       */
      reportsDirectory: './coverage',

      /**
       * Clean coverage results before running tests
       */
      clean: true,
    },

    /**
     * Test timeout in milliseconds (30 seconds)
     * Extended timeout for PDF generation tests which involve:
     * - Puppeteer browser operations
     * - Page rendering and PDF creation
     * - Template compilation
     */
    testTimeout: 30000,

    /**
     * Hook timeout in milliseconds (30 seconds)
     * Extended timeout for beforeAll/afterAll hooks that may:
     * - Initialize/shutdown Puppeteer browser instances
     * - Set up/tear down test fixtures
     * - Start/stop test servers
     */
    hookTimeout: 30000,

    /**
     * Setup files to run before each test file
     * Can be used for global test utilities, mocks, or environment setup
     */
    setupFiles: [],

    /**
     * Retry failed tests (useful for flaky integration tests)
     * Set to 0 for strict test validation
     */
    retry: 0,

    /**
     * Reporter configuration for test output
     */
    reporters: ['default'],

    /**
     * Pool configuration for test isolation
     * Using 'forks' for better isolation with Puppeteer
     */
    pool: 'forks',

    /**
     * Pool options for controlling parallelism
     */
    poolOptions: {
      forks: {
        /**
         * Single fork for integration tests to avoid Puppeteer conflicts
         * Increase for unit tests only if needed
         */
        singleFork: false,
      },
    },

    /**
     * Watch mode exclusions
     * Prevents test re-runs when these files change
     */
    watchExclude: [
      'node_modules/**',
      'dist/**',
      'coverage/**',
      '**/*.hbs',
      '**/*.css',
    ],

    /**
     * Deps configuration for handling external dependencies
     */
    deps: {
      /**
       * Inline certain modules that may have issues with ESM
       */
      inline: [],
    },

    /**
     * Sequence configuration for test ordering
     */
    sequence: {
      /**
       * Shuffle tests for better isolation detection
       * Set to false for deterministic ordering
       */
      shuffle: false,
    },
  },

  /**
   * Module resolution configuration
   */
  resolve: {
    /**
     * Path aliases for cleaner imports in tests
     * Maps '@' to './src' directory for imports like:
     * import { config } from '@/config';
     */
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },

  /**
   * ESBuild configuration for TypeScript transformation
   */
  esbuild: {
    /**
     * Target ES2022 for modern Node.js 20 features
     */
    target: 'es2022',
  },
});
