# Technical Specification

# 0. Agent Action Plan

## 0.1 Intent Clarification

### 0.1.1 Core Refactoring Objective

Based on the prompt, the Blitzy platform understands that the refactoring objective is to **migrate the Odoo 19 filestore from local filesystem storage to a pluggable S3-compatible backend**, using Moto as the in-process AWS service mocking layer for dev/test parity, while preserving 100% functional parity with existing Odoo attachment behavior.

- **Refactoring type:** Tech stack migration — Storage backend abstraction (filesystem → S3)
- **Target repository:** Same repository (`blitzy-public-samples/blitzy-odoo`, branch `19.0`)
- **Scope of change:** Surgical — only three methods in one model file are modified, plus dependency and test additions

**Refactoring goals with enhanced clarity:**

- **Pluggable S3 Storage Backend** — Introduce an S3 storage path within the existing `ir.attachment` model's `_file_write`, `_file_read`, and `_file_delete` methods, activated exclusively when `IR_ATTACHMENT_STORAGE=s3` is set as an environment variable
- **Transparent Moto Test Harness** — All S3 calls use `boto3`, intercepted transparently by Moto's `mock_aws` context during tests; the implementation code is identical whether targeting Moto or real AWS — only credentials and endpoint differ
- **Zero Regression Guarantee** — All existing Odoo tests must pass unmodified; no changes to the `ir.attachment` public API signatures, PostgreSQL schema, or ORM field definitions
- **Zero Manual Setup** — S3 bucket auto-provisioned on Odoo startup via idempotent `create_bucket` (no-op if exists), and test execution requires only `pip install -r requirements.txt && pytest tests/s3_integration/` from a clean clone
- **Per-Call Client Instantiation** — The boto3 S3 client must be instantiated per-call via a `_get_s3_client()` helper to guarantee Moto interception; cached clients bypass Moto entirely

**Implicit requirements surfaced:**

- The `_get_s3_client()` helper must read all AWS configuration from environment variables at call time, not at import or class-init time
- The `AWS_ENDPOINT_URL` environment variable must be explicitly removed during tests to prevent stale LocalStack values from bypassing Moto
- An `__init__.py` file is needed in `tests/s3_integration/` to make it a proper Python package for pytest discovery
- Inline comments documenting every change to `ir_attachment.py` with the marker `# S3 storage backend — see IR_ATTACHMENT_STORAGE env var.`

### 0.1.2 Technical Interpretation

This refactoring translates to the following technical transformation strategy:

**Current Architecture:**
- `ir.attachment` stores binary files exclusively on the local filesystem via `_file_write`, `_file_read`, and `_file_delete`
- File paths follow the pattern `{checksum[:2]}/{checksum}` within the configured filestore directory
- A garbage collection mechanism (`_mark_for_gc`, `_gc_file_store`) manages orphaned files

**Target Architecture:**
- `ir.attachment` gains an S3 code path within the same three methods, branching on `os.environ.get('IR_ATTACHMENT_STORAGE') == 's3'`
- When S3 is active, files are written to/read from/deleted from an S3 bucket using the same `{checksum[:2]}/{checksum}` key structure
- When S3 is not active, existing filesystem logic executes unchanged
- A new `_get_s3_client()` instance method returns a fresh `boto3.client('s3')` on every invocation

**Transformation rules:**

| Rule | Description |
|------|-------------|
| Conditional branching | Each of `_file_write`, `_file_read`, `_file_delete` checks `IR_ATTACHMENT_STORAGE` env var at the top of the method |
| Fallback preservation | The `else` branch preserves the original filesystem implementation verbatim |
| Key format consistency | S3 object keys use the same `{checksum[:2]}/{checksum}` pattern as filesystem paths |
| Client lifecycle | `_get_s3_client()` creates a new `boto3.client('s3')` per invocation — never cached |
| Bucket auto-creation | Idempotent bucket creation on Odoo startup path |
| Error handling | `_file_read` on a missing S3 key returns `b''` (matching current filesystem behavior) rather than raising an unhandled exception |

**Success criteria:**

