# Blitzy Branding Implementation

## Overview

This document provides comprehensive documentation for the Blitzy visual identity integration into the Odoo 19.0 web client. The implementation replaces the default Odoo branding with the Blitzy brand identity across all user-facing web client touchpoints while maintaining full backward compatibility and preserving all existing Odoo functionality.

### Implementation Philosophy

- **Minimal Change Approach**: Only the changes absolutely necessary for Blitzy branding have been implemented
- **Override-Only Strategy**: SCSS variable overrides are used rather than structural modifications
- **Backward Compatibility**: All existing Odoo modules continue to function without modification
- **LGPL Compliance**: Odoo attribution is preserved in the footer per license requirements

---

## Brand Colors Reference

### Primary Colors

| Token | HEX Value | RGB | Usage |
|-------|-----------|-----|-------|
| `--blitzy-primary` | `#5B39F3` | `rgb(91, 57, 243)` | Primary brand color, buttons, links, main UI accents |
| `--blitzy-primary-dark` | `#4101DB` | `rgb(65, 1, 219)` | Gradient endpoints, hover states, darker accents |
| `--blitzy-primary-light` | `#7A6DEC` | `rgb(122, 109, 236)` | Gradient start points, lighter accents, highlights |

### Accent Colors

| Token | HEX Value | RGB | Usage |
|-------|-----------|-----|-------|
| `--blitzy-accent-mint` | `#94FAD5` | `rgb(148, 250, 213)` | Button text, success indicators, secondary accents |
| `--blitzy-accent-green` | `#07FF97` | `rgb(7, 255, 151)` | Gradient accent, active indicators, highlights |

### Background Colors

| Token | HEX Value | RGB | Usage |
|-------|-----------|-----|-------|
| `--blitzy-bg-dark` | `#130342` | `rgb(19, 3, 66)` | Dark mode backgrounds, login page gradient end |
| `--blitzy-bg-darker` | `#240086` | `rgb(36, 0, 134)` | Deep backgrounds, overlays, login page gradient start |
| `--blitzy-bg-light` | `#F4EFF6` | `rgb(244, 239, 246)` | Light mode backgrounds, webclient background |

### Text & Border Colors

| Token | HEX/RGBA Value | Usage |
|-------|----------------|-------|
| `--blitzy-text-muted` | `#5F5B76` | Secondary text, muted content, labels |
| `--blitzy-border` | `rgba(200, 191, 255, 0.45)` | Borders, dividers, subtle separations |

### Color Mapping from Odoo Defaults

| Odoo Variable | Original Value | Blitzy Replacement |
|---------------|----------------|-------------------|
| `$o-community-color` | `#71639e` | `#5B39F3` |
| `$o-brand-primary` | `#71639e` | `#5B39F3` |
| `$o-brand-secondary` | `#8f8f8f` | `#94FAD5` |
| `$o-webclient-background-color` | `#F7F8F7` | `#F4EFF6` |

---

## Gradient Specifications

### Primary Brand Gradient

**Usage**: Primary CTAs, navbar background, headers

```scss
$blitzy-gradient-primary: linear-gradient(61deg, #7A6DEC 14%, #5B39F3 63.32%, #4101DB 86%);
```

**CSS**:
```css
background: linear-gradient(61deg, #7A6DEC 14%, #5B39F3 63.32%, #4101DB 86%);
```

### Accent Gradient

**Usage**: Highlights, secondary elements, decorative accents

```scss
$blitzy-gradient-accent: linear-gradient(271deg, #5B39F3 -11.94%, #94FAD5 70%, #07FF97);
```

**CSS**:
```css
background: linear-gradient(271deg, #5B39F3 -11.94%, #94FAD5 70%, #07FF97);
```

### Background Gradient

**Usage**: Dark sections, login page background

```scss
$blitzy-gradient-bg: linear-gradient(180deg, #240086, #130342);
```

**CSS**:
```css
background: linear-gradient(180deg, #240086, #130342);
```

### Vertical Gradient

**Usage**: Vertical surfaces, sidebars, panels

```scss
$blitzy-gradient-vertical: linear-gradient(180deg, #561AD6, #240086);
```

**CSS**:
```css
background: linear-gradient(180deg, #561AD6, #240086);
```

---

## Typography

### Font Family

**Primary Font**: Inter (Google Fonts)

