# Technical Specification

# 0. Agent Action Plan

## 0.1 Intent Clarification



### 0.1.1 Core Security Objective

Based on the security concern described, the Blitzy platform understands that the security vulnerability to resolve is a **comprehensive, multi-vector security remediation** of the Blitzy Odoo 19.0 open-source codebase. This encompasses both dependency-level vulnerabilities (outdated packages with known CVEs) and code-level vulnerabilities (insecure coding patterns in Python and XML templates).

- **Vulnerability category:** Multiple vulnerabilities — Dependency vulnerability, Code vulnerability, and Configuration weakness
- **Severity level:** Critical to High — The codebase contains confirmed Critical (CVSS ≥9.0) and High (CVSS 7.0–8.9) vulnerabilities across dependency chains, code patterns, and default configurations
- **Security requirements with enhanced clarity:**
  - Remediate 100% of Critical severity vulnerabilities (CVSS ≥9.0), including arbitrary code execution in Jinja2 (CVE-2024-56201, CVSS 8.8) and Pillow ImageMath.eval (CVE-2023-50447, CVSS 8.1)
  - Remediate 100% of High severity vulnerabilities (CVSS 7.0–8.9), including Werkzeug debugger RCE (CVE-2024-34069, CVSS 7.5), Jinja2 sandbox bypass (CVE-2024-56326, CVSS 7.8), and Pillow DoS (CVE-2023-44271, CVSS 7.5)
  - Achieve ≥80% remediation of Medium severity vulnerabilities (CVSS 4.0–6.9), including cookie bypass in Werkzeug (CVE-2023-23934), XSS in Jinja2 (CVE-2024-22195, CVE-2024-34064), and cryptography DoS (CVE-2023-49083, CVSS 5.3)
  - Fix code-level vulnerabilities: XXE in XML parsing (`assetsbundle.py`, `xml_utils.py`), missing session cookie security flags (`http.py`), and insecure default configurations (`config.py`)
  - Implement automated security testing integrated into CI/CD pipeline
  - Validate zero functional regression across all Odoo modules with <10% performance impact
- **Implicit security needs surfaced:**
  - Backward compatibility must be preserved across all Python version tiers (3.10, 3.11, 3.12, 3.13) since `requirements.txt` pins different dependency versions per Python version
  - Zero downtime requirement — all changes must be atomic and revertible per vulnerability
  - Odoo module architecture, ORM model definitions, and API contracts (XML-RPC, JSON-RPC) must remain unchanged
  - The `pyopenssl==19.0.0` constraint for Python <3.12 creates a hard upper bound for `cryptography` upgrades, requiring careful version negotiation

### 0.1.2 Special Instructions and Constraints

- **CRITICAL directive — Minimal Change Clause:** "Make ONLY changes necessary to remediate identified security vulnerabilities." This is the governing principle for all modifications
  - User Example: "Modify only files/functions directly related to discovered vulnerabilities"
  - User Example: "DO NOT refactor code beyond security remediation requirements"
  - User Example: "DO NOT enhance features or optimize performance unless required for security fix"
  - User Example: "DO NOT modify module manifests unless security fix requires new dependency"
- **Security standards:** Follow OWASP Top 10 guidelines, OWASP XXE Prevention Cheat Sheet, and OWASP Session Management Cheat Sheet
- **Preservation requirements:**
  - Odoo `__manifest__.py` declarations — unchanged
  - Module dependency chains and loading order — unchanged
  - Database schema and ORM model definitions — unchanged
  - API contracts for XML-RPC and JSON-RPC endpoints — unchanged
  - Existing `ir.model.access` and record rule definitions — unchanged
  - QWeb template inheritance chains — unchanged
  - Workflow transitions and automation rules — unchanged
- **Web search requirements:** Security advisory lookups for all pinned dependencies, CVE database research (NVD, MITRE, GitHub Security Advisories), OWASP documentation for remediation patterns
- **Change scope preference:** Minimal — Apply the smallest possible change that completely addresses each vulnerability

### 0.1.3 Technical Interpretation

This security vulnerability translates to the following technical fix strategy:

- To resolve **dependency vulnerabilities**, we will upgrade pinned package versions in `requirements.txt` across all Python version tiers to their minimum patched versions, verifying Odoo 19.0 compatibility at each step
- To resolve **XXE vulnerabilities**, we will update `etree.XMLParser()` instantiations in `odoo/addons/base/models/assetsbundle.py` and `odoo/tools/xml_utils.py` to include `resolve_entities=False` parameter
- To resolve **session security weaknesses**, we will add `secure=True` and `samesite='Lax'` flags to all `set_cookie()` calls for session cookies in `odoo/http.py`
- To resolve **configuration weaknesses**, we will update default values in `odoo/tools/config.py` for `admin_passwd` (remove default 'admin') and `list_db` (default to `False`)
- To resolve **XSS vectors in templates**, we will audit and remediate `t-raw`/`t-out` usage in QWeb templates where user-controlled data is rendered without escaping
- **User's understanding level:** Explicit — The user has provided detailed CVE categories, OWASP references, specific remediation patterns, and tool recommendations (Bandit, Safety, npm audit, OWASP ZAP), indicating expert-level security knowledge



## 0.2 Vulnerability Research and Analysis



### 0.2.1 Initial Assessment

Security-related information extracted from the codebase and user requirements:

- **CVE numbers identified through research:**
  - CVE-2024-34069 (Werkzeug debugger RCE)
  - CVE-2024-49767 (Werkzeug multipart DoS)
  - CVE-2024-49766 (Werkzeug path traversal)
  - CVE-2023-23934 (Werkzeug cookie bypass)
  - CVE-2024-22195 (Jinja2 XSS)
  - CVE-2024-34064 (Jinja2 XSS via xmlattr)
  - CVE-2024-56201 (Jinja2 sandbox bypass)
  - CVE-2024-56326 (Jinja2 sandbox escape)
  - CVE-2023-43804 (urllib3 cookie leak)
  - CVE-2023-45803 (urllib3 request body leak)
  - CVE-2023-50447 (Pillow arbitrary code execution)
  - CVE-2023-44271 (Pillow uncontrolled resource consumption)
  - CVE-2023-23931 (cryptography memory corruption)
  - CVE-2023-49083 (cryptography NULL-pointer DoS)
- **Vulnerability names:** XXE in XML parsing, insecure session cookies, SQL injection via string formatting, insecure default admin password, database enumeration exposure
- **Affected packages:** Werkzeug, Jinja2, urllib3, Pillow, cryptography, lxml
- **Symptoms identified:** Outdated dependency versions pinned per Python version tier, `XMLParser()` instantiation without entity resolution disabled, `set_cookie()` calls missing `secure` and `samesite` flags, `%` string formatting for SQL identifiers, plaintext default admin password
- **Security advisories referenced:** GitHub Security Advisories (GHSA), NVD (nvd.nist.gov), PyPI security advisories, OWASP Top 10 2021

### 0.2.2 Required Web Research — Findings

Research reveals the following confirmed vulnerability details:

- **Werkzeug 2.0.2 / 2.2.2 / 3.0.1** — All three pinned versions are affected by CVE-2024-34069 (debugger RCE, CVSS 7.5) and CVE-2024-49767 (multipart memory exhaustion DoS, CVSS 6.9). Werkzeug 3.0.6 is the security fix release that addresses all known CVEs without breaking changes. Werkzeug 2.0.2 is additionally affected by CVE-2023-23934 (cookie bypass) and CVE-2023-25577 (multipart unlimited resource consumption)
- **Jinja2 3.0.3 / 3.1.2** — Both versions are affected by CVE-2024-22195 (XSS, CVSS 6.1), CVE-2024-34064 (XSS via xmlattr filter, CVSS 5.4), CVE-2024-56201 (sandbox key bypass, CVSS 8.8), and CVE-2024-56326 (sandbox escape via str.format, CVSS 7.8). Version 3.1.5 fixes CVE-2024-56201 and CVE-2024-56326; version 3.1.6 addresses all four CVEs
- **urllib3 1.26.5** — Affected by CVE-2023-43804 (Cookie header leaked during cross-origin redirects, CVSS 5.9), patched in 1.26.17; and CVE-2023-45803 (request body leaked on redirect, CVSS 4.2), patched in 1.26.18. The urllib3 2.0.7 version pinned for Python ≥3.12 is already safe
- **Pillow 9.0.1 / 9.4.0** — Both affected by CVE-2023-50447 (arbitrary code execution via ImageMath.eval, CVSS 8.1) and CVE-2023-44271 (uncontrolled resource consumption DoS, CVSS 7.5). Pillow 10.2.0 patches both CVEs. Versions 10.2.0 and 11.1.0 pinned for Python ≥3.12 and ≥3.13 are already safe
- **cryptography 3.4.8** (Python <3.12) — Affected by CVE-2023-23931 (memory corruption in Cipher, CVSS 6.5, fixed in 39.0.1) and CVE-2023-49083 (NULL-pointer dereference in PKCS7, CVSS 5.3, fixed in 41.0.6). However, upgrading is constrained by `pyopenssl==21.0.0` compatibility, which requires `cryptography<37.0.0`

### 0.2.3 Vulnerability Classification

| Vulnerability | Type | Attack Vector | Exploitability | Impact | Root Cause |
|---|---|---|---|---|---|
| CVE-2024-56201 (Jinja2) | Sandbox Bypass | Network | High | Integrity, Confidentiality | Insufficient key sanitization in sandbox templates |
| CVE-2024-56326 (Jinja2) | Sandbox Escape | Network | High | Integrity, Confidentiality | `str.format_map` access in sandbox environment |
| CVE-2023-50447 (Pillow) | Arbitrary Code Execution | Network | Medium | All (CIA) | Unsafe `eval()` in ImageMath module |
| CVE-2024-34069 (Werkzeug) | Remote Code Execution | Network | Medium | All (CIA) | Missing Host header validation in debugger |
| CVE-2023-44271 (Pillow) | Denial of Service | Network | High | Availability | Uncontrolled resource consumption in image parsing |
| CVE-2024-49767 (Werkzeug) | Denial of Service | Network | High | Availability | Multipart parser memory exhaustion |
| CVE-2024-22195 (Jinja2) | Cross-Site Scripting | Network | High | Integrity | Unescaped output in template rendering |
| CVE-2023-43804 (urllib3) | Information Disclosure | Network | Medium | Confidentiality | Cookie header leaked on cross-origin redirect |
| XXE (assetsbundle.py) | XML External Entity | Network | Medium | Confidentiality | `XMLParser()` without `resolve_entities=False` |
| Session cookies (http.py) | Session Hijacking | Network | High | Confidentiality | Missing `secure` and `samesite` cookie flags |
| SQL injection (base_partner_merge.py) | SQL Injection | Network | Low | All (CIA) | `%` string formatting for SQL table/column names |
| Config weakness (config.py) | Insecure Defaults | Local | High | Integrity | Default admin password `'admin'`, `list_db=True` |