- All 7 mandatory test scenarios in `tests/s3_integration/test_s3_attachment.py` pass against Moto-mocked S3
- All existing Odoo tests pass unmodified
- S3 operation latency ≤500ms per call (trivially satisfied with Moto's in-process, synchronous mock)
- Complete end-to-end execution from clean clone: `pip install -r requirements.txt && pytest tests/s3_integration/ -v`


## 0.2 Source Analysis

### 0.2.1 Comprehensive Source File Discovery

The refactoring scope is intentionally narrow by design — a minimal-change mandate that touches only the files explicitly listed in the user's System Boundaries specification. The following analysis maps every source file requiring modification or serving as reference context.

**Primary Modification Target:**

```
odoo/addons/base/models/ir_attachment.py   (949 lines)
├── IrAttachment class (line 48)
│   ├── _file_read(fname, size)            (lines 133-142)  — TO BE MODIFIED
│   ├── _file_write(bin_value, checksum)   (lines 145-157)  — TO BE MODIFIED
│   ├── _file_delete(fname)                (lines 159-162)  — TO BE MODIFIED
│   ├── _get_s3_client()                                     — TO BE ADDED
│   ├── _storage()                         (lines 74-76)    — READ-ONLY REFERENCE
│   ├── _filestore()                       (lines 78-80)    — READ-ONLY REFERENCE
│   ├── _get_path(bin_data, sha)           (lines 118-131)  — READ-ONLY REFERENCE
│   ├── _full_path(path)                   (lines 111-116)  — READ-ONLY REFERENCE
│   └── _mark_for_gc(fname)               (lines 164-175)  — READ-ONLY REFERENCE
```

**Method-Level Analysis of Modification Targets:**

| Method | Lines | Current Behavior | Modification |
|--------|-------|------------------|-------------|
| `_file_read(fname, size)` | 133-142 | Opens file from `_full_path(fname)`, returns bytes or `b''` on error | Add S3 branch: call `_get_s3_client().get_object()` when `IR_ATTACHMENT_STORAGE=s3`, return body bytes |
| `_file_write(bin_value, checksum)` | 145-157 | Gets path via `_get_path()`, writes to disk, marks for GC | Add S3 branch: call `_get_s3_client().put_object()` with key `{checksum[:2]}/{checksum}` |
| `_file_delete(fname)` | 159-162 | Marks file for filesystem garbage collection | Add S3 branch: call `_get_s3_client().delete_object()` by key |
| `_get_s3_client()` | N/A | Does not exist | New helper: instantiate `boto3.client('s3')` with env var configuration |

**Dependency Manifest:**

```
requirements.txt   (root level, ~80 lines)
├── Version-conditional pins for Python 3.10-3.13
├── No existing boto3 or moto entries
└── TO BE MODIFIED: append boto3>=1.34.0 and moto[s3]>=5.0.0
```

**Repository Configuration:**

```
.gitignore   (root level, ~50 lines)
├── Existing entries: *.py[co], __pycache__/, node_modules/, etc.
├── No .env entry present
└── TO BE MODIFIED: add .env to prevent credential leaks
```

### 0.2.2 Reference Files (Read-Only Context)

These files are not modified but are essential context for understanding the integration surface:

| File | Lines | Purpose |
|------|-------|---------|
| `odoo/addons/base/models/__init__.py` | ~60 | Imports `ir_attachment` — no change needed |
| `odoo/addons/base/tests/test_ir_attachment.py` | 475 | Existing test suite — MUST NOT be modified, must continue passing |
| `odoo/release.py` | ~40 | `MIN_PY_VERSION = (3, 10)`, confirms Python 3.12 compatibility |
| `setup.py` | ~75 | `python_requires` derived from `MIN_PY_VERSION` |
| `README.md` | ~40 | Project landing page — no change needed |

### 0.2.3 Current Structure Mapping

```
Current Repository Structure (relevant paths only):
blitzy-odoo/  (branch 19.0)
├── .gitignore                                     — TO BE MODIFIED
├── requirements.txt                               — TO BE MODIFIED
├── README.md                                      — UNCHANGED
├── setup.py                                       — UNCHANGED
├── odoo/
│   ├── release.py                                 — UNCHANGED (reference: Python version)
│   └── addons/
│       └── base/
│           ├── models/
│           │   ├── __init__.py                    — UNCHANGED (imports ir_attachment)
│           │   └── ir_attachment.py               — TO BE MODIFIED (3 methods + 1 new)
│           └── tests/
│               └── test_ir_attachment.py           — MUST NOT TOUCH (475 lines)
├── tests/                                         — DOES NOT EXIST (to be created)
├── .env.example                                   — DOES NOT EXIST (to be created)
└── docker-compose.yml                             — DOES NOT EXIST (to be created)
```

All source files requiring refactoring have been comprehensively identified. No additional files need discovery.


## 0.3 Scope Boundaries

### 0.3.1 Exhaustively In Scope

**Source Transformations:**

| Pattern | Scope Detail |
|---------|-------------|
| `odoo/addons/base/models/ir_attachment.py` | Modify `_file_write`, `_file_read`, `_file_delete`; add `_get_s3_client` helper; add `import boto3` and `import os` (os already imported) |
| `requirements.txt` | Append two new dependency lines: `boto3>=1.34.0` and `moto[s3]>=5.0.0` |
| `.gitignore` | Append `.env` to prevent credential files from being committed |

**New File Creation:**

| Pattern | Scope Detail |
|---------|-------------|
| `tests/s3_integration/__init__.py` | Empty file for Python package recognition |
| `tests/s3_integration/conftest.py` | Moto fixtures using `@mock_aws` with explicit environment setup via `monkeypatch` |
| `tests/s3_integration/test_s3_attachment.py` | Seven mandatory test scenarios covering S3 CRUD, fallback, and Moto interception |
| `.env.example` | Documents all required environment variables with dev/test defaults |
| `docker-compose.yml` | Optional convenience file for full Odoo stack (PostgreSQL + Odoo only) |

**Test Validation:**

| Pattern | Scope Detail |
|---------|-------------|
| `tests/s3_integration/test_s3_attachment.py` | All 7 test scenarios must pass at 100% gate |
| `odoo/addons/base/tests/test_ir_attachment.py` | Existing tests must continue passing unmodified (read-only validation) |

**Configuration and Documentation:**

| Pattern | Scope Detail |
|---------|-------------|
| `.env.example` | Document `IR_ATTACHMENT_STORAGE`, `AWS_S3_BUCKET`, `AWS_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` |

### 0.3.2 Explicitly Out of Scope

The user has defined strict system boundaries. The following are explicitly out of scope and must not be touched:

**Odoo Core Application Logic:**

- All Odoo addon business logic outside the three `_file_*` methods and `_get_s3_client` helper in `ir_attachment.py`
- All other model files in `odoo/addons/base/models/` (approximately 30+ files)
- All addon modules in `addons/` (300+ modules)
- `odoo/addons/base/models/__init__.py` — no import changes needed

**Database and ORM Layer:**

- PostgreSQL schema — zero DDL changes
- ORM field definitions on `ir.attachment` — `store_fname`, `db_datas`, `checksum`, `mimetype`, `file_size` remain identical
- `ir.attachment` public API signatures — `_file_write(bin_data, checksum)`, `_file_read(fname, bin_size)`, `_file_delete(fname)` signatures unchanged

**Existing Test Suite:**

- `odoo/addons/base/tests/test_ir_attachment.py` — zero modifications permitted
- All other existing Odoo tests across all addon modules — must continue passing

**Frontend and Web Layer:**

- Frontend/JavaScript layer — no changes
- OWL components, web assets, SCSS — no changes
- XML views, QWeb templates — no changes

**Server Infrastructure:**

- `odoo-bin` entrypoint — no changes
- Authentication, session management — no changes
- All XML-RPC and JSON-RPC endpoint behaviors — unchanged
- WSGI/HTTP layer in `odoo/http.py` — no changes

**Unrelated Refactoring:**

- No refactoring of unrelated code
- No features beyond S3 filestore switching
- No modifications to the garbage collection system (`_gc_file_store`, `_gc_file_store_unsafe`) for the S3 path — S3 objects are deleted directly via `delete_object` API
- No architectural changes to Odoo's module loading, registry, or environment systems


## 0.4 Target Design

### 0.4.1 Refactored Structure Planning

The target structure preserves the existing repository layout exactly, adding only the files specified in the System Boundaries. No existing directories are reorganized.

**Target Architecture:**

```
Target:
blitzy-odoo/  (branch 19.0)
├── .gitignore                                     — UPDATED: add .env
├── .env.example                                   — NEW: environment variable documentation
├── docker-compose.yml                             — NEW: optional Odoo+PostgreSQL convenience stack
├── requirements.txt                               — UPDATED: add boto3, moto[s3], pytest, pytest-odoo
├── README.md                                      — UNCHANGED
├── setup.py                                       — UNCHANGED
├── setup.cfg                                      — UNCHANGED
├── ruff.toml                                      — UNCHANGED
├── odoo/
│   ├── release.py                                 — UNCHANGED
│   └── addons/
│       └── base/
│           ├── models/
│           │   ├── __init__.py                    — UNCHANGED
│           │   └── ir_attachment.py               — UPDATED: S3 backend in _file_* methods + _get_s3_client
│           └── tests/
│               └── test_ir_attachment.py           — UNCHANGED (must pass)
├── tests/                                         — NEW DIRECTORY
│   └── s3_integration/                            — NEW DIRECTORY
│       ├── __init__.py                            — NEW: empty package init
│       ├── conftest.py                            — NEW: Moto aws_s3 fixture + monkeypatch setup
│       └── test_s3_attachment.py                  — NEW: 7 mandatory test scenarios
```

### 0.4.2 Web Search Research Conducted

Research was conducted on the following topics to inform the target design:

- **Moto `mock_aws` best practices with pytest fixtures** — Confirmed that boto3 clients must be created inside the active `mock_aws` context for interception to work. The official Moto documentation states that "moto.core should be imported before a client is created" and recommends establishing a mock before clients are set up. This validates the per-call client instantiation requirement.
- **boto3 S3 client lifecycle patterns** — Confirmed that creating a fresh client per call is the safest approach for test mocking. The standard pattern uses `boto3.client('s3')` within the active mock context.
- **Package version verification** — Confirmed `boto3` latest stable version is 1.42.x (>=1.34.0 as specified is valid), `moto` latest stable version is 5.1.x (>=5.0.0 as specified is valid), both actively maintained on PyPI.

### 0.4.3 Design Pattern Applications

**Strategy Pattern for Storage Backend:**

The implementation applies the Strategy pattern implicitly through environment variable-driven branching within each `_file_*` method. Rather than introducing a separate storage backend class hierarchy (which would violate the minimal-change mandate), the S3 path is a conditional branch gated by `os.environ.get('IR_ATTACHMENT_STORAGE') == 's3'`.

```python
def _file_read(self, fname, size=None):
    if os.environ.get('IR_ATTACHMENT_STORAGE') == 's3':
        # S3 path
    else:
        # Original filesystem path (unchanged)
```

**Factory Method for Client Creation:**

The `_get_s3_client()` helper serves as a factory method that creates a new boto3 S3 client on every call, reading configuration from environment variables at invocation time:

```python
def _get_s3_client(self):
    return boto3.client('s3', ...)
```

**Idempotent Initialization for Bucket Provisioning:**

Bucket auto-creation uses an idempotent `create_bucket` call wrapped in exception handling — `ClientError` with `BucketAlreadyOwnedByYou` is caught and treated as a no-op. This follows the idempotent initialization pattern.

### 0.4.4 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Environment variable gating (`IR_ATTACHMENT_STORAGE`) over Odoo system parameter | Env vars are available before Odoo ORM is initialized; avoids database dependency for storage routing |
| Per-call client instantiation over cached client | Moto only intercepts clients created within active `mock_aws` context; caching at module/class/instance level bypasses Moto |
| Inline branching over class hierarchy | Minimal-change mandate — adding classes would touch more files and require import changes |
| `ClientError` handling in `_file_read` returning `b''` | Matches existing filesystem behavior where `OSError` returns `b''` (line 142) |
| S3 key format `{checksum[:2]}/{checksum}` | Preserves the same key structure as filesystem paths for consistency |
| `monkeypatch.delenv('AWS_ENDPOINT_URL')` in conftest | Prevents stale LocalStack holdover values from bypassing Moto interception |


## 0.5 Transformation Mapping

### 0.5.1 File-by-File Transformation Plan

Every target file is mapped to a source file with its transformation mode and detailed description of key changes. This is a single-phase execution — the entire refactor is delivered in one phase.

| Target File | Transformation | Source File | Key Changes |
|------------|----------------|-------------|-------------|
| `odoo/addons/base/models/ir_attachment.py` | UPDATE | `odoo/addons/base/models/ir_attachment.py` | Add `import boto3` at top; add `_get_s3_client(self)` helper method; modify `_file_read` to branch on `IR_ATTACHMENT_STORAGE=s3` for S3 `get_object`; modify `_file_write` to branch for S3 `put_object`; modify `_file_delete` to branch for S3 `delete_object`; add idempotent bucket auto-creation logic; add inline comment `# S3 storage backend — see IR_ATTACHMENT_STORAGE env var.` on every changed line |
| `requirements.txt` | UPDATE | `requirements.txt` | Append `boto3>=1.34.0` and `moto[s3]>=5.0.0` with comment headers; append `pytest>=8.0` and `pytest-odoo` for test execution |
| `.gitignore` | UPDATE | `.gitignore` | Append `.env` entry under dotfiles section to prevent credential leakage |
| `tests/s3_integration/__init__.py` | CREATE | — | Empty file for Python package recognition by pytest |
| `tests/s3_integration/conftest.py` | CREATE | — | Implement `aws_s3` pytest fixture: use `monkeypatch` to set `IR_ATTACHMENT_STORAGE=s3`, `AWS_S3_BUCKET=odoo-attachments`, `AWS_ACCESS_KEY_ID=test`, `AWS_SECRET_ACCESS_KEY=test`, `AWS_DEFAULT_REGION=us-east-1`; use `monkeypatch.delenv('AWS_ENDPOINT_URL', raising=False)`; start `mock_aws()` context; create bucket; yield client. Implement separate `filesystem_storage` fixture for fallback test. |
| `tests/s3_integration/test_s3_attachment.py` | CREATE | — | Implement 7 mandatory test scenarios: (1) bucket auto-creation idempotent, (2) file write to S3, (3) file read integrity via SHA1, (4) file delete from S3, (5) missing file graceful error, (6) filesystem fallback when `IR_ATTACHMENT_STORAGE` unset, (7) Moto interception confirmation. Each test includes `time.monotonic()` performance assertion ≤500ms. |
| `.env.example` | CREATE | — | Document all 6 environment variables: `IR_ATTACHMENT_STORAGE=s3`, `AWS_S3_BUCKET=odoo-attachments`, `AWS_ENDPOINT_URL=`, `AWS_ACCESS_KEY_ID=test`, `AWS_SECRET_ACCESS_KEY=test`, `AWS_DEFAULT_REGION=us-east-1` with inline comments explaining dev/test vs production usage |
| `docker-compose.yml` | CREATE | — | Optional convenience file defining two services: `db` (PostgreSQL 16 image) and `web` (Odoo 19 with volume mounts); no S3/Moto services — S3 mocking handled entirely in-process by Moto |

### 0.5.2 Cross-File Dependencies

**Import Statement Updates:**

The only import addition is within `ir_attachment.py`:

- **ADD:** `import boto3` — new top-level import for S3 client creation
- **ADD:** `from botocore.exceptions import ClientError` — for graceful error handling on missing keys and idempotent bucket creation
- **EXISTING:** `import os` — already imported at line 8, used for `os.environ.get()` calls

No other files in the repository require import changes. The S3 integration is entirely self-contained within the `IrAttachment` class.

**Environment Variable Dependencies:**

All S3 configuration is read from environment variables at runtime. No Odoo configuration files, XML data files, or system parameters are modified.

| Variable | Read By | Purpose |
|----------|---------|---------|
| `IR_ATTACHMENT_STORAGE` | `ir_attachment.py` (`_file_write`, `_file_read`, `_file_delete`) | Gates S3 vs filesystem path |
| `AWS_S3_BUCKET` | `ir_attachment.py` (all S3 operations) | Target bucket name |
| `AWS_ENDPOINT_URL` | `ir_attachment.py` (`_get_s3_client`) | Custom endpoint (unset for Moto) |
| `AWS_ACCESS_KEY_ID` | `ir_attachment.py` (`_get_s3_client`) | AWS credential |
| `AWS_SECRET_ACCESS_KEY` | `ir_attachment.py` (`_get_s3_client`) | AWS credential |
| `AWS_DEFAULT_REGION` | `ir_attachment.py` (`_get_s3_client`) | AWS region |

**Test-to-Source Dependencies:**

| Test File | Depends On |
|-----------|-----------|
| `tests/s3_integration/conftest.py` | `boto3`, `moto`, `pytest` (all from PyPI) |
| `tests/s3_integration/test_s3_attachment.py` | `conftest.py` fixtures (`aws_s3`, `filesystem_storage`); `odoo.addons.base.models.ir_attachment.IrAttachment` (import target under test) |

### 0.5.3 Detailed Method Transformation Map

**`_file_write(bin_value, checksum)` — Lines 145-157:**

```python
# BEFORE: filesystem only

#### AFTER: S3 branch + original filesystem fallback

```

- S3 branch: compute key as `f"{checksum[:2]}/{checksum}"`, call `self._get_s3_client().put_object(Bucket=bucket, Key=key, Body=bin_value)`, return key as `fname`
- Filesystem branch: original code preserved verbatim in `else` block

**`_file_read(fname, size)` — Lines 133-142:**

```python
# BEFORE: filesystem only

#### AFTER: S3 branch + original filesystem fallback

```

- S3 branch: call `self._get_s3_client().get_object(Bucket=bucket, Key=fname)`, read `Body`, return bytes (or slice if `size` is set)
- On `ClientError`: log warning, return `b''` (matches existing filesystem `OSError` behavior)
- Filesystem branch: original code preserved verbatim in `else` block

**`_file_delete(fname)` — Lines 159-162:**

```python
# BEFORE: filesystem GC marking only

#### AFTER: S3 direct delete + original filesystem fallback

```

- S3 branch: call `self._get_s3_client().delete_object(Bucket=bucket, Key=fname)` — direct deletion, no garbage collection needed for S3
- Filesystem branch: original `_mark_for_gc(fname)` preserved in `else` block

### 0.5.4 One-Phase Execution

The entire refactor is executed by Blitzy in a single phase. There is no phased rollout, no feature flags beyond the `IR_ATTACHMENT_STORAGE` environment variable, and no intermediate states. All files listed in Section 0.5.1 are delivered together as one atomic change set.


## 0.6 Dependency Inventory

### 0.6.1 Key Private and Public Packages

All packages are public, hosted on PyPI. No private dependencies are required.

**New Dependencies to Add:**

| Registry | Package | Version | Purpose |
|----------|---------|---------|---------|
| PyPI | `boto3` | `>=1.34.0` | AWS SDK for Python — provides S3 client for `put_object`, `get_object`, `delete_object`, `create_bucket` operations |
| PyPI | `moto[s3]` | `>=5.0.0` | In-process AWS service mocking — provides `mock_aws` decorator/context for transparent S3 interception during tests |
| PyPI | `pytest` | `>=8.0` | Test framework for running the S3 integration test suite |
| PyPI | `pytest-odoo` | (latest) | Pytest plugin for Odoo test execution compatibility |

**Transitive Dependencies (auto-installed by pip):**

| Package | Pulled By | Purpose |
|---------|-----------|---------|
| `botocore` | `boto3` | Low-level AWS service interface; provides `ClientError` exception class |
| `s3transfer` | `boto3` | S3 transfer management |
| `jmespath` | `boto3` | JSON query language for AWS response parsing |
| `cryptography` | `moto` | Cryptographic operations for mocked service signatures |
| `responses` | `moto` | HTTP request mocking used internally by Moto |
| `xmltodict` | `moto` | XML parsing for S3 API responses |

**Existing Dependencies (unchanged, relevant to context):**

| Registry | Package | Version (Python 3.12) | Relevance |
|----------|---------|----------------------|-----------|
| PyPI | `psycopg2` | `==2.9.9` | PostgreSQL adapter — unchanged, referenced by ir_attachment.py imports |
| PyPI | `Werkzeug` | `==3.0.1` | WSGI toolkit — unchanged, used by ir_attachment.py for safe_join |
| PyPI | `Pillow` | `==10.2.0` | Image processing — unchanged, used by attachment postprocessing |
| PyPI | `lxml` | `==5.2.1` | XML processing — unchanged, general Odoo dependency |

### 0.6.2 Dependency Updates

**Import Refactoring in `ir_attachment.py`:**

Two new import statements are added at the top of the file:

| Import | Line Position | Purpose |
|--------|---------------|---------|
| `import boto3` | After existing `import os` (line 8) | S3 client creation in `_get_s3_client()` |
| `from botocore.exceptions import ClientError` | After `import boto3` | Graceful error handling for missing keys and idempotent bucket creation |

No other files require import updates. The S3 integration is entirely encapsulated within `ir_attachment.py`.

**Requirements.txt Update Pattern:**

The following lines are appended to `requirements.txt`:

```
# S3 storage backend dependencies

boto3>=1.34.0
moto[s3]>=5.0.0
# Test execution

pytest>=8.0
pytest-odoo
```

### 0.6.3 External Reference Updates

**Configuration Files:**

| File | Change |
|------|--------|
| `requirements.txt` | Add `boto3>=1.34.0`, `moto[s3]>=5.0.0`, `pytest>=8.0`, `pytest-odoo` |
| `.gitignore` | Add `.env` entry |
| `.env.example` | New file documenting all environment variables |
| `docker-compose.yml` | New file with PostgreSQL 16 + Odoo 19 services |

**No Changes Required To:**

| File Category | Reason |
|---------------|--------|
| `setup.py` | No new `install_requires` — boto3 is an optional runtime dependency controlled by environment variable |
| `setup.cfg` | No configuration changes needed |
| `ruff.toml` | No linting rule changes needed |
| `.github/` | No CI/CD pipeline changes specified |
| `odoo/addons/base/__manifest__.py` | No module manifest changes — S3 is a server-level configuration, not an addon dependency |


## 0.7 Refactoring Rules

### 0.7.1 Refactoring-Specific Rules

The user has defined explicit rules that govern every aspect of this refactoring. These are non-negotiable constraints:

**Minimal Change Mandate:**

- Make only the changes listed in the System Boundaries section — no additional files, no extra features
- Preserve all existing Odoo code, behavior, and interfaces exactly
- Do not refactor unrelated code
- Do not add features beyond S3 filestore switching
- Do not modify existing tests
- When multiple implementation approaches exist, choose the one requiring the fewest modifications to existing files

**API Contract Preservation:**

- `_file_write(bin_data, checksum)` — signature unchanged; return value remains `fname` (S3 key in S3 mode, filesystem path in filesystem mode)
- `_file_read(fname, bin_size)` — signature unchanged; return value remains `bytes`
- `_file_delete(fname)` — signature unchanged; no return value
- All XML-RPC and JSON-RPC endpoint behaviors unchanged
- `ir.attachment` public API surface unchanged

**Code Documentation Requirement:**

- Every change to `ir_attachment.py` must include an inline comment: `# S3 storage backend — see IR_ATTACHMENT_STORAGE env var.`

**S3 Backend Activation Rule:**

- The S3 backend MUST activate only when `IR_ATTACHMENT_STORAGE=s3` is set
- When unset, existing filesystem behavior is preserved exactly
- The check uses `os.environ.get('IR_ATTACHMENT_STORAGE') == 's3'` — not Odoo's `ir.config_parameter` system

**boto3 Client Instantiation Rule:**

- The boto3 client MUST be instantiated per-call via `_get_s3_client()`
- It MUST NOT be cached at module load time, class level, or instance level
- Each of `_file_write`, `_file_read`, and `_file_delete` MUST call `self._get_s3_client()` at the start of their S3 branch

User Example — `_get_s3_client` implementation:
```python
def _get_s3_client(self):
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    return boto3.client('s3',
        endpoint_url=os.environ.get('AWS_ENDPOINT_URL'),
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID', 'test'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY', 'test'),
        region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
```

### 0.7.2 Special Instructions and Constraints

**Moto Test Fixture Requirements:**

- The `conftest.py` fixture MUST use `monkeypatch` to explicitly set all required environment variables
- MUST use `monkeypatch.delenv('AWS_ENDPOINT_URL', raising=False)` to ensure Moto interception is not bypassed by stale LocalStack values
- MUST start the `mock_aws` context so all boto3 clients created during the test are intercepted
- MUST create the test bucket within the fixture so tests begin with a clean, pre-provisioned state
- All S3 behavior tests MUST use the `aws_s3` fixture
- The filesystem fallback test (scenario 6) MUST use a separate fixture that sets `IR_ATTACHMENT_STORAGE` to an empty string or leaves it unset

User Example — `conftest.py` fixture pattern:
```python
@pytest.fixture
def aws_s3(monkeypatch):
    monkeypatch.setenv('IR_ATTACHMENT_STORAGE', 's3')
    monkeypatch.setenv('AWS_S3_BUCKET', 'odoo-attachments')
    monkeypatch.delenv('AWS_ENDPOINT_URL', raising=False)
    with mock_aws():
        client = boto3.client('s3', region_name='us-east-1')
        client.create_bucket(Bucket='odoo-attachments')
        yield client
```

**Test Execution Constraints:**

- No Docker dependency for tests — Moto is always available in-process
- No health check polling required
- Performance assertion: each S3 operation must complete in ≤500ms (via `time.monotonic()` delta)
- Test command: `pytest tests/s3_integration/ -v`

**Seven Mandatory Test Scenarios — 100% Gate:**

| # | Scenario | Pass Condition |
|---|----------|---------------|
| 1 | Bucket auto-creation | Bucket exists after Odoo init, idempotent on repeat |
| 2 | File write | Object exists in S3 at expected key after `_file_write` |
| 3 | File read integrity | Content retrieved by `_file_read` matches original via SHA1 |
| 4 | File delete | Object absent from S3 after `_file_delete` |
| 5 | Missing file error | `_file_read` on nonexistent key raises graceful error, not unhandled exception |
| 6 | Filesystem fallback | When `IR_ATTACHMENT_STORAGE` unset, existing filesystem path executes (S3 not called) |
| 7 | Moto interception confirmed | After `_file_write`, written object retrievable directly via `aws_s3` fixture client |

**Scenario 7 Rationale (user-specified):** Without this test, it is possible for all other scenarios to pass against a real AWS endpoint while appearing to validate Moto coverage. Scenario 7 proves the fixture client and the client used by `ir_attachment.py` share the same Moto mock context.

### 0.7.3 Environment Variable Rules

| Variable | Dev/Test Default | Production | Critical Notes |
|----------|-----------------|------------|---------------|
| `IR_ATTACHMENT_STORAGE` | `s3` | `s3` | Must equal `'s3'` to activate S3 backend |
| `AWS_S3_BUCKET` | `odoo-attachments` | Real bucket name | Used in all S3 operations |
| `AWS_ENDPOINT_URL` | (unset) | (unset or custom) | MUST be unset during tests to prevent Moto bypass |
| `AWS_ACCESS_KEY_ID` | `test` | Real key | Default `'test'` in `_get_s3_client` |
| `AWS_SECRET_ACCESS_KEY` | `test` | Real secret | Default `'test'` in `_get_s3_client` |
| `AWS_DEFAULT_REGION` | `us-east-1` | Target region | Default `'us-east-1'` in `_get_s3_client` |

**Critical:** `AWS_ENDPOINT_URL` MUST be unset during tests. If set to any value, boto3 will attempt to reach that address instead of being intercepted by Moto, causing test failures. The `conftest.py` fixture explicitly removes this variable before each test.


## 0.8 References

### 0.8.1 Codebase Files and Folders Searched

The following files and folders were systematically searched and analyzed across the codebase to derive the conclusions in this Agent Action Plan:

**Files Retrieved and Analyzed:**

| File Path | Lines | Purpose of Analysis |
|-----------|-------|-------------------|
| `odoo/addons/base/models/ir_attachment.py` | 949 | Primary modification target — full analysis of `IrAttachment` class, `_file_read`, `_file_write`, `_file_delete` method signatures, existing imports, line numbers, and code structure |
| `requirements.txt` | ~80 | Dependency manifest analysis — confirmed no existing boto3/moto entries, identified version-conditional pin patterns for Python 3.10-3.13 |
| `.gitignore` | ~50 | Repository ignore patterns — confirmed no `.env` entry, identified dotfile exclusion section |
| `odoo/addons/base/models/__init__.py` | ~60 | Import chain verification — confirmed `ir_attachment` is imported, no changes needed |
| `odoo/addons/base/tests/test_ir_attachment.py` | 475 | Existing test inventory — cataloged 20 test methods across 2 test classes, confirmed no S3-related tests exist |
| `odoo/release.py` | ~40 | Python version constraints — confirmed `MIN_PY_VERSION = (3, 10)` and Odoo version 19.0 |
| `setup.py` | ~75 | Package configuration — confirmed `python_requires` derived from `MIN_PY_VERSION`, reviewed `install_requires` |
| `setup.cfg` | ~10 | Build configuration — confirmed no pytest configuration present |
| `ruff.toml` | ~15 | Linting configuration — confirmed Python 3.10 target, known-first-party = ["odoo"] |
| `README.md` | ~40 | Project overview — confirmed repository identity and documentation structure |

**Folders Explored:**

| Folder Path | Purpose of Analysis |
|-------------|-------------------|
| `/` (repository root) | Top-level structure discovery — identified all root-level files and directories |
| `odoo/` | Core package structure — identified addons path |
| `odoo/addons/base/models/` | Model file inventory — confirmed ir_attachment.py location |
| `odoo/addons/base/tests/` | Existing test discovery — confirmed test_ir_attachment.py exists with 475 lines |
| `tests/` (root) | Verified directory does not exist — needs creation for S3 integration tests |

**Negative Searches (confirmed absence):**

| Search Target | Result |
|--------------|--------|
| `.blitzyignore` files | None found in repository |
| `docker-compose.yml` | Does not exist at root |
| `.env.example` | Does not exist at root |
| `.env` | Does not exist at root |
| `boto3` / `moto` references in codebase | Zero occurrences — entirely new dependencies |
| `tests/` directory at root | Does not exist — to be created |

### 0.8.2 External Research Sources

| Source | Topic | Key Finding |
|--------|-------|-------------|
| Moto Official Documentation (docs.getmoto.org) | `mock_aws` best practices | Clients must be created inside active `mock_aws` context for interception; module-level clients bypass mocking |
| PyPI — boto3 | Version verification | Latest stable: 1.42.x; `>=1.34.0` specified by user is valid |
| PyPI — moto | Version verification | Latest stable: 5.1.x; `>=5.0.0` specified by user is valid with `mock_aws` unified decorator |
| Moto GitHub (github.com/getmoto/moto) | Fixture patterns | Confirmed `mock_aws` context manager pattern with `yield` for pytest fixtures |

### 0.8.3 Attachments

No attachments were provided for this project. No Figma URLs were specified. The complete specification was provided as inline text in the user's prompt.