```scss
$blitzy-font-family: 'Inter', ui-sans-serif, system-ui, sans-serif, 
    'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji';
```

### Font Weights

| Weight | Value | Usage |
|--------|-------|-------|
| Regular | `400` | Body text, default content |
| Medium | `500` | Labels, emphasized text |
| Semi-Bold | `600` | Subheadings, buttons |
| Bold | `700` | Headings, important labels |

### Google Fonts Import

**HTML Link Tag** (added to template):
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&amp;display=swap" 
      rel="stylesheet"/>
```

**SCSS Import** (alternative):
```scss
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
```

---

## Effect Specifications

### Button Glow Effect

**Usage**: Primary buttons, CTAs with emphasis

```scss
$blitzy-button-glow: 0 0 32px 0 rgba(91, 57, 243, 0.8);
```

**CSS**:
```css
box-shadow: 0 0 32px 0 rgba(91, 57, 243, 0.8);
```

### Text Glow Effect

**Usage**: Highlighted text, hover states on important labels

```scss
$blitzy-text-glow: 0 0 8px #5B39F3, 0 0 16px #5B39F3;
```

**CSS**:
```css
text-shadow: 0 0 8px #5B39F3, 0 0 16px #5B39F3;
```

### Element Glow Effect

**Usage**: Featured elements, active states, special highlighting

```scss
$blitzy-element-glow: 0 0 8px 0 rgba(255, 255, 255, 0.5), 
                      0 0 40px 0 #C5B7FF, 
                      0 0 80px 0 #5B39F3;
```

**CSS**:
```css
box-shadow: 0 0 8px 0 rgba(255, 255, 255, 0.5), 
            0 0 40px 0 #C5B7FF, 
            0 0 80px 0 #5B39F3;
```

### Shadow Effect

**Usage**: Card elevations, modal shadows, floating elements

```scss
$blitzy-shadow: 0 36px 100px 0 rgba(36, 0, 134, 0.5);
```

**CSS**:
```css
box-shadow: 0 36px 100px 0 rgba(36, 0, 134, 0.5);
```

---

## Modified Files

### SCSS Variable Files

| File Path | Operation | Description |
|-----------|-----------|-------------|
| `addons/web/static/src/scss/_blitzy_variables.scss` | **CREATE** | Central definition file containing all Blitzy brand tokens, gradients, typography, and effect specifications. This file serves as the single source of truth for all Blitzy visual properties. |
| `addons/web/static/src/scss/primary_variables.scss` | **UPDATE** | Overridden `$o-community-color` from `#71639e` to `#5B39F3`, updated `$o-brand-secondary`, and configured font family variable to use Inter. |
| `addons/web/static/src/scss/secondary_variables.scss` | **UPDATE** | Overridden `$o-webclient-background-color` to `#F4EFF6` and configured button styling overrides in `$o-btns-bs-override` map with Blitzy-specific button configurations including glow effects. |

### Component SCSS Files

| File Path | Operation | Description |
|-----------|-----------|-------------|
| `addons/web/static/src/webclient/navbar/navbar.variables.scss` | **UPDATE** | Replaced solid `$o-navbar-background` color with Blitzy gradient: `linear-gradient(61deg, #7A6DEC 14%, #5B39F3 63.32%, #4101DB 86%)`. |
| `addons/web/static/src/webclient/navbar/navbar.scss` | **UPDATE** | Added navbar text color overrides and hover state styling to ensure proper contrast with gradient background. |

### Template Files

| File Path | Operation | Description |
|-----------|-----------|-------------|
| `addons/web/views/webclient_templates.xml` | **UPDATE** | Updated logo image paths to reference Blitzy logo files, added Google Fonts Inter import link in head template, and updated footer brand attribution to "Powered by Blitzy \| Based on Odoo" for LGPL compliance. |

### Configuration Files

| File Path | Operation | Description |
|-----------|-----------|-------------|
| `addons/web/__manifest__.py` | **UPDATE** | Added `web/static/src/scss/_blitzy_variables.scss` to the `web._assets_primary_variables` bundle to ensure Blitzy brand tokens are compiled into the CSS output and loaded before other variable definitions. |

### Static Image Assets