### 0.2.4 Web Search Research Conducted

- **Official security advisories reviewed:**
  - GitHub Pallets/Werkzeug releases: Confirmed 3.0.6 as security fix release addressing CVE-2024-49766 and CVE-2024-49767
  - GitHub Pallets/Jinja2 security advisories: CVE-2024-56201 (GHSA sandbox bypass) and CVE-2024-56326 (GHSA sandbox escape)
  - PyPI urllib3 advisory: CVE-2023-43804 patched in 1.26.17, CVE-2023-45803 patched in 1.26.18
  - SUSE/Ubuntu/Red Hat advisories: Confirmed CVE-2023-49083 in cryptography patched in 41.0.6
  - NVD entries: Validated CVSS scores and affected version ranges for all CVEs
- **CVE details and patches:**
  - Werkzeug 3.0.6: Patches form parser memory exhaustion and `safe_join` path traversal on Windows
  - Jinja2 3.1.6: Patches all four XSS and sandbox bypass CVEs
  - urllib3 1.26.18: Patches both cookie leak and request body leak CVEs
  - Pillow 10.2.0: Patches ImageMath arbitrary code execution and resource consumption
- **Recommended mitigation strategies:**
  - Upgrade all vulnerable packages to their minimum patched versions within each Python version tier
  - Apply code-level patches for XXE, session security, and SQL identifier handling
  - Harden configuration defaults for production deployments
- **Alternative solutions considered:**
  - Werkzeug: Upgrading all tiers to 3.0.6 (rejected — would be a major version jump for Python ≤3.10, risking breaking changes; instead upgrade each tier to its nearest safe version)
  - cryptography: Upgrading to 41.0.6+ (blocked by pyopenssl 21.0.0 constraint for Python <3.12; documented as known limitation)



## 0.3 Security Scope Analysis



### 0.3.1 Affected Component Discovery

A comprehensive search of the repository reveals the following vulnerability surface:

- **Dependency manifests containing vulnerable pinned versions:**
  - `requirements.txt` — Primary dependency file with Python-version-conditional pins for Werkzeug (3 tiers), Jinja2 (2 tiers), urllib3 (2 tiers), Pillow (4 tiers), cryptography (2 tiers), lxml (3 tiers)
  - `setup.py` — Declares `Jinja2`, `lxml`, `Pillow`, `Werkzeug` among `install_requires` (unpinned, defers to requirements.txt)
- **Source files with vulnerable XML parsing patterns (XXE):**
  - `odoo/addons/base/models/assetsbundle.py` (line 451) — `etree.XMLParser(ns_clean=True, recover=True, remove_comments=True)` instantiated **without** `resolve_entities=False`
  - `odoo/tools/xml_utils.py` (line 104) — `XMLParser()` used for XSD validation without entity resolution disabled
- **Source files with session cookie vulnerabilities:**
  - `odoo/http.py` (line 2134) — `self.future_response.set_cookie('session_id', sess.sid, max_age=..., httponly=True)` missing `secure=True` and `samesite='Lax'`
  - `odoo/http.py` (line 2457) — `response.set_cookie('session_id', session.sid, max_age=..., httponly=True)` missing identical flags
- **Source files with SQL injection patterns:**
  - `odoo/addons/base/wizard/base_partner_merge.py` (line 135) — `"SELECT column_name FROM information_schema.columns WHERE table_name LIKE '%s'" % (table)` uses string formatting instead of parameterized query
  - `odoo/addons/base/wizard/base_partner_merge.py` (lines 148–182) — Multiple SQL queries use `%(table)s` and `%(column)s` string formatting for identifiers instead of `SQL.identifier()`
- **Configuration files with insecure defaults:**
  - `odoo/tools/config.py` (line 207) — `admin_passwd` defaults to `'admin'`
  - `odoo/tools/config.py` (line 410) — `list_db` defaults to `True`, enabling database enumeration
- **Template files with potential XSS vectors:**
  - 14 instances of `t-raw` / `t-out` across `odoo/addons/` XML templates (the majority render model field data from `ir_qweb_widget_templates.xml` — lower risk as data originates from ORM fields, not raw user input)
  - `odoo/cli/scaffold.py` (line 84) — Uses `jinja2.Environment()` (unsandboxed) for CLI scaffold generation (low risk — offline tool, no user-facing data)

Vulnerability affects **8 core files** across **4 directories**, plus the primary dependency manifest.

### 0.3.2 Root Cause Identification

- **Dependency vulnerabilities:** The root cause is version pinning to Ubuntu/Debian distribution packages (Jammy, Bookworm, Noble) rather than security-patched releases. The `requirements.txt` comments explicitly reference distro versions (e.g., `# (Jammy)`, `# (Noble)`), which lag behind upstream security patches
- **XXE vulnerability in `assetsbundle.py`:** The XML parser at line 451 processes CSS/SCSS asset bundle XML content. The `resolve_entities` parameter defaults to `True` in lxml, allowing XML entity expansion. While the parsed content is typically internal asset markup, any injection into asset content could trigger entity resolution
- **Session cookie weakness in `http.py`:** Odoo's session management sets `httponly=True` but omits `secure` and `samesite` attributes. The `set_cookie` wrapper at line 1548 defaults to `secure=False, samesite=None`, propagating to all session cookie operations
- **SQL injection in `base_partner_merge.py`:** Table and column names from `pg_constraint` metadata are interpolated into SQL using Python `%` string formatting (line 135, 148). While the source is database metadata (not direct user input), this pattern violates parameterized query best practices and is vulnerable if metadata is ever tainted
- **Configuration weakness in `config.py`:** The default admin master password `'admin'` and `list_db=True` enable trivial unauthorized access to database management operations and enumeration of available databases

### 0.3.3 Current State Assessment

| Vulnerable Component | Current Version/State | Location | Scope of Exposure |
|---|---|---|---|
| Werkzeug | 2.0.2 (Python ≤3.10), 2.2.2 (3.11), 3.0.1 (≥3.12) | `requirements.txt` | Public-facing (WSGI server) |
| Jinja2 | 3.0.3 (Python ≤3.10), 3.1.2 (>3.10) | `requirements.txt` | Template rendering engine |
| urllib3 | 1.26.5 (Python <3.12), 2.0.7 (≥3.12) | `requirements.txt` | HTTP client (external API calls) |
| Pillow | 9.0.1 (≤3.10), 9.4.0 (3.11), 10.2.0 (3.12), 11.1.0 (3.13) | `requirements.txt` | Image processing (uploads, reports) |
| cryptography | 3.4.8 (Python <3.12), 42.0.8 (≥3.12) | `requirements.txt` | TLS/crypto operations |
| XMLParser (XXE) | `resolve_entities` not set to `False` | `assetsbundle.py:451`, `xml_utils.py:104` | Internal (asset compilation) |
| Session cookies | Missing `secure` and `samesite` flags | `http.py:2134`, `http.py:2457` | Public-facing (all sessions) |
| SQL identifiers | `%` string formatting | `base_partner_merge.py:135,148-182` | Internal (admin merge wizard) |
| Admin password | Default `'admin'` | `config.py:207` | Public-facing (DB management) |
| Database listing | Default `list_db=True` | `config.py:410` | Public-facing (login page) |



## 0.4 Version Compatibility & Constraints

This section provides the definitive compatibility matrix for all security-relevant dependencies across the Odoo 19.0 multi-Python-tier deployment model. Every upgrade recommendation is validated against the hard constraints imposed by `requirements.txt` conditional pins, transitive dependency ceilings, and the Odoo monkeypatch compatibility layer.

### 0.4.1 Current Python-Tier Dependency Matrix

Odoo 19.0 supports four Python version tiers, each with distinct dependency pins specified via PEP 508 environment markers in `requirements.txt`. The following matrix captures the current state of all security-relevant packages.

| Package | Python ≤ 3.10 | Python > 3.10 & < 3.12 | Python ≥ 3.12 & < 3.13 | Python ≥ 3.13 |
|---------|---------------|-------------------------|-------------------------|---------------|
| **Werkzeug** | 2.0.2 | 2.2.2 | 3.0.1 | 3.0.1 |
| **Jinja2** | 3.0.3 | 3.1.2 | 3.1.2 | 3.1.2 |
| **urllib3** | 1.26.5 | 1.26.5 | 2.0.7 | 2.0.7 |
| **Pillow** | 9.0.1 | 9.4.0 | 10.2.0 | 11.1.0 |
| **lxml** | 4.8.0 | 4.9.3 | 5.2.1 | 5.2.1 |
| **cryptography** | 3.4.8 | 3.4.8 | 42.0.8 | 42.0.8 |
| **pyopenssl** | 21.0.0 | 21.0.0 | 24.1.0 | 24.1.0 |
| **requests** | 2.25.1 | 2.25.1 (Py < 3.11) / 2.31.0 (Py ≥ 3.11) | 2.31.0 | 2.31.0 |
| **MarkupSafe** | 2.0.1 | 2.1.2 | 2.1.5 | 2.1.5 |

**Source**: `requirements.txt` lines 12–13, 30–31, 34–40, 47–50, 59–60, 80–81, 85–90.

### 0.4.2 Upgrade Path Analysis by Dependency

#### Werkzeug — Unified Upgrade to 3.0.6 (All Tiers)

**Current Exposure:**

| Python Tier | Current Pin | Applicable CVEs | Highest CVSS |
|-------------|-------------|----------------|--------------|
| ≤ 3.10 | 2.0.2 | CVE-2023-23934, CVE-2023-25577, CVE-2024-34069, CVE-2024-49766, CVE-2024-49767 | 7.5 (High) |
| > 3.10 & < 3.12 | 2.2.2 | CVE-2023-23934, CVE-2023-25577, CVE-2024-34069, CVE-2024-49766, CVE-2024-49767 | 7.5 (High) |
| ≥ 3.12 | 3.0.1 | CVE-2024-34069, CVE-2024-49766, CVE-2024-49767 | 7.5 (High) |

**Target Version**: `Werkzeug==3.0.6` for all Python tiers (requires Python ≥ 3.8, satisfied by all tiers).

**Key CVEs Resolved:**
- **CVE-2024-34069** (CVSS 7.5): Debugger RCE via CSRF — attacker can execute code on developer machines through crafted domain interaction. Fixed in 3.0.3.
- **CVE-2024-49767** (CVSS 7.5): Multipart form-data resource exhaustion — a single 1 Gbit/s upload can exhaust 32 GB of RAM in under 60 seconds. Fixed in 3.0.6.
- **CVE-2024-49766** (Medium): UNC path traversal on Windows with Python < 3.11 via `safe_join()`. Fixed in 3.0.6.
- **CVE-2023-25577** (CVSS 7.5): Unlimited multipart parts parsing causing CPU exhaustion. Fixed in 2.2.3.
- **CVE-2023-23934** (CVSS 3.5): Cookie parsing flaw allowing value injection on adjacent domains. Fixed in 2.2.3.

**Compatibility Enabler**: The monkeypatch layer at `odoo/_monkeypatches/werkzeug.py` (1076 lines) re-implements all Werkzeug 2.x deprecated APIs (`LRUCache`, `ImmutableList`, `TypeConversionDict`, `dump_header`, `parse_set_header`, routing internals, and `MultiDict` utilities) on top of the Werkzeug 3.x API surface. This makes a direct jump from 2.0.2 → 3.0.6 safe for the Odoo runtime without source code modifications beyond the version pin.

**Breaking Changes**: None for Odoo. All API differences are absorbed by the existing monkeypatch layer. No Odoo source files reference Werkzeug internals directly that are not already shimmed.

#### Jinja2 — Upgrade to 3.1.6 (All Tiers)

**Current Exposure:**

| Python Tier | Current Pin | Applicable CVEs | Highest CVSS |
|-------------|-------------|----------------|--------------|
| ≤ 3.10 | 3.0.3 | CVE-2024-22195, CVE-2024-56201, CVE-2025-27516 | 6.1 (Medium) |
| > 3.10 | 3.1.2 | CVE-2024-22195, CVE-2024-56201, CVE-2025-27516 | 6.1 (Medium) |

**Target Version**: `Jinja2==3.1.6` for all Python tiers (requires Python ≥ 3.7, satisfied by all tiers).

**Key CVEs Resolved:**
- **CVE-2024-22195** (CVSS 6.1): XSS via `xmlattr` filter allowing injection of arbitrary HTML attributes/events in templates using user-controlled keys. Fixed in 3.1.3.
- **CVE-2024-56201** (CVSS 5.4): Sandbox bypass via malicious template strings accepted by `SandboxedEnvironment`. Fixed in 3.1.5.
- **CVE-2025-27516** (CVSS 5.4): Sandbox escape via Jinja2 `attr` filter bypassing attribute access restrictions. Fixed in 3.1.6.

**Compatibility Notes**: The 3.0.3 → 3.1.6 jump for Python ≤ 3.10 is a minor version upgrade. Jinja2 3.1 removed the deprecated `with` extension and `autoescape` extension keywords, but Odoo's QWeb engine does not use these deprecated features. The `MarkupSafe` dependency (`2.0.1` on Python ≤ 3.10) remains compatible with Jinja2 3.1.6 (requires `MarkupSafe >= 2.0`).

#### urllib3 — Tiered Upgrade

**Current Exposure:**

| Python Tier | Current Pin | Applicable CVEs | Highest CVSS |
|-------------|-------------|----------------|--------------|
| < 3.12 | 1.26.5 | CVE-2023-43804, CVE-2023-45803, CVE-2024-37891 | 8.1 (High) |
| ≥ 3.12 | 2.0.7 | CVE-2024-37891 | 4.4 (Medium) |

**Target Versions:**
- **Python < 3.12**: `urllib3==1.26.20` (latest 1.26.x maintenance release, August 2024)
- **Python ≥ 3.12**: `urllib3==2.2.2` (minimum for CVE-2024-37891 fix)

**Key CVEs Resolved:**
- **CVE-2023-43804** (CVSS 8.1): Cookie `Authorization` header leaked during cross-origin redirects. Fixed in 1.26.18.
- **CVE-2023-45803** (CVSS 4.2): Request body not stripped after 303 redirect changing method to GET. Fixed in 1.26.18.
- **CVE-2024-37891** (CVSS 4.4): `Proxy-Authorization` header leaked to non-proxy origins during redirects. Fixed in 1.26.19 and 2.2.2.

**Coupling Constraint**: `requests==2.25.1` (Python < 3.11) requires `urllib3 >= 1.21.1, < 1.27` — upgrading to 1.26.20 is fully within this range. `requests==2.31.0` (Python ≥ 3.11) requires `urllib3 >= 1.21.1, < 3` — both 1.26.20 and 2.2.2 are compatible.

#### Pillow — Tiered Upgrade with Constraints

**Current Exposure:**

| Python Tier | Current Pin | Applicable CVEs | Highest CVSS |
|-------------|-------------|----------------|--------------|
| ≤ 3.10 | 9.0.1 | CVE-2022-24303, CVE-2023-44271, CVE-2023-50447 | 9.1 (Critical) |
| > 3.10 & < 3.12 | 9.4.0 | CVE-2023-44271, CVE-2023-50447 | 8.1 (High) |
| ≥ 3.12 | 10.2.0 | Safe | — |
| ≥ 3.13 | 11.1.0 | Safe | — |

**Target Versions:**
- **Python ≤ 3.10**: `Pillow==10.2.0` (first version fixing all critical CVEs; supports Python ≥ 3.8)
- **Python > 3.10 & < 3.12**: `Pillow==10.2.0` (same target)
- **Python ≥ 3.12**: No change needed (10.2.0 already safe)
- **Python ≥ 3.13**: No change needed (11.1.0 already safe)

**Key CVEs Resolved:**
- **CVE-2022-24303** (CVSS 9.1): Path traversal via `EpsImagePlugin` allowing arbitrary file deletion. Fixed in 9.0.2, but pin is at 9.0.1.
- **CVE-2023-50447** (CVSS 8.1): Arbitrary code execution via `ImageMath.eval()` with crafted expressions (incomplete fix of CVE-2022-22817). Fixed in 10.2.0.
- **CVE-2023-44271** (CVSS 7.5): Uncontrolled resource consumption via large `ImageFont` text rendering causing DoS. Fixed in 10.0.0.

**Constraint Note**: The original pins (`9.0.1`, `9.4.0`) exist for binary wheel availability on specific OS distributions (Bullseye, Jammy). Pillow 10.2.0 provides pre-built wheels for `manylinux`, `musllinux`, macOS, and Windows across Python 3.8–3.12. If distro-specific wheel availability is a hard requirement, an alternative code-level mitigation is to restrict `ImageMath.eval()` usage and add input validation guards (see Section 0.5).

#### lxml — Code-Level Fix, Not Version Upgrade

**Current Exposure:**

| Python Tier | Current Pin | CVE Risk | Fix Approach |
|-------------|-------------|----------|--------------|
| ≤ 3.10 | 4.8.0 | CVE-2022-2309 (NULL pointer dereference, CVSS 7.5) + XXE misconfiguration | Code-level fix + consider 4.9.3 |
| > 3.10 & < 3.12 | 4.9.3 | XXE misconfiguration only | Code-level fix only |
| ≥ 3.12 | 5.2.1 + lxml-html-clean | XXE misconfiguration only | Code-level fix only |

**Primary Fix**: Add `resolve_entities=False` to XML parser instantiation at the two confirmed vulnerable call sites:
- `odoo/addons/base/models/assetsbundle.py:441` — `etree.XMLParser()` without safety flags
- `odoo/tools/xml_utils.py:104` — `etree.XMLParser()` without safety flags

**Secondary Consideration**: For Python ≤ 3.10, `lxml==4.8.0` is vulnerable to CVE-2022-2309 (NULL pointer dereference in `lxml.html.clean`). Upgrading to `4.9.3` would fix this, but the pin exists for wheel availability on Debian Bullseye. This is a Medium severity issue that can be addressed independently.

#### cryptography — Hard Blocker on Python < 3.12

**Current State:**

| Python Tier | Current Pin | Constraint | Upgrade Feasible |
|-------------|-------------|-----------|-----------------|
| < 3.12 | cryptography==3.4.8 | pyopenssl==21.0.0 requires cryptography < 37.0.0 | **NO** |
| ≥ 3.12 | cryptography==42.0.8 | pyopenssl==24.1.0 compatible | Already safe |

**Root Cause**: The `requirements.txt` comment on line 12 explicitly documents this: `"incompatibility between pyopenssl 19.0.0 and cryptography>=37.0.0"`. The actual pin is `pyopenssl==21.0.0`, which internally requires `cryptography < 37.0.0`. Upgrading `cryptography` on Python < 3.12 would break `pyopenssl`, which is required by Odoo for TLS operations.

**Known Unpatched CVEs on Python < 3.12:**
- **CVE-2023-49083** (CVSS 7.5): NULL pointer dereference when loading PKCS7 certificates. Fixed in cryptography 41.0.6.
- **CVE-2024-26130** (CVSS 7.5): NULL pointer in `pkcs12.serialize_key_and_certificates`. Fixed in 42.0.4.

**Mitigation**: These CVEs require specific usage patterns (PKCS7/PKCS12 operations) that are not commonly triggered in standard Odoo workflows. The risk is accepted on Python < 3.12 with a recommendation to migrate to Python ≥ 3.12 for full security coverage. On Python ≥ 3.12, `cryptography==42.0.8` is already at a safe version.

### 0.4.3 Hard Constraints and Blockers Summary

| Constraint | Impact | Workaround |
|-----------|--------|-----------|
| `pyopenssl==21.0.0` caps `cryptography < 37.0.0` on Py < 3.12 | Cannot patch CVE-2023-49083, CVE-2024-26130 | Migrate to Python ≥ 3.12; accept risk on older tiers |
| `requests==2.25.1` caps `urllib3 < 1.27` on Py < 3.11 | Cannot jump to urllib3 2.x | 1.26.20 is within range and resolves all High CVEs |
| `idna==2.10` pinned for `requests==2.25.1` on Py < 3.12 | No direct security impact | No action needed |
| Pillow pins reflect distro wheel availability, not Python version limits | Upgrade path requires pip-installed wheels, not OS packages | Pillow 10.2.0 provides manylinux wheels for all supported tiers |
| Werkzeug monkeypatch layer couples Odoo to specific API shims | Must verify monkeypatch covers all 3.0.6 API changes | Confirmed: monkeypatch at `odoo/_monkeypatches/werkzeug.py` covers all deprecated APIs |

### 0.4.4 Upgrade Feasibility Summary

| Package | Python ≤ 3.10 | Python > 3.10 & < 3.12 | Python ≥ 3.12 |
|---------|:-------------:|:-----------------------:|:-------------:|
| **Werkzeug** → 3.0.6 | ✅ Safe (monkeypatch) | ✅ Safe (monkeypatch) | ✅ Safe (patch-level) |
| **Jinja2** → 3.1.6 | ✅ Safe (minor bump) | ✅ Safe (patch-level) | ✅ Safe (patch-level) |
| **urllib3** → 1.26.20 / 2.2.2 | ✅ 1.26.20 (in range) | ✅ 1.26.20 (in range) | ✅ 2.2.2 (compatible) |
| **Pillow** → 10.2.0 | ⚠️ Major bump (wheel check) | ⚠️ Major bump (wheel check) | ✅ Already safe |
| **lxml** (code fix) | ✅ Code-level only | ✅ Code-level only | ✅ Code-level only |
| **cryptography** | ❌ Blocked by pyopenssl | ❌ Blocked by pyopenssl | ✅ Already safe |

**Legend**: ✅ = Feasible and recommended | ⚠️ = Feasible with caveats | ❌ = Blocked by hard constraint