| File Path | Operation | Description |
|-----------|-----------|-------------|
| `addons/web/static/img/blitzy-logo.svg` | **CREATE** | Primary Blitzy logo (200x50px, transparent background) for general use in navigation and branded areas. |
| `addons/web/static/img/blitzy-logo-white.svg` | **CREATE** | White variant Blitzy logo (200x50px, transparent background) for dark gradient backgrounds such as login page and navbar. |
| `addons/web/static/img/blitzy-logo-dark.svg` | **CREATE** | Dark variant Blitzy logo (200x50px, transparent background) for light backgrounds. |
| `addons/web/static/img/favicon.ico` | **UPDATE** | Replaced with Blitzy multi-size favicon containing 16x16, 32x32, and 48x48 pixel variants in ICO format with transparent background. |
| `addons/web/static/img/favicon.png` | **CREATE** | Blitzy favicon in PNG format (32x32) for modern browser support. |
| `addons/web/static/img/blitzy-icon-192.png` | **CREATE** | PWA manifest icon (192x192) for Progressive Web App support. |
| `addons/web/static/img/blitzy-icon-512.png` | **CREATE** | PWA manifest icon (512x512) for Progressive Web App support. |

---

## Screenshots Gallery

The following screenshots document the Blitzy-branded Odoo web client UI. All desktop screenshots are captured at 1920x1080 resolution. Mobile screenshots are captured at 375x812 resolution.

### Screenshot Directory

All screenshots are located in: `docs/branding/screenshots/`

### Screenshot Index

| # | Filename | Resolution | Description |
|---|----------|------------|-------------|
| 1 | `01-login-page.png` | 1920x1080 | Login/authentication screen displaying Blitzy gradient background (`#240086` → `#130342`), white Blitzy logo, and styled login form with branded primary buttons. |
| 2 | `02-dashboard.png` | 1920x1080 | Main dashboard after successful login showing the Blitzy-branded navigation header with gradient background, favicon visible in browser tab. |
| 3 | `03-app-menu.png` | 1920x1080 | Application menu/launcher expanded showing Blitzy header styling and branded module icons with proper color contrast. |
| 4 | `04-list-view.png` | 1920x1080 | Standard list view demonstrating branded header, action buttons with `#5B39F3` primary color, and properly styled list elements. |
| 5 | `05-form-view.png` | 1920x1080 | Form view showing branded primary buttons with glow effect, Inter font typography, and consistent color application across form elements. |
| 6 | `06-kanban-view.png` | 1920x1080 | Kanban board view demonstrating Blitzy brand colors applied to cards, column headers, and interactive elements. |
| 7 | `07-settings.png` | 1920x1080 | Settings page with branded sidebar navigation and proper application of Blitzy colors to configuration panels. |
| 8 | `08-user-menu.png` | 1920x1080 | User profile dropdown menu expanded, showing profile options and logout button with proper Blitzy styling. |
| 9 | `09-search-panel.png` | 1920x1080 | Search/filter panel opened showing branded search controls, filter chips, and properly styled input elements. |
| 10 | `10-mobile-responsive.png` | 375x812 | Mobile viewport demonstrating responsive Blitzy header, hamburger menu, and proper brand styling at mobile breakpoints. |

### Screenshot Capture Requirements

- **Browser Settings**: 100% zoom, no extensions visible
- **Cache**: Clear browser cache before capturing to ensure fresh assets load
- **Test Data**: Use consistent test data across all screenshots
- **Browser Tab**: Include browser tab showing Blitzy favicon
- **Modes**: Capture default light mode (dark mode variants if applicable)

---

## Validation Checklist

### Visual Validation

- [ ] Login page displays Blitzy gradient background (`#240086` → `#130342`)
- [ ] Login page shows Blitzy logo (white variant for dark background)
- [ ] Primary buttons use `#5B39F3` background with `#94FAD5` text
- [ ] Primary buttons display glow effect on hover
- [ ] Navigation header displays gradient background (`61deg, #7A6DEC → #5B39F3 → #4101DB`)
- [ ] Navigation header text has proper contrast against gradient
- [ ] Favicon displays Blitzy icon in browser tab
- [ ] Inter font family loads and applies to all UI text
- [ ] Footer shows "Powered by Blitzy | Based on Odoo"
- [ ] Webclient background color is `#F4EFF6`
- [ ] All links use Blitzy primary color (`#5B39F3`)

### Functional Validation