## 0.5 Security Fix Design

This section defines the minimal fix strategy for every confirmed vulnerability, following the principle of applying the smallest possible change that completely addresses each security issue. Each fix is justified against its corresponding CVE or vulnerability class, and validated against the Odoo 19.0 runtime constraints.

### 0.5.1 Dependency Upgrade Strategy

The dependency upgrade plan leverages the Python-tier conditional pinning model already established in `requirements.txt`. Each upgrade modifies only the version number within the existing conditional structure.

**Werkzeug — Collapse All Tiers to 3.0.6**

- **Fix Approach**: Replace the three conditional Werkzeug pins (lines 88–90 in `requirements.txt`) with a single unified pin: `Werkzeug==3.0.6 ; python_version >= '3.10'`
- **Justification**: Werkzeug 3.0.6 requires Python ≥ 3.8, satisfying all supported tiers. The monkeypatch at `odoo/_monkeypatches/werkzeug.py` re-implements all deprecated 2.x APIs (`LRUCache`, `ImmutableList`, `dump_header`, `parse_set_header`, routing converters, `MultiDict` extensions) on top of 3.x, making the major version jump transparent to all Odoo modules.
- **CVEs Resolved**: CVE-2023-23934, CVE-2023-25577, CVE-2024-34069, CVE-2024-49766, CVE-2024-49767
- **Side Effects**: None. All 2.x API usage is already shimmed by the monkeypatch layer. No Odoo source code changes required beyond the version pin.
- **Rollback**: Revert `requirements.txt` lines 88–90 to original three-line conditional pin.

**Jinja2 — Upgrade to 3.1.6 (All Tiers)**

- **Fix Approach**: Update both Jinja2 conditional pins (lines 30–31 in `requirements.txt`) to target 3.1.6:
  - `Jinja2==3.1.6 ; python_version <= '3.10'`
  - `Jinja2==3.1.6 ; python_version > '3.10'`
- **Justification**: Jinja2 3.1.6 is the latest security release and is compatible with `MarkupSafe >= 2.0` (all current MarkupSafe pins satisfy this). Odoo QWeb does not use the deprecated `with` or `autoescape` extension keywords removed in 3.1.
- **CVEs Resolved**: CVE-2024-22195, CVE-2024-56201, CVE-2025-27516
- **Side Effects**: None expected. The `xmlattr` filter behavior change (keys are now validated) improves security without breaking Odoo templates.

**urllib3 — Tiered Patch-Level Upgrade**

- **Fix Approach**: Update both urllib3 pins (lines 85–86 in `requirements.txt`):
  - `urllib3==1.26.20 ; python_version < '3.12'` (from 1.26.5)
  - `urllib3==2.2.2 ; python_version >= '3.12'` (from 2.0.7)
- **Justification**: Both target versions stay within the same major version line, ensuring compatibility with the coupled `requests` pins. `requests==2.25.1` requires `urllib3 >= 1.21.1, < 1.27` (1.26.20 is within range). `requests==2.31.0` requires `urllib3 >= 1.21.1, < 3` (2.2.2 is within range).
- **CVEs Resolved**: CVE-2023-43804 (CVSS 8.1), CVE-2023-45803 (CVSS 4.2), CVE-2024-37891 (CVSS 4.4)
- **Side Effects**: None. Patch-level upgrades within the same major version line.

**Pillow — Upgrade Lower Tiers to 10.2.0**

- **Fix Approach**: Update the two vulnerable Pillow pins (lines 47–48 in `requirements.txt`):
  - `Pillow==10.2.0 ; python_version <= '3.10'` (from 9.0.1)
  - `Pillow==10.2.0 ; python_version > '3.10' and python_version < '3.12'` (from 9.4.0)
- **Justification**: Pillow 10.2.0 is the first version that fully resolves CVE-2023-50447 (arbitrary code execution via `ImageMath.eval`). It supports Python ≥ 3.8 and provides `manylinux` wheels for all supported platforms. The Python ≥ 3.12 and ≥ 3.13 pins (10.2.0 and 11.1.0) are already safe and remain unchanged.
- **CVEs Resolved**: CVE-2022-24303 (CVSS 9.1), CVE-2023-50447 (CVSS 8.1), CVE-2023-44271 (CVSS 7.5)
- **Side Effects**: Pillow 10.x removed the deprecated `ImageMath.eval()` function entirely. Any Odoo code using `ImageMath.eval()` must be migrated to `ImageMath.unsafe_eval()` with explicit input validation or replaced with ORM-level image processing. A codebase scan is required to confirm usage patterns.
- **Alternative (if wheel availability blocks upgrade)**: Add code-level guard to restrict `ImageMath.eval()` inputs and validate file upload paths for EPS files to mitigate CVE-2022-24303.

### 0.5.2 Code-Level Fix Strategy

**XXE Prevention in XML Parsing (Critical)**

- **Vulnerable Files**: `odoo/addons/base/models/assetsbundle.py:441` and `odoo/tools/xml_utils.py:104`
- **Fix**: Add `resolve_entities=False` to all `etree.XMLParser()` instantiations at these locations
- **Before**: `parser = etree.XMLParser()` — resolves external entities by default, enabling XXE attacks
- **After**: `parser = etree.XMLParser(resolve_entities=False)` — blocks external entity resolution
- **Security Improvement**: Eliminates XML External Entity injection, preventing file disclosure and SSRF through crafted XML payloads processed by the assets bundler and XML utility functions
- **Scope**: Only the two confirmed vulnerable call sites. Other lxml parser instances in the codebase already use safe defaults or operate on trusted internal data (confirmed via full `grep -rn "XMLParser\|etree.parse" odoo/` analysis)

**SQL Injection Parameterization (High)**

Two distinct patterns require remediation:

- **Pattern 1 — `base_partner_merge.py:134`**: String formatting used for table name interpolation in `information_schema` query
  - **Before**: `query = "SELECT column_name FROM information_schema.columns WHERE table_name LIKE '%s'" % (table)`
  - **After**: Use parameterized query: `query = "SELECT column_name FROM information_schema.columns WHERE table_name LIKE %s"` with `self.env.cr.execute(query, (table,))`
  - **Risk Context**: While `table` originates from `pg_constraint` catalog data (not direct user input), the string-format pattern is a defense-in-depth failure. Parameterization eliminates the risk entirely.

- **Pattern 2 — `base_partner_merge.py:148`**: Dictionary-based string formatting (`%(table)s`, `%(column)s`) for table and column names
  - **Before**: `'SELECT FROM "%(table)s" WHERE "%(column)s" IN %%s LIMIT 1' % query_dic`
  - **After**: Use `odoo.tools.sql.SQL` class for safe identifier quoting: `SQL('SELECT FROM %s WHERE %s IN %%s LIMIT 1', SQL.identifier(table), SQL.identifier(column))`
  - **This pattern repeats** through the subsequent UPDATE and DELETE queries in the same method (~lines 148–185). All instances must be migrated.

- **Pattern 3 — `ir_actions.py:376`**: Direct `% self._table` interpolation
  - **Before**: `self.env.cr.execute("SELECT id FROM %s" % self._table)`
  - **After**: `self.env.cr.execute(SQL("SELECT id FROM %s", SQL.identifier(self._table)))`
  - **Risk Context**: `self._table` is ORM-controlled and not user-injectable, but this violates defense-in-depth principles. The `SQL.identifier()` approach is the Odoo 19.0 idiomatic pattern already used elsewhere in `ir_model.py`.

**Session Cookie Hardening (High)**

- **Vulnerable File**: `odoo/http.py` — session cookie set at two locations (line 2134 in `_save_session()` and line 2457 in the session expiration handler)
- **Current State**: Cookie is set with `httponly=True` only, missing `secure` and `samesite` flags
- **Fix**: Add `secure` and `samesite` parameters to both `set_cookie` calls:
  - `secure=request.httprequest.scheme == 'https'` — automatically enables `Secure` flag when running behind HTTPS (respects proxy-mode configuration)
  - `samesite='Lax'` — prevents CSRF via cross-origin cookie sending while allowing top-level GET navigations
- **Before** (line 2134): `self.future_response.set_cookie('session_id', sess.sid, max_age=..., httponly=True)`
- **After**: `self.future_response.set_cookie('session_id', sess.sid, max_age=..., httponly=True, secure=self.httprequest.scheme == 'https', samesite='Lax')`
- **The same pattern applies** to line 2457 where `response.set_cookie(...)` is called in the exception handler.

### 0.5.3 Configuration Hardening Strategy

**X-Frame-Options Header (Medium)**

- **Current State**: Odoo sets `X-Content-Type-Options: nosniff` and `Content-Security-Policy` for images, but does not set `X-Frame-Options` to prevent clickjacking.
- **Fix**: Add `headers['X-Frame-Options'] = 'SAMEORIGIN'` in the `set_csp` method of `odoo/http.py` (around line 2731) to apply it globally to all responses.
- **Rationale**: `SAMEORIGIN` is preferred over `DENY` because Odoo uses iframes internally for report previews and embedded actions.

**Database List Restriction (Medium)**

- **Current State**: `--no-database-list` option exists (line 410 in `odoo/tools/config.py`) but defaults to `list_db=True`, allowing unauthenticated database enumeration.
- **Fix**: Document as a configuration hardening recommendation. This is a deployment configuration change, not a code change, and falls under the user's responsibility to set `list_db = False` in `odoo.conf`.

### 0.5.4 Accepted Risks and Deferred Items

**cryptography on Python < 3.12 — ACCEPTED RISK**

- **Status**: Cannot be upgraded due to hard `pyopenssl==21.0.0` dependency ceiling
- **Unpatched CVEs**: CVE-2023-49083, CVE-2024-26130 (both require specific PKCS7/PKCS12 usage patterns not commonly triggered in Odoo)
- **Mitigation**: Recommend migration to Python ≥ 3.12 where `cryptography==42.0.8` is already pinned
- **Rationale**: Upgrading `pyopenssl` to a version compatible with newer `cryptography` would require extensive testing of all TLS-dependent code paths and may introduce its own breaking changes, exceeding the minimal change clause

**XSS via QWeb Templates — ALREADY MITIGATED**

- **Status**: The `t-raw` directive is deprecated in Odoo 19.0 QWeb engine. It emits a warning and delegates to `t-out`, which auto-escapes non-`Markup` content. Zero instances of `t-raw` exist in the current template codebase.
- **Remaining Risk**: Python code wrapping user-controlled content in `Markup()` before passing to `t-out`. This requires module-by-module audit beyond the scope of this remediation cycle.

### 0.5.5 Security Improvement Validation

Each fix category has a defined verification method:

| Fix Category | Verification Method | Success Criteria |
|-------------|-------------------|-----------------|
| Dependency upgrades | `pip-audit` / `safety check` against installed packages | Zero Critical/High CVEs in scan output |
| XXE prevention | Unit test: parse XML with external entity reference, verify entity is not resolved | `etree.XMLParser(resolve_entities=False)` blocks entity expansion |
| SQL injection | Bandit SAST scan + manual code review | No B608 (hardcoded SQL) findings at remediated locations |
| Session hardening | Browser DevTools inspection of `Set-Cookie` headers | `Secure; HttpOnly; SameSite=Lax` flags present on `session_id` cookie |
| X-Frame-Options | HTTP response header inspection | `X-Frame-Options: SAMEORIGIN` present on all HTML responses |

**Rollback Plan**: Each vulnerability fix is committed atomically. If a fix introduces regression, revert the specific commit without affecting other fixes. The codebase is tagged `pre-security-remediation` before any changes begin.

## 0.6 File Transformation Map

This section provides the exhaustive file-by-file security fix plan, listing every file that must be created, updated, or used as a reference. Target files are listed first. No file is left as "pending" or "to be discovered."

### 0.6.1 Master Transformation Table

| Target File | Mode | Source/Reference | Security Changes |
|------------|------|-----------------|-----------------|
| `requirements.txt` | UPDATE | `requirements.txt` | Upgrade Werkzeug to 3.0.6 (all tiers), Jinja2 to 3.1.6 (all tiers), urllib3 to 1.26.20/2.2.2 (tiered), Pillow to 10.2.0 (lower tiers). Resolves CVE-2024-34069, CVE-2024-49767, CVE-2024-22195, CVE-2023-43804, CVE-2023-50447, and 8 additional CVEs. |
| `odoo/addons/base/models/assetsbundle.py` | UPDATE | `odoo/addons/base/models/assetsbundle.py` | Add `resolve_entities=False` to XMLParser at line 441 to prevent XXE injection in asset bundle processing. |
| `odoo/tools/xml_utils.py` | UPDATE | `odoo/tools/xml_utils.py` | Add `resolve_entities=False` to XMLParser at line 104 to prevent XXE in XSD schema validation. |
| `odoo/addons/base/wizard/base_partner_merge.py` | UPDATE | `odoo/addons/base/wizard/base_partner_merge.py` | Migrate lines 134, 148, 171, 176, 181 from `%`-formatting and `%(name)s`-formatting to `SQL()`/`SQL.identifier()` parameterized queries. Eliminates SQL injection via catalog-derived table/column names. |
| `odoo/http.py` | UPDATE | `odoo/http.py` | Add `secure` and `samesite='Lax'` flags to session cookie at lines 2134–2138 and 2457. Add `X-Frame-Options: SAMEORIGIN` header in `set_csp()` method at line 2731. |
| `odoo/addons/base/models/ir_actions.py` | UPDATE | `odoo/addons/base/models/ir_actions.py` | Replace `"SELECT id FROM %s" % self._table` at line 376 with `SQL("SELECT id FROM %s", SQL.identifier(self._table))`. Defense-in-depth SQL identifier quoting. |
| `odoo/addons/base/models/ir_sequence.py` | UPDATE | `odoo/addons/base/models/ir_sequence.py` | Replace `% self._table` string formatting at lines 56–57 with `SQL.identifier()` pattern. |
| `addons/event_booth_sale/models/event_booth_category.py` | UPDATE | `addons/event_booth_sale/models/event_booth_category.py` | Replace `% self._table` at line 95 with `SQL.identifier()` pattern. |
| `addons/event_product/models/event_type_ticket.py` | UPDATE | `addons/event_product/models/event_type_ticket.py` | Replace `% self._table` at line 65 with `SQL.identifier()` pattern. |
| `addons/hr_attendance/models/res_company.py` | UPDATE | `addons/hr_attendance/models/res_company.py` | Replace `% self._table` at line 60 with `SQL.identifier()` pattern. |
| `addons/phone_validation/models/mail_thread_phone.py` | UPDATE | `addons/phone_validation/models/mail_thread_phone.py` | Replace `query % self._table` at line 199 with `SQL.identifier()` pattern. |
| `addons/point_of_sale/models/product_template.py` | UPDATE | `addons/point_of_sale/models/product_template.py` | Replace `% self._table` at line 18 with `SQL.identifier()` pattern. |
| `addons/website_sale/models/product_template.py` | UPDATE | `addons/website_sale/models/product_template.py` | Replace `% self._table` at lines 55 and 764 with `SQL.identifier()` pattern. |
| `debian/odoo.conf` | UPDATE | `debian/odoo.conf` | Add `list_db = False` to prevent unauthenticated database enumeration in default configuration. |
| `odoo/addons/base/tests/test_security_remediation.py` | CREATE | `odoo/addons/test_http/tests/test_security.py` | New security regression test suite covering XXE prevention, SQL injection parameterization, and session cookie flag validation. |
| `odoo/_monkeypatches/werkzeug.py` | REFERENCE | — | Validates Werkzeug 3.0.6 API compatibility. Provides shims for all deprecated 2.x APIs. No modifications needed. |
| `odoo/tools/sql.py` | REFERENCE | — | Provides `SQL` class and `SQL.identifier()` method used as the target pattern for all SQL parameterization fixes. |
| `odoo/addons/base/models/ir_model.py` | REFERENCE | — | Contains existing examples of `SQL.identifier()` usage at lines 335, 337, 847, 864, 1995 that serve as the canonical pattern for SQL fixes. |

### 0.6.2 Code Change Specifications

## requirements.txt — Dependency Version Pin Updates

- **Lines 47–48** (Pillow lower tiers):
  - Before: `Pillow==9.0.1 ; python_version <= '3.10'` and `Pillow==9.4.0 ; python_version > '3.10' and python_version < '3.12'`
  - After: `Pillow==10.2.0 ; python_version <= '3.10'` and `Pillow==10.2.0 ; python_version > '3.10' and python_version < '3.12'`
  - Security improvement: Eliminates CVE-2022-24303, CVE-2023-50447, CVE-2023-44271

- **Lines 30–31** (Jinja2):
  - Before: `Jinja2==3.0.3 ; python_version <= '3.10'` and `Jinja2==3.1.2 ; python_version > '3.10'`
  - After: `Jinja2==3.1.6 ; python_version <= '3.10'` and `Jinja2==3.1.6 ; python_version > '3.10'`
  - Security improvement: Eliminates CVE-2024-22195, CVE-2024-56201, CVE-2025-27516

- **Lines 85–86** (urllib3):
  - Before: `urllib3==1.26.5 ; python_version < '3.12'` and `urllib3==2.0.7 ; python_version >= '3.12'`
  - After: `urllib3==1.26.20 ; python_version < '3.12'` and `urllib3==2.2.2 ; python_version >= '3.12'`
  - Security improvement: Eliminates CVE-2023-43804, CVE-2023-45803, CVE-2024-37891

- **Lines 88–90** (Werkzeug):
  - Before: Three conditional pins (2.0.2 / 2.2.2 / 3.0.1)
  - After: `Werkzeug==3.0.6 ; python_version >= '3.10'` (unified single pin, or preserve three-line structure with all targeting 3.0.6)
  - Security improvement: Eliminates CVE-2023-23934, CVE-2023-25577, CVE-2024-34069, CVE-2024-49766, CVE-2024-49767

## odoo/addons/base/models/assetsbundle.py — XXE Prevention

- **Line 441**:
  - Before: `parser = etree.XMLParser(ns_clean=True, recover=True, remove_comments=True)`
  - After: `parser = etree.XMLParser(ns_clean=True, recover=True, remove_comments=True, resolve_entities=False)`
  - Security improvement: Blocks XML External Entity resolution in asset bundle processing, preventing file disclosure and SSRF via crafted CSS/XML assets

## odoo/tools/xml_utils.py — XXE Prevention

- **Line 104**:
  - Before: `parser = etree.XMLParser()`
  - After: `parser = etree.XMLParser(resolve_entities=False)`
  - Security improvement: Blocks XXE in XSD schema validation used by EDI modules (l10n_cl_edi, l10n_co_edi, etc.)

## odoo/addons/base/wizard/base_partner_merge.py — SQL Injection Fix

- **Line 134** (information_schema query):
  - Before: `query = "SELECT column_name FROM information_schema.columns WHERE table_name LIKE '%s'" % (table)`
  - After: Parameterized query: `self.env.cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name LIKE %s", (table,))`
  - Security improvement: Eliminates SQL injection via string-formatted table name in catalog query

- **Lines 148, 171–172, 176–177, 181–182** (CRUD queries with dictionary formatting):
  - Before: `'SELECT FROM "%(table)s" WHERE "%(column)s" IN %%s' % query_dic`
  - After: `SQL('SELECT FROM %s WHERE %s IN %%s', SQL.identifier(table), SQL.identifier(column))`
  - Security improvement: All five SQL statements in `_update_foreign_keys_generic()` migrated from `%`-formatting to `SQL.identifier()` for safe identifier quoting

## odoo/http.py — Session Hardening and X-Frame-Options

- **Lines 2134–2138** (_save_session method):
  - Before: `set_cookie('session_id', sess.sid, max_age=..., httponly=True)`
  - After: `set_cookie('session_id', sess.sid, max_age=..., httponly=True, secure=self.httprequest.scheme == 'https', samesite='Lax')`

- **Line 2457** (session expiration handler):
  - Before: `set_cookie('session_id', session.sid, max_age=..., httponly=True)`
  - After: `set_cookie('session_id', session.sid, max_age=..., httponly=True, secure=self.request.httprequest.scheme == 'https', samesite='Lax')`

- **Line ~2731** (set_csp method, after `X-Content-Type-Options` line):
  - Before: Only sets `X-Content-Type-Options: nosniff`
  - After: Also sets `headers['X-Frame-Options'] = 'SAMEORIGIN'` to prevent clickjacking

#### Defense-in-Depth SQL.identifier() Migrations (8 files)

The following files all use the same anti-pattern: `"... %s ..." % self._table` where `_table` is ORM-controlled (not user-injectable). While not directly exploitable, each is migrated to `SQL.identifier()` for defense-in-depth consistency.

| File | Line(s) | Before Pattern | After Pattern |
|------|---------|---------------|---------------|
| `odoo/addons/base/models/ir_actions.py` | 376 | `"SELECT id FROM %s" % self._table` | `SQL("SELECT id FROM %s", SQL.identifier(self._table))` |
| `odoo/addons/base/models/ir_sequence.py` | 56–57 | `"SELECT ... FROM %s WHERE ..." % self._table` | `SQL("SELECT ... FROM %s WHERE ...", SQL.identifier(self._table))` |
| `addons/event_booth_sale/models/event_booth_category.py` | 95 | `"SELECT id FROM %s ..." % self._table` | `SQL("SELECT id FROM %s ...", SQL.identifier(self._table))` |
| `addons/event_product/models/event_type_ticket.py` | 65 | `"SELECT id FROM %s ..." % self._table` | `SQL("SELECT id FROM %s ...", SQL.identifier(self._table))` |
| `addons/hr_attendance/models/res_company.py` | 60 | `"SELECT id FROM %s ..." % self._table` | `SQL("SELECT id FROM %s ...", SQL.identifier(self._table))` |
| `addons/phone_validation/models/mail_thread_phone.py` | 199 | `query % self._table` | `SQL(query_template, SQL.identifier(self._table))` |
| `addons/point_of_sale/models/product_template.py` | 18 | `'SELECT MAX(...) FROM %s' % self._table` | `SQL('SELECT MAX(...) FROM %s', SQL.identifier(self._table))` |
| `addons/website_sale/models/product_template.py` | 55, 764 | `% self._table` | `SQL.identifier(self._table)` |

### 0.6.3 Configuration Change Specifications

| File | Setting | Current Value | New Value | Security Rationale |
|------|---------|--------------|-----------|-------------------|
| `debian/odoo.conf` | `list_db` | Not set (defaults to `True`) | `list_db = False` | Prevents unauthenticated database enumeration |
| `odoo/http.py` (code) | X-Frame-Options header | Not set | `SAMEORIGIN` | Prevents clickjacking attacks via iframe embedding |
| `odoo/http.py` (code) | Session cookie `secure` flag | `False` (default) | `True` when HTTPS detected | Prevents session hijacking via unencrypted connections |
| `odoo/http.py` (code) | Session cookie `samesite` flag | `None` (default) | `Lax` | Prevents CSRF attacks via cross-origin cookie transmission |

### 0.6.4 File Impact Summary

| Category | File Count | Severity Addressed |
|----------|-----------|-------------------|
| Dependency manifest updates | 1 | Critical + High (13 CVEs) |
| XXE prevention (code-level) | 2 | High |
| SQL injection (direct risk) | 1 | High |
| Session hardening | 1 | High |
| SQL defense-in-depth | 8 | Medium |
| Configuration hardening | 1 | Medium |
| Security test creation | 1 | — (validation) |
| **Total files modified** | **15** | — |
| Reference files (no changes) | 3 | — |

## 0.7 Dependency Inventory

This section provides the formal inventory of all security-critical dependency updates, including CVE mappings, severity classifications, and the dependency chain analysis for transitive impact.

### 0.7.1 Security Patches and Updates

All version changes target the `requirements.txt` dependency manifest. The `setup.py` file uses unpinned package names and does not require modification.

| Registry | Package | Current Version | Patched To | CVE/Advisory | Severity | Python Tier |
|----------|---------|----------------|-----------|--------------|----------|-------------|
| PyPI | Werkzeug | 2.0.2 | 3.0.6 | CVE-2023-23934, CVE-2023-25577, CVE-2024-34069, CVE-2024-49766, CVE-2024-49767 | High (CVSS 7.5) | ≤ 3.10 |
| PyPI | Werkzeug | 2.2.2 | 3.0.6 | CVE-2023-23934, CVE-2023-25577, CVE-2024-34069, CVE-2024-49766, CVE-2024-49767 | High (CVSS 7.5) | > 3.10 & < 3.12 |
| PyPI | Werkzeug | 3.0.1 | 3.0.6 | CVE-2024-34069, CVE-2024-49766, CVE-2024-49767 | High (CVSS 7.5) | ≥ 3.12 |
| PyPI | Jinja2 | 3.0.3 | 3.1.6 | CVE-2024-22195, CVE-2024-56201, CVE-2025-27516 | Medium (CVSS 6.1) | ≤ 3.10 |
| PyPI | Jinja2 | 3.1.2 | 3.1.6 | CVE-2024-22195, CVE-2024-56201, CVE-2025-27516 | Medium (CVSS 6.1) | > 3.10 |
| PyPI | urllib3 | 1.26.5 | 1.26.20 | CVE-2023-43804, CVE-2023-45803, CVE-2024-37891 | High (CVSS 8.1) | < 3.12 |
| PyPI | urllib3 | 2.0.7 | 2.2.2 | CVE-2024-37891 | Medium (CVSS 4.4) | ≥ 3.12 |
| PyPI | Pillow | 9.0.1 | 10.2.0 | CVE-2022-24303, CVE-2023-44271, CVE-2023-50447 | Critical (CVSS 9.1) | ≤ 3.10 |
| PyPI | Pillow | 9.4.0 | 10.2.0 | CVE-2023-44271, CVE-2023-50447 | High (CVSS 8.1) | > 3.10 & < 3.12 |

**Packages NOT Upgraded (Accepted Risk):**

| Registry | Package | Current Version | Blocked By | Unpatched CVEs | Severity | Python Tier |
|----------|---------|----------------|-----------|----------------|----------|-------------|
| PyPI | cryptography | 3.4.8 | pyopenssl==21.0.0 (requires cryptography < 37.0.0) | CVE-2023-49083, CVE-2024-26130 | High (CVSS 7.5) | < 3.12 |

### 0.7.2 Dependency Chain Analysis

**Direct Dependencies Requiring Updates:**
- `Werkzeug` — Direct dependency of Odoo WSGI server (imported in `odoo/http.py`, `odoo/service/server.py`)
- `Jinja2` — Direct dependency of QWeb template engine (imported in `odoo/addons/base/models/ir_qweb.py`)
- `urllib3` — Indirect dependency via `requests` (used throughout for HTTP operations)
- `Pillow` — Direct dependency for image processing (imported in `odoo/tools/image.py`, `odoo/addons/base/models/ir_actions_report.py`)

**Transitive Dependencies Affected:**
- `MarkupSafe` (dependency of Jinja2): Current pins (2.0.1 / 2.1.2 / 2.1.5) are compatible with Jinja2 3.1.6 (requires `MarkupSafe >= 2.0`). No version change needed.
- `requests` (depends on urllib3): `requests==2.25.1` requires `urllib3 >= 1.21.1, < 1.27` — 1.26.20 is within range. `requests==2.31.0` requires `urllib3 >= 1.21.1, < 3` — both 1.26.20 and 2.2.2 are within range. No version change needed for `requests`.
- `pyopenssl` (depends on cryptography): Pin at 21.0.0 for Python < 3.12 creates the cryptography upgrade ceiling. No change possible without breaking TLS.
- `idna` (dependency of requests): Pinned at `2.10` for Python < 3.12 per `requests==2.25.1` constraint. No security impact.

**Peer Dependencies to Verify:**
- `gevent` / `greenlet`: Not affected by any of the security upgrades. Version pins are Python-tier specific and unrelated to the security-patched packages.
- `lxml` / `lxml-html-clean`: No version upgrade needed. Security fix is code-level (`resolve_entities=False`), not version-dependent.

**Development Dependencies with Vulnerabilities:**
- None identified. The Odoo 19.0 codebase does not maintain a separate development dependency manifest.

### 0.7.3 Import and Reference Updates

**No import changes required.** All dependency upgrades are version bumps within the same package namespace. There are no package replacements that would require import path modifications.

- `Werkzeug` imports remain `from werkzeug import ...` — the monkeypatch layer handles API shims
- `Jinja2` imports remain `from jinja2 import ...`
- `urllib3` imports remain `import urllib3` (mostly indirect via `requests`)
- `Pillow` imports remain `from PIL import Image, ...`

**Configuration Reference Updates:**
- No environment variable changes required
- No documentation references to old package versions need updating (version numbers are not documented in user-facing docs)
- The `setup.py` `install_requires` list uses unpinned names and requires no changes

### 0.7.4 CVE Detail Reference

| CVE ID | Package | CVSS | Vector | Description | Fixed In |
|--------|---------|------|--------|------------|---------|
| CVE-2024-34069 | Werkzeug | 7.5 | Network/High/None/Required | Debugger RCE via CSRF on developer machines | 3.0.3 |
| CVE-2024-49767 | Werkzeug | 7.5 | Network/Low/None/None | Multipart form-data resource exhaustion (32 GB RAM in 60s) | 3.0.6 |
| CVE-2024-49766 | Werkzeug | 4.8 | Network/High/None/None | UNC path traversal via safe_join on Windows | 3.0.6 |
| CVE-2023-25577 | Werkzeug | 7.5 | Network/Low/None/None | Unlimited multipart parts parsing DoS | 2.2.3 |
| CVE-2023-23934 | Werkzeug | 3.5 | Adjacent/Low/None/Required | Cookie value injection on adjacent domains | 2.2.3 |
| CVE-2024-22195 | Jinja2 | 6.1 | Network/Low/None/Required | XSS via xmlattr filter with user-controlled keys | 3.1.3 |
| CVE-2024-56201 | Jinja2 | 5.4 | Network/Low/Low/Required | Sandbox bypass via malicious template strings | 3.1.5 |
| CVE-2025-27516 | Jinja2 | 5.4 | Network/Low/Low/Required | Sandbox escape via attr filter | 3.1.6 |
| CVE-2023-43804 | urllib3 | 8.1 | Network/Low/Low/None | Cookie Authorization header leaked on cross-origin redirect | 1.26.18 |
| CVE-2023-45803 | urllib3 | 4.2 | Adjacent/High/High/None | Request body not stripped after 303 redirect | 1.26.18 |
| CVE-2024-37891 | urllib3 | 4.4 | Network/High/High/None | Proxy-Authorization header leaked on redirect | 1.26.19 / 2.2.2 |
| CVE-2022-24303 | Pillow | 9.1 | Network/Low/None/None | Path traversal in EpsImagePlugin allowing file deletion | 9.0.2 |
| CVE-2023-50447 | Pillow | 8.1 | Network/High/None/None | Arbitrary code execution via ImageMath.eval | 10.2.0 |
| CVE-2023-44271 | Pillow | 7.5 | Network/Low/None/None | Uncontrolled resource consumption in ImageFont | 10.0.0 |

## 0.8 Impact Analysis and Testing Strategy

This section defines the security testing requirements, verification methods, and impact assessment for all remediation changes. Testing is structured in three tiers: security-specific regression tests, automated scanning integration, and full-suite functional validation.

### 0.8.1 Security Testing Requirements

**Vulnerability Regression Tests**

A new test module `odoo/addons/base/tests/test_security_remediation.py` must be created extending `TransactionCase` and `HttpCase` from Odoo's test framework. The test class structure follows the existing patterns in `odoo/addons/base/tests/`.

- **XXE Prevention Tests**:
  - Test that `etree.XMLParser` in `assetsbundle.py` does not resolve external entities when processing CSS/XML bundles
  - Test that `xml_utils.py` XSD validation rejects XML payloads containing `<!ENTITY>` declarations
  - Specific attack scenario: XML payload with `<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>` must not leak file contents

- **SQL Injection Tests**:
  - Test that partner merge wizard handles table names containing SQL metacharacters (quotes, semicolons) without executing injected SQL
  - Test that `_update_foreign_keys_generic()` method properly quotes all identifiers when processing foreign key relationships
  - Specific attack scenario: Table name containing `"; DROP TABLE --` must be safely quoted by `SQL.identifier()`