- [ ] All existing Odoo modules load without errors
- [ ] User authentication works unchanged
- [ ] All menu navigation functions correctly
- [ ] Form submissions work unchanged
- [ ] Report generation works unchanged
- [ ] Mobile responsive breakpoints preserved
- [ ] Keyboard navigation remains functional
- [ ] All tooltips and popovers display correctly
- [ ] Modal dialogs render properly
- [ ] Date pickers and dropdowns function correctly

### Build Validation

- [ ] SCSS compiles without errors
- [ ] No JavaScript console errors introduced
- [ ] Asset bundling completes successfully
- [ ] Page load time within 10% of baseline
- [ ] All static assets load correctly (logos, favicon, fonts)
- [ ] CSS specificity doesn't cause override conflicts
- [ ] No SCSS deprecation warnings

### Browser Compatibility

- [ ] Chrome (latest) - Desktop and Mobile
- [ ] Firefox (latest)
- [ ] Safari (latest) - Desktop and Mobile
- [ ] Edge (latest)

### Accessibility Validation

- [ ] Color contrast ratios meet WCAG 2.1 AA standards
- [ ] Focus states are visible and properly styled
- [ ] Button labels remain readable
- [ ] Form inputs maintain proper labeling

---

## Footer Attribution

### LGPL License Compliance

Per the LGPL license requirements of Odoo, the footer attribution has been updated to maintain proper attribution while incorporating Blitzy branding:

**Updated Footer Text**:
```
Powered by Blitzy | Based on Odoo
```

This attribution:
- Preserves required Odoo attribution per LGPL terms
- Establishes Blitzy as the primary brand
- Maintains transparency about the underlying platform

### Location

The footer attribution appears in `addons/web/views/webclient_templates.xml` within the `brand_promotion` template block.

---

## Technical Implementation Notes

### SCSS Variable Override Pattern

The implementation uses the SCSS `!default` pattern to override Odoo variables:

```scss
// In _blitzy_variables.scss (loaded first)
$blitzy-primary: #5B39F3;

// In primary_variables.scss
$o-community-color: $blitzy-primary !default;
```

This ensures Blitzy values take precedence when loaded before the default Odoo values in the asset bundle.

### Asset Bundle Load Order

The modified `__manifest__.py` ensures proper variable cascade:

1. `_blitzy_variables.scss` (Blitzy tokens - loaded first)
2. `primary_variables.scss` (Core brand colors)
3. `secondary_variables.scss` (Derived colors)
4. `pre_variables.scss` (Bootstrap defaults)
5. `bootstrap_overridden.scss` (Bootstrap mappings)

### Variable Propagation Chain

```
_blitzy_variables.scss (defines tokens)
        ↓
primary_variables.scss (uses tokens for $o-brand-*)
        ↓
bootstrap_overridden.scss (maps to Bootstrap $primary, $secondary)
        ↓
All component SCSS files (inherit Bootstrap/Odoo variables)
        ↓
Compiled CSS Bundle (served to browser)
```

### Performance Considerations

- Google Fonts import uses `display=swap` to prevent render blocking
- No additional JavaScript introduced
- SCSS compilation produces optimized CSS output
- Asset bundling and minification handled by existing Odoo pipeline
- Font preconnect can be added for improved loading performance

---

## Changelog

### Version 1.0.0 (Initial Implementation)

**Date**: December 2024

**Summary**: Complete Blitzy visual identity integration into Odoo 19.0 web client.

**Changes**:
- Created `_blitzy_variables.scss` with all brand tokens
- Updated `primary_variables.scss` with Blitzy primary colors
- Updated `secondary_variables.scss` with background and button overrides
- Updated `navbar.variables.scss` with gradient background
- Updated `navbar.scss` with text color adjustments
- Updated `webclient_templates.xml` with logo paths, font import, and footer text
- Updated `__manifest__.py` with new SCSS file in asset bundle
- Added Blitzy logo variants (standard, white, dark)
- Replaced favicon with Blitzy brand icon
- Created this documentation

**Breaking Changes**: None

**Compatibility**: Full backward compatibility with all existing Odoo modules

---

## Contact & Support

For questions about this branding implementation or to report issues, please contact the Blitzy development team.

---

*This documentation was created as part of the Blitzy Branding Implementation project for Odoo 19.0 web client.*