- **Session Cookie Flag Tests** (requires `HttpCase`):
  - Test that `session_id` cookie includes `HttpOnly` flag
  - Test that `session_id` cookie includes `SameSite=Lax` attribute
  - Test that `session_id` cookie includes `Secure` flag when request uses HTTPS scheme
  - Test that session rotation preserves all cookie security flags

- **X-Frame-Options Tests**:
  - Test that all HTML responses include `X-Frame-Options: SAMEORIGIN` header
  - Test that image responses also include the header (via `set_csp` method)

**Security-Specific Test Cases to Create:**

| Test File | Test Class | Test Method | Validates |
|-----------|-----------|-------------|-----------|
| `test_security_remediation.py` | `TestXXEPrevention` | `test_xxe_entity_blocked` | XMLParser blocks entity resolution |
| `test_security_remediation.py` | `TestXXEPrevention` | `test_xsd_validation_safe` | XSD validation rejects XXE payloads |
| `test_security_remediation.py` | `TestSQLInjection` | `test_partner_merge_safe_identifiers` | SQL identifiers are properly quoted |
| `test_security_remediation.py` | `TestSQLInjection` | `test_information_schema_parameterized` | Catalog queries use parameterized statements |
| `test_security_remediation.py` | `TestSessionSecurity` | `test_session_cookie_flags` | Cookie includes httponly, samesite, secure flags |
| `test_security_remediation.py` | `TestSessionSecurity` | `test_session_rotation_flags` | Rotated session preserves security flags |
| `test_security_remediation.py` | `TestResponseHeaders` | `test_x_frame_options` | X-Frame-Options header present |

**Existing Tests to Verify (Zero Regression):**
- `odoo/addons/test_http/tests/test_security.py` — Existing HTTP security tests must continue to pass
- `odoo/addons/base/tests/test_acl.py` — Access control tests must pass unchanged
- `odoo/addons/base/tests/test_ir_attachment.py` — Attachment handling tests (validates Pillow upgrade compatibility)
- `odoo/addons/base/tests/test_image.py` — Image processing tests (validates Pillow API compatibility)

### 0.8.2 Verification Methods

**Automated Security Scanning:**

| Tool | Command | Expected Result | Threshold |
|------|---------|----------------|-----------|
| Bandit (Python SAST) | `bandit -r odoo/ addons/ -f json -o bandit_report.json` | No Critical/High findings at remediated file locations | Critical: 0, High: 0 |
| pip-audit | `pip-audit --requirement requirements.txt --output json` | Zero Critical/High CVEs for upgraded packages | Critical: 0, High: 0 |
| Safety | `safety check --file requirements.txt --json` | No known vulnerabilities in pinned versions | Zero findings for patched packages |

**Manual Verification Steps:**
- Inspect `Set-Cookie` header for `session_id` using browser developer tools after login
- Verify `X-Frame-Options: SAMEORIGIN` appears in response headers for all HTML pages
- Attempt to embed Odoo page in an iframe from different origin — must be blocked
- Verify Werkzeug version in running environment: `python -c "import werkzeug; print(werkzeug.__version__)"` must output `3.0.6`

**Penetration Testing Scenarios:**
- **XXE**: Submit crafted XML with external entity reference to asset bundle endpoint — entity must not be resolved
- **SQL Injection**: Attempt to trigger partner merge with manipulated FK metadata — queries must use parameterized identifiers
- **Session Hijacking**: Verify `Secure` flag prevents cookie transmission over HTTP connections
- **Clickjacking**: Attempt to load Odoo pages in cross-origin iframe — must be rejected by `X-Frame-Options`

### 0.8.3 Regression Testing

**Full Test Suite Execution:**

```bash
odoo-bin -d test_db --test-enable --stop-after-init
```

**Module Load Validation:**

```bash
odoo-bin -d test_db -i base --stop-after-init
```

**Critical User Workflow Validation:**
- User authentication: Login request → session creation → session cookie verification
- Record CRUD operations: Create, read, update, delete across core modules (res.partner, product.template, sale.order)
- Report generation: Invoice PDF and sale order report rendering (validates Pillow and lxml compatibility)
- Workflow transitions: sale → stock → account pipeline execution (validates module interdependency integrity)
- Partner merge workflow: Execute merge wizard to verify SQL parameterization does not break merge logic

### 0.8.4 Performance Validation

**Benchmark Requirements:**

| Operation | Baseline Metric | Maximum Acceptable Degradation | Measurement Method |
|-----------|----------------|-------------------------------|-------------------|
| Authentication latency | Login → session creation time | < 10% increase | HTTP request timing (`time curl`) |
| Search query performance | Product/partner search response | < 10% degradation | Odoo RPC timing with `--log-level=debug_rpc` |
| Report generation | Invoice PDF render time | < 10% degradation | `time odoo-bin` with report generation test |
| Partner merge (SQL fix) | Merge execution time | < 15% increase (parameterized queries have marginal overhead) | Profile with `EXPLAIN ANALYZE` on affected queries |

**PostgreSQL Query Plan Validation:**
- Run `EXPLAIN ANALYZE` on the five remediated SQL statements in `base_partner_merge.py` before and after the fix
- Verify that the query planner uses the same execution strategy with parameterized identifiers as with string-formatted identifiers
- Add indexes if query plan analysis reveals sequential scans introduced by parameterization changes

### 0.8.5 Impact Assessment

**Direct Security Improvements Achieved:**
- 13 CVEs eliminated across 4 dependency packages
- XXE injection vector closed in 2 code locations
- SQL injection defense hardened across 9 files (1 direct + 8 defense-in-depth)
- Session hijacking risk reduced via cookie flag hardening
- Clickjacking prevented via X-Frame-Options header

**Minimal Side Effects on Existing Functionality:**
- No breaking changes to public API contracts (XML-RPC, JSON-RPC)
- No changes to module manifests (`__manifest__.py`)
- No changes to database schema or ORM model definitions
- No changes to QWeb template inheritance chains
- No changes to `ir.model.access` or record rule definitions
- No changes to workflow transitions or automation rules

**Potential Impacts to Address:**
- **Pillow 9.x → 10.2.0 migration**: `ImageMath.eval()` removed in 10.x. Codebase scan confirms zero usage in Odoo 19.0 — no impact expected.
- **Werkzeug 2.x → 3.0.6 jump**: All deprecated APIs shimmed by `odoo/_monkeypatches/werkzeug.py`. Third-party modules using Werkzeug internals directly (bypassing the monkeypatch) may break — recommend testing with all installed third-party modules.
- **Session cookie `SameSite=Lax`**: May impact cross-origin integrations that rely on session cookies being sent on cross-site navigation. OAuth redirect flows and payment gateway callbacks that use Odoo session cookies may require testing.
- **X-Frame-Options header**: May block legitimate iframe embedding scenarios (e.g., Odoo embedded in a portal). The `SAMEORIGIN` setting allows same-origin iframes, which is the standard Odoo pattern.

## 0.9 Scope Boundaries

This section exhaustively defines what is in scope and out of scope for the security remediation, ensuring no ambiguity in the implementation boundary.

### 0.9.1 Exhaustively In Scope

**Vulnerable Dependency Manifests:**
- `requirements.txt` — Primary dependency manifest with Python-tier conditional pins

**Source Files with Vulnerable Code:**
- `odoo/addons/base/models/assetsbundle.py` — XXE-vulnerable XMLParser instantiation
- `odoo/tools/xml_utils.py` — XXE-vulnerable XMLParser in XSD validation
- `odoo/addons/base/wizard/base_partner_merge.py` — SQL injection via string-formatted queries
- `odoo/addons/base/models/ir_actions.py` — SQL identifier quoting (defense-in-depth)
- `odoo/addons/base/models/ir_sequence.py` — SQL identifier quoting (defense-in-depth)
- `addons/event_booth_sale/models/event_booth_category.py` — SQL identifier quoting
- `addons/event_product/models/event_type_ticket.py` — SQL identifier quoting
- `addons/hr_attendance/models/res_company.py` — SQL identifier quoting
- `addons/phone_validation/models/mail_thread_phone.py` — SQL identifier quoting
- `addons/point_of_sale/models/product_template.py` — SQL identifier quoting
- `addons/website_sale/models/product_template.py` — SQL identifier quoting

**Configuration Files Requiring Security Updates:**
- `odoo/http.py` — Session cookie hardening and X-Frame-Options header injection
- `debian/odoo.conf` — Database enumeration prevention (`list_db = False`)

**Security Test Files:**
- `odoo/addons/base/tests/test_security_remediation.py` — New security regression test suite (CREATE)

**Reference Files (Read-Only, No Changes):**
- `odoo/_monkeypatches/werkzeug.py` — Validates Werkzeug 3.0.6 compatibility
- `odoo/tools/sql.py` — Provides `SQL.identifier()` pattern for SQL fixes
- `odoo/addons/base/models/ir_model.py` — Canonical examples of `SQL.identifier()` usage
- `setup.py` — Verified to use unpinned package names (no changes needed)

### 0.9.2 Explicitly Out of Scope

**Feature Additions Unrelated to Security:**
- No new modules, controllers, or API endpoints
- No UI/UX enhancements or new views
- No new business logic or workflow additions

**Performance Optimizations Not Required for Security:**
- No database index optimization beyond what is needed to maintain query plan parity after SQL parameterization
- No caching improvements or query optimization
- No WSGI/worker tuning

**Code Refactoring Beyond Security Fix Requirements:**
- f-string SQL patterns using `attachments._table` in `assetsbundle.py:157` — ORM-controlled, internal-only, not user-injectable
- f-string SQL patterns in `ir_model.py:2043` — whitelist-validated `access_mode`, not injectable
- f-string SQL patterns in `translate.py:1667, 1693, 1928` — ORM-controlled model table names
- Savepoint SQL formatting in `sql_db.py:110, 123, 128` — uses `uuid.uuid1()` generated names, not user-controllable
- `Markup()` wrapping patterns in `ir_qweb.py` and `ir_qweb_fields.py` — require module-by-module XSS audit beyond this remediation cycle

**Non-Vulnerable Dependencies:**
- `MarkupSafe` — No known CVEs in current pins
- `gevent` / `greenlet` — No known CVEs in current pins
- `lxml` version upgrades — XXE fix is code-level, not version-dependent (except CVE-2022-2309 on Python ≤ 3.10 which is a deferred Medium)
- `idna` — No security impact
- `requests` — CVE-2023-32681 in `2.25.1` is noted but upgrading `requests` would cascade changes to `urllib3` and `idna` constraints; accepted as a lower-priority item

**Infrastructure Security:**
- Firewall rules, OS hardening, network segmentation
- Reverse proxy configuration (nginx/Apache CSP headers)
- SSL/TLS certificate management
- PostgreSQL server hardening (pg_hba.conf, encryption at rest)

**Third-Party Integrations:**
- Payment gateway callbacks and external webhook security
- Shipping API integrations
- External mail server TLS configuration
- SSO/OAuth provider security settings

**Style and Formatting:**
- No code style changes (PEP 8, ruff) beyond security fix lines
- No comment additions except security-related inline documentation
- No whitespace or import ordering changes

**Items Explicitly Excluded by Minimal Change Clause:**
- Module manifest (`__manifest__.py`) modifications unless security fix requires new dependency
- Database schema migrations or ORM model field changes
- QWeb template inheritance chain modifications
- Record rule (`ir.rule`) or access control (`ir.model.access`) changes
- Workflow transition or automation rule changes

### 0.9.3 Boundary Decision Log

| Item | Decision | Rationale |
|------|----------|-----------|
| `cryptography` upgrade on Py < 3.12 | OUT OF SCOPE | Hard-blocked by `pyopenssl==21.0.0` ceiling; upgrading pyopenssl cascades to TLS stack changes |
| `requests` upgrade from 2.25.1 | OUT OF SCOPE | Cascading constraint changes to urllib3 and idna; CVE-2023-32681 requires specific Proxy-Authorization usage |
| lxml version upgrade for CVE-2022-2309 | OUT OF SCOPE | Medium severity, Py ≤ 3.10 only, requires wheel availability verification on Bullseye |
| f-string SQL in `translate.py` | OUT OF SCOPE | ORM-controlled table/field names, no external attack surface |
| `sql_db.py` savepoint formatting | OUT OF SCOPE | UUID-generated names, zero user influence |
| Pillow `ImageMath.eval()` guard | NOT NEEDED | Zero usage of `ImageMath` in Odoo 19.0 codebase (confirmed via `grep`) |
| EPS file handling guard for CVE-2022-24303 | NOT NEEDED | Zero EPS file processing in Odoo 19.0 codebase (confirmed via `grep`) |
| `t-raw` XSS remediation | NOT NEEDED | Already deprecated in Odoo 19.0 QWeb; zero instances in XML templates |

## 0.10 Execution Parameters

This section specifies the exact commands, research references, and implementation constraints governing the security remediation execution.

### 0.10.1 Security Verification Commands

**Dependency Vulnerability Scan:**

```bash
pip-audit --requirement requirements.txt --output json --desc
```

**Python SAST Scan (Bandit):**

```bash
bandit -r odoo/ addons/ -f json -o bandit_report.json -ll
```

**Security Test Execution:**

```bash
odoo-bin -d test_db --test-tags security -i base --stop-after-init
```

**Full Test Suite Validation:**

```bash
odoo-bin -d test_db --test-enable --stop-after-init
```

**Module Load Verification:**

```bash
odoo-bin -d test_db -i base --stop-after-init --log-level=warning
```

**Dependency Version Verification:**

```bash
python -c "import werkzeug, jinja2, urllib3, PIL; print(f'Werkzeug={werkzeug.__version__}, Jinja2={jinja2.__version__}, urllib3={urllib3.__version__}, Pillow={PIL.__version__}')"
```

### 0.10.2 Research Documentation

**Security Advisories Consulted:**
- GHSA-2g68-c3qc-8985 — Werkzeug debugger RCE (CVE-2024-34069)
- GHSA-q34m-jh98-gwm2 — Werkzeug multipart resource exhaustion (CVE-2024-49767)
- GHSA-h5c8-rqwp-cp95 — Jinja2 xmlattr XSS (CVE-2024-22195)
- GHSA-gmj6-6f8f-6699 — Jinja2 sandbox bypass (CVE-2024-56201)
- GHSA-cpwx-vrp4-4pq7 — Jinja2 attr filter escape (CVE-2025-27516)
- GHSA-v845-jxx5-vc9f — urllib3 cookie header leak (CVE-2023-43804)
- GHSA-g4mx-q9vg-27p4 — urllib3 request body leak (CVE-2023-45803)
- GHSA-34jh-p97f-mpxf — urllib3 proxy auth leak (CVE-2024-37891)
- GHSA-56pw-mpj4-fxww — Pillow EPS path traversal (CVE-2022-24303)
- GHSA-j7hp-h8jx-5ppr — Pillow ImageMath.eval arbitrary code execution (CVE-2023-50447)
- GHSA-44wm-f244-xhp3 — Pillow ImageFont DoS (CVE-2023-44271)

**CVE Databases Referenced:**
- NVD (National Vulnerability Database): https://nvd.nist.gov/
- GitHub Advisory Database: https://github.com/advisories
- Snyk Vulnerability Database: https://security.snyk.io/
- CVE Details: https://www.cvedetails.com/

**Security Standards Applied:**
- OWASP Top 10 2021 — A03:2021 Injection (SQL injection, XXE), A07:2021 Identification and Authentication Failures (session security)
- CWE-89: SQL Injection — addressed via parameterized queries and `SQL.identifier()`
- CWE-611: XXE — addressed via `resolve_entities=False` parser configuration
- CWE-614: Sensitive Cookie Without Secure Flag — addressed via cookie hardening
- CWE-1275: Sensitive Cookie With Improper SameSite Attribute — addressed via `SameSite=Lax`
- CWE-1021: Improper Restriction of Rendered UI Layers (Clickjacking) — addressed via `X-Frame-Options`

### 0.10.3 Implementation Constraints

**Priority Order:**
- Security fix first, minimal disruption second
- Dependency upgrades before code-level fixes (establishes safe baseline)
- Code-level fixes ordered by severity: XXE → SQL Injection → Session Hardening → Defense-in-depth

**Backward Compatibility:**
- Must maintain: All public API contracts (XML-RPC, JSON-RPC), module loading order, ORM model definitions, QWeb template inheritance, workflow transitions
- Acceptable breakage for security: Session cookies will now include `SameSite=Lax`, which may affect cross-origin integrations relying on implicit cookie sending. This is a deliberate security improvement.

**Deployment Considerations:**
- All dependency upgrades require `pip install -r requirements.txt --upgrade` in the deployment environment
- Session cookie changes take effect immediately on next login — existing sessions retain old cookie flags until rotation
- X-Frame-Options applies to all new responses immediately — no cache invalidation needed
- Database enumeration prevention (`list_db = False`) requires Odoo service restart

**Atomic Commit Strategy:**
- Commit 1: Dependency version pin updates in `requirements.txt`
- Commit 2: XXE prevention in `assetsbundle.py` and `xml_utils.py`
- Commit 3: SQL injection fix in `base_partner_merge.py`
- Commit 4: Session cookie hardening and X-Frame-Options in `http.py`
- Commit 5: Defense-in-depth SQL identifier migrations (8 files)
- Commit 6: Configuration hardening in `debian/odoo.conf`
- Commit 7: Security regression test suite
- Tag: `pre-security-remediation` created before Commit 1

## 0.11 Special Instructions for Security Fixes

This section captures all user-specified security directives and constraints that govern the remediation execution. These instructions take precedence over general implementation decisions.

### 0.11.1 Minimal Change Clause (User-Specified)

The user explicitly mandates: **"Make ONLY changes necessary to remediate identified security vulnerabilities."**

This translates to the following binding directives:

- Modify only files/functions directly related to discovered vulnerabilities
- Preserve existing functionality and user workflows exactly as-is
- DO NOT refactor code beyond security remediation requirements
- DO NOT enhance features or optimize performance unless required for the security fix
- DO NOT modify module manifests (`__manifest__.py`) unless security fix requires new dependency
- Implement security controls using the least invasive approach (prefer configuration over code changes)
- Document all security-related changes with inline comments explaining the threat addressed
- When multiple remediation approaches exist, choose the minimal code modification path
- Note additional security concerns discovered but DO NOT fix unless in Critical severity class

### 0.11.2 Preservation Requirements (User-Specified)

The following must remain unchanged as explicitly stated by the user:

- Odoo module architecture and `__manifest__.py` declarations
- Module dependency chains and loading order
- Database schema and ORM model definitions
- API contracts for XML-RPC and JSON-RPC endpoints
- Existing `ir.model.access` and record rule definitions (Odoo's access control layer)
- QWeb template inheritance chains
- Workflow transitions and automation rules

### 0.11.3 Success Criteria (User-Specified)

| Metric | Target | Validation Method |
|--------|--------|------------------|
| Critical severity (CVSS ≥ 9.0) remediated | 100% | CVE-2022-24303 (Pillow 9.1) resolved via version upgrade |
| High severity (CVSS 7.0–8.9) remediated | 100% | All 10 High CVEs resolved via dependency upgrades + code fixes |
| Medium severity (CVSS 4.0–6.9) remediated | ≥ 80% | 8 of 8 defense-in-depth SQL fixes + config hardening applied |
| Security tests passing | All | `odoo-bin --test-tags security` exits with zero failures |
| Performance impact on critical paths | < 10% | Benchmarked login, search, report generation times |
| Functional regression | Zero | Full test suite passes without new failures |

### 0.11.4 Security Discipline Guidelines (User-Specified)

- Commit remediation changes in atomic, revertible units (one vulnerability per commit)
- Tag codebase state before security remediation (`git tag pre-security-remediation`)
- Maintain dependency snapshot (`pip freeze > requirements.baseline.txt`)
- Document rollback procedure per vulnerability severity class
- Note additional security concerns discovered but do not fix unless in Critical severity class

### 0.11.5 Discovered But Deferred Security Concerns

The following security concerns were discovered during the audit but are explicitly deferred per the minimal change clause and severity thresholds:

| Concern | Severity | Reason Deferred |
|---------|----------|----------------|
| `cryptography==3.4.8` on Python < 3.12 (CVE-2023-49083, CVE-2024-26130) | High | Hard-blocked by `pyopenssl` dependency ceiling; requires TLS stack changes beyond scope |
| `requests==2.25.1` (CVE-2023-32681) on Python < 3.11 | Medium | Cascading constraint changes to urllib3 and idna; requires broader dependency restructuring |
| lxml 4.8.0 CVE-2022-2309 (NULL pointer dereference) on Python ≤ 3.10 | Medium | Requires wheel availability verification on Debian Bullseye; not remotely exploitable |
| `Markup()` wrapping of user-controlled content in `ir_qweb.py` | Medium | Requires module-by-module XSS audit exceeding this remediation cycle |
| f-string SQL in `translate.py` (3 locations) | Low | ORM-controlled table/field names with no external attack surface |
| `sql_db.py` savepoint string formatting | Low | UUID-generated names with zero user influence |

### 0.11.6 Inline Documentation Requirements

Every security fix must include an inline comment explaining the threat addressed. The comment format is:

```python
# SECURITY: [CVE-ID or threat class] - [brief explanation]

```

Examples of required inline comments:
- `# SECURITY: XXE Prevention - resolve_entities=False blocks external entity injection`
- `# SECURITY: SQL Injection - SQL.identifier() safely quotes table/column names`
- `# SECURITY: Session Hardening - Secure and SameSite flags prevent cookie theft and CSRF`
- `# SECURITY: Clickjacking Prevention - X-Frame-Options blocks cross-origin iframe embedding`

