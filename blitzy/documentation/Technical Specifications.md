# Technical Specification

# 0. Agent Action Plan

## 0.1 Intent Clarification

### 0.1.1 Core Refactoring Objective

Based on the prompt, the Blitzy platform understands that the refactoring objective is to **migrate the Odoo 19.0 binary attachment filestore from local filesystem storage to a pluggable S3-compatible backend**, activated exclusively via the environment variable `IR_ATTACHMENT_STORAGE=s3`. The implementation targets three well-defined internal methods within the `ir.attachment` model — `_file_write`, `_file_read`, and `_file_delete` — while preserving 100% functional parity with existing Odoo attachment behavior.

- **Refactoring type:** Tech stack migration (local filesystem → S3-compatible object storage)
- **Target repository:** Same repository (`blitzy-public-samples/blitzy-odoo`, branch `19.0`)
- **Backend activation:** Conditional — S3 backend activates ONLY when `IR_ATTACHMENT_STORAGE=s3` is set in the environment; when unset, the existing filesystem behavior is preserved exactly
- **Validation harness:** LocalStack Community Edition, cloned as a git submodule, provides the S3 emulation layer for dev/test parity
- **Storage key pattern:** `{checksum[:2]}/{checksum}` — identical to the existing filesystem scatter pattern used in `_get_path()` (line 122 of `ir_attachment.py`)

**Refactoring Goals (Enhanced Clarity):**

- Introduce a `boto3`-based S3 client within `ir_attachment.py` that writes, reads, and deletes attachment binary data to/from an S3-compatible bucket
- All S3 calls use `boto3.client('s3', endpoint_url=...)` with configurable endpoint override, making the implementation identical whether targeting LocalStack or real AWS
- Auto-provision the S3 bucket on Odoo startup via an idempotent `create_bucket` call (no-op if the bucket already exists)
- Create a standalone integration test suite (`tests/s3_integration/`) with six mandatory test scenarios validating end-to-end S3 operations against LocalStack
- Register LocalStack as a git submodule at `localstack/` with its CLI and test utilities directly importable

**Implicit Requirements Surfaced:**

- The `_get_path()` method (lines 118–131) creates filesystem directories and performs collision detection. When S3 is active, the `_file_write` method must bypass `_get_path()` for filesystem operations and compute the S3 key independently, but the `store_fname` value must remain in the same `{sha[:2]}/{sha}` format for ORM compatibility
- The `_mark_for_gc()` method (lines 164–175) writes to a filesystem-based spool directory. For S3 mode, `_file_delete` must issue a direct S3 `delete_object` call instead of relying on the garbage collection spool
- The `_to_http_stream()` method (lines 883–929) accesses the local filesystem using `store_fname` to construct a path. When S3 is the active backend, this method's filesystem path resolution (`os.stat`, `os.path.abspath`) will not find the file locally. Per the user's explicit minimal change mandate, this method is OUT OF SCOPE, which means HTTP streaming of S3-stored attachments will fallback to the `_compute_raw → _file_read` ORM path rather than direct filesystem streaming. This is an accepted trade-off documented in the user's system boundaries.
- The `_gc_file_store()` and `_gc_file_store_unsafe()` methods perform filesystem-based garbage collection. These are guarded by `if self._storage() != 'file': return`, so they will naturally no-op when the storage configuration is set to `s3`
- The `_same_content()` method performs filesystem-based collision detection and is only invoked by `_get_path()` — it does not require modification

### 0.1.2 Technical Interpretation

This refactoring translates to the following technical transformation strategy:

**Current Architecture:**
- `ir.attachment` stores binary data to the **local filesystem** via `_file_write`, `_file_read`, and `_file_delete`
- File paths follow the `{sha1[:2]}/{sha1}` scatter pattern under the Odoo filestore directory (`config.filestore(dbname)`)
- The `store_fname` field records the relative path within the filestore
- Garbage collection uses a filesystem spool directory (`checklist/`)

**Target Architecture:**
- `ir.attachment` conditionally routes storage operations to **S3-compatible object storage** when `IR_ATTACHMENT_STORAGE=s3`
- S3 object keys follow the identical `{sha1[:2]}/{sha1}` pattern as S3 key prefixes
- The `store_fname` field continues to store the same key format, maintaining ORM and downstream compatibility
- A lazily-initialized `boto3` S3 client is shared across operations, configured via environment variables
- The S3 bucket is auto-created on first access using an idempotent `create_bucket` call
- When `IR_ATTACHMENT_STORAGE` is unset or set to any value other than `s3`, the existing filesystem path executes unchanged

**Transformation Rules:**

| Aspect | Current (Filesystem) | Target (S3 Mode) |
|--------|---------------------|-------------------|
| Write operation | `open(full_path, 'wb').write(bin_value)` | `s3.put_object(Bucket=bucket, Key=fname, Body=bin_value)` |
| Read operation | `open(full_path, 'rb').read(size)` | `s3.get_object(Bucket=bucket, Key=fname)['Body'].read()` |
| Delete operation | `_mark_for_gc(fname)` via spool | `s3.delete_object(Bucket=bucket, Key=fname)` |
| Key format | `{sha[:2]}/{sha}` (filesystem path) | `{sha[:2]}/{sha}` (S3 object key) |
| Bucket provisioning | N/A | Idempotent `create_bucket` on startup |
| Fallback | N/A | Existing filesystem logic when env var unset |


## 0.2 Source Analysis

### 0.2.1 Comprehensive Source File Discovery

The following exhaustive analysis identifies every file involved in this refactoring, derived from systematic repository inspection of the `blitzy-odoo` repository (branch `19.0`).

**Primary Modification Target:**

| File | Lines | Role | Methods Affected |
|------|-------|------|-----------------|
| `odoo/addons/base/models/ir_attachment.py` | 949 | Core attachment model with filestore abstraction | `_file_write` (L145–157), `_file_read` (L134–142), `_file_delete` (L160–162) |

**Dependency Manifest:**

| File | Role | Change Type |
|------|------|-------------|
| `requirements.txt` | Python dependency manifest with version-conditional pins for Python 3.10–3.13 | Append new packages |

**Repository Configuration Files:**

| File | Exists Today | Change Type |
|------|-------------|-------------|
| `.gitmodules` | Does not exist | Create new |
| `.gitignore` | Exists (30 lines, standard Odoo patterns) | Append entries |

**Files to Create (New):**

| File | Purpose |
|------|---------|
| `tests/s3_integration/__init__.py` | Package initializer for S3 test suite |
| `tests/s3_integration/conftest.py` | LocalStack pytest fixtures and health-gate logic |
| `tests/s3_integration/test_s3_attachment.py` | Six mandatory S3 integration test scenarios |
| `.env.example` | Environment variable documentation with dev/test defaults |
| `docker-compose.yml` | Optional convenience file for full stack startup |

### 0.2.2 Current Structure Mapping

```
blitzy-odoo/  (branch 19.0)
├── .gitignore                                    (exists — to be updated)
├── .gitmodules                                   (does NOT exist — to be created)
├── requirements.txt                              (exists — to be updated)
├── setup.py                                      (exists — NO changes)
├── setup.cfg                                     (exists — NO changes)
├── ruff.toml                                     (exists — NO changes)
├── README.md                                     (exists — NO changes per scope)
├── odoo/
│   ├── release.py                                (MIN_PY_VERSION=(3,10), version_info=(19,0,0,FINAL,0,''))
│   ├── addons/
│   │   └── base/
│   │       ├── models/
│   │       │   ├── ir_attachment.py              (949 lines — PRIMARY TARGET)
│   │       │   ├── assetsbundle.py               (calls _file_delete on L161)
│   │       │   └── [45 other model files]        (NO changes)
│   │       └── tests/
│   │           ├── test_ir_attachment.py          (475 lines — MUST NOT modify)
│   │           └── [80+ other test files]        (NO changes)
│   └── [other core packages]                     (NO changes)
├── addons/
│   └── mail/
│       └── models/
│           └── ir_model.py                       (calls _file_delete on L68 — NO changes)
├── tests/                                        (does NOT exist — to be created)
│   └── s3_integration/                           (NEW test suite directory)
├── localstack/                                   (does NOT exist — git submodule to add)
├── .env.example                                  (does NOT exist — to be created)
└── docker-compose.yml                            (does NOT exist — to be created)
```

### 0.2.3 Cross-Reference: External Callers of Modified Methods

The following files call the `_file_delete` method on `ir.attachment` instances, confirming they will continue working without modification since the method signature is preserved:

- `odoo/addons/base/models/assetsbundle.py` (line 161): `attachments._file_delete(fpath)` — cleans up asset bundle files
- `addons/mail/models/ir_model.py` (line 68): `self.env['ir.attachment']._file_delete(fname)` — removes attachment files during model operations

Both callers pass a `fname` string matching the `{sha[:2]}/{sha}` pattern and expect no return value, which is preserved by the S3 implementation.

### 0.2.4 Existing Attachment Test Coverage

The file `odoo/addons/base/tests/test_ir_attachment.py` (475 lines) contains the existing Odoo attachment test suite with `TransactionCaseWithUserDemo`-based tests covering:
- File storage in DB vs. filesystem modes
- Checksum computation and content hashing
- Attachment security and access control
- File size tracking and base64 encoding

Per the user's explicit mandate, this file **MUST NOT be modified** and all existing tests must continue passing unmodified. The new S3 integration tests are placed in a completely separate directory (`tests/s3_integration/`) to avoid any interference.


## 0.3 Scope Boundaries

### 0.3.1 Exhaustively In Scope

**Source Transformations:**
- `odoo/addons/base/models/ir_attachment.py` — S3 storage backend logic injected into `_file_write`, `_file_read`, `_file_delete` methods only

**New File Creation:**
- `tests/s3_integration/__init__.py` — Package initializer
- `tests/s3_integration/conftest.py` — LocalStack fixtures using `localstack/localstack-core/localstack/testing/`
- `tests/s3_integration/test_s3_attachment.py` — Six mandatory test scenarios
- `.env.example` — Environment variable documentation
- `docker-compose.yml` — Optional convenience orchestration file

**Test Suite:**
- `tests/s3_integration/test_s3_attachment.py` — Six mandatory scenarios:
  - Bucket auto-creation (idempotent on repeat)
  - File write (object exists at expected S3 key after `_file_write`)
  - File read integrity (SHA1 match after `_file_read`)
  - File delete (object absent after `_file_delete`)
  - Missing file graceful error (no unhandled exceptions)
  - Filesystem fallback (S3 not called when `IR_ATTACHMENT_STORAGE` unset)

**Configuration Updates:**
- `requirements.txt` — Append `boto3>=1.34.0` and `localstack-client>=2.0.0`
- `.gitmodules` — Register LocalStack submodule at `localstack/` pointing to `https://github.com/localstack/localstack.git`
- `.gitignore` — Add `.env` and `localstack/` build artifact patterns

**Import Additions:**
- `odoo/addons/base/models/ir_attachment.py` — Add `import os` (already present), `import boto3`, `import logging` (already present) at module top; add conditional S3 client initialization

### 0.3.2 Explicitly Out of Scope

Per the user's **Minimal Change Mandate** and **System Boundaries**:

- **All Odoo addon business logic** outside the three `_file_*` methods in `ir_attachment.py`
- **PostgreSQL schema** — no DDL changes, no ORM field definition changes, no `ir.attachment` column additions
- **`ir.attachment` public API signatures** — `_file_write(bin_data, checksum)`, `_file_read(fname, bin_size)`, `_file_delete(fname)` signatures remain identical
- **Existing Odoo test suite** — zero modifications to `odoo/addons/base/tests/test_ir_attachment.py` or any other existing test file; all must continue passing
- **Frontend/JavaScript layer** — no client-side changes
- **`odoo-bin` entrypoint** — no modifications to server startup script
- **Authentication and session management** — no changes
- **XML-RPC and JSON-RPC endpoint behaviors** — all unchanged
- **`_to_http_stream()` method** — not modified despite its filesystem dependency (accepted trade-off; attachment data accessed via ORM `raw` field which routes through `_file_read`)
- **`_get_path()` method** — not modified; S3 mode computes keys independently within `_file_write`
- **`_mark_for_gc()` method** — not modified; S3 mode performs direct deletion
- **`_gc_file_store()` / `_gc_file_store_unsafe()` methods** — not modified; naturally no-op when `_storage() != 'file'`
- **`_same_content()` method** — not modified; only used by `_get_path()` for filesystem collision detection
- **`setup.py`** — no changes to packaging metadata
- **`README.md`** — no changes per explicit user scope
- **All 300+ addon modules in `addons/`** — no modifications except the incidental compatibility through preserved method signatures
- **`addons/mail/models/ir_model.py`** — no modification; continues calling `_file_delete` with preserved signature
- **`odoo/addons/base/models/assetsbundle.py`** — no modification; continues calling `_file_delete` with preserved signature


## 0.4 Target Design

### 0.4.1 Refactored Structure Planning

The target structure adds a minimal set of new files and a git submodule to the existing repository while modifying only the files explicitly listed in the user's system boundaries. The existing Odoo directory structure remains entirely untouched outside the specified files.

```
Target:
blitzy-odoo/  (branch 19.0)
├── .env.example                                  (NEW — environment variable documentation)
├── .gitignore                                    (UPDATED — add .env, localstack/ artifacts)
├── .gitmodules                                   (NEW — LocalStack submodule registration)
├── docker-compose.yml                            (NEW — optional full-stack convenience)
├── requirements.txt                              (UPDATED — append boto3, localstack-client)
├── localstack/                                   (NEW — git submodule)
│   ├── localstack-core/
│   │   └── localstack/
│   │       └── testing/                          (test utilities import root)
│   └── bin/
│       └── localstack                            (CLI entrypoint)
├── tests/                                        (NEW — top-level test directory)
│   └── s3_integration/                           (NEW — S3 validation test suite)
│       ├── __init__.py                           (NEW — package initializer)
│       ├── conftest.py                           (NEW — LocalStack fixtures, health gate)
│       └── test_s3_attachment.py                 (NEW — 6 mandatory test scenarios)
├── odoo/
│   └── addons/
│       └── base/
│           └── models/
│               └── ir_attachment.py              (UPDATED — S3 backend in 3 methods)
└── [all other files unchanged]
```

### 0.4.2 Web Search Research Conducted

Research was conducted to validate package versions and best practices:

- **boto3 S3 API**: Confirmed `boto3>=1.34.0` supports the `endpoint_url` parameter for S3-compatible backends. The `put_object`, `get_object`, and `delete_object` client methods are the standard low-level API for object CRUD operations. The current latest version is 1.42.53.
- **LocalStack Client**: The `localstack-client` package (latest version 2.11, released January 9, 2026) provides a thin boto3 wrapper that auto-configures endpoints for LocalStack. The `>=2.0.0` floor specified by the user ensures Python 3.12 compatibility.
- **pytest-odoo**: Latest version is 2.1.3 (released May 20, 2025), supporting Python 3.8–3.12 and providing `TransactionCase`/`HttpCase` integration with pytest. This enables running Odoo's existing test suite alongside the new S3 integration tests.
- **LocalStack S3 emulation**: LocalStack Community Edition exposes S3 at `http://localhost:4566` by default. Health check endpoint: `http://localhost:4566/_localstack/health`. The S3 service reports `"s3": "available"` when ready.
- **S3-compatible storage patterns**: The `endpoint_url` override pattern used by boto3 is the standard approach for S3-compatible backends (confirmed across LocalStack, MinIO, and other providers). Using `boto3.client('s3', endpoint_url=...)` makes code portable between LocalStack dev/test and real AWS production.

### 0.4.3 Design Pattern Applications

The S3 integration follows these established design patterns:

- **Strategy Pattern for Storage Backend**: The three `_file_*` methods act as strategy implementations. A conditional check (`os.environ.get('IR_ATTACHMENT_STORAGE') == 's3'`) at the top of each method selects between the S3 path and the existing filesystem path. This avoids introducing new classes or changing the inheritance chain, consistent with the minimal change mandate.

- **Lazy Initialization for S3 Client**: The `boto3` S3 client is initialized lazily on first use and cached at the module level. This avoids import-time side effects and ensures the client is only created when S3 mode is active.

- **Idempotent Provisioning**: The bucket auto-creation uses `create_bucket` wrapped in a `try/except` for `BucketAlreadyOwnedByYou` / `BucketAlreadyExists` exceptions, making it safe to call on every startup without side effects.

- **Environment-Driven Configuration**: All S3 parameters are sourced from environment variables (`AWS_ENDPOINT_URL`, `AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`), enabling identical code to target LocalStack in dev/test and real AWS in production with zero code changes.

- **Graceful Degradation**: When the S3 environment is not configured, the existing filesystem code path executes unchanged, ensuring backward compatibility.

### 0.4.4 Environment Variable Configuration

| Variable | Dev/Test Default | Production | Purpose |
|----------|-----------------|------------|---------|
| `IR_ATTACHMENT_STORAGE` | `s3` | `s3` | Activates S3 backend; unset preserves filesystem |
| `AWS_S3_BUCKET` | `odoo-attachments` | Real bucket name | Target S3 bucket for attachment storage |
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | Unset (uses AWS default) | S3 endpoint override for LocalStack |
| `AWS_ACCESS_KEY_ID` | `test` | Real AWS key | S3 authentication credential |
| `AWS_SECRET_ACCESS_KEY` | `test` | Real AWS secret | S3 authentication secret |
| `AWS_DEFAULT_REGION` | `us-east-1` | Target region | S3 region configuration |


## 0.5 Transformation Mapping

### 0.5.1 File-by-File Transformation Plan

Every target file is mapped to its source file with explicit transformation mode and key changes. No files are left pending or to be discovered.

| Target File | Transformation | Source File | Key Changes |
|------------|---------------|-------------|-------------|
| `odoo/addons/base/models/ir_attachment.py` | UPDATE | `odoo/addons/base/models/ir_attachment.py` | Add `import boto3` and `import botocore.exceptions`; add module-level lazy S3 client helper function; inject S3 conditional branches into `_file_write` (L145–157), `_file_read` (L134–142), and `_file_delete` (L160–162); add idempotent bucket creation function; annotate each change with `# S3 storage backend — see IR_ATTACHMENT_STORAGE env var` |
| `requirements.txt` | UPDATE | `requirements.txt` | Append `boto3>=1.34.0` and `localstack-client>=2.0.0` as new lines at end of file |
| `.gitmodules` | CREATE | — | Register submodule: `[submodule "localstack"]` with `path = localstack`, `url = https://github.com/localstack/localstack.git`, `branch = main` |
| `.gitignore` | UPDATE | `.gitignore` | Append `.env`, `localstack/.venv/`, `localstack/.cache/`, `localstack/volume/` patterns after existing entries |
| `tests/s3_integration/__init__.py` | CREATE | — | Empty package initializer (minimal `# S3 integration test suite`) |
| `tests/s3_integration/conftest.py` | CREATE | `odoo/addons/base/tests/test_ir_attachment.py` | Create pytest fixtures: `s3_client` fixture providing configured boto3 client; `localstack_health_gate` autouse session fixture that checks `http://localhost:4566/_localstack/health` for `s3: available` within 30s or skips with `pytest.skip("LocalStack S3 not available")`; `s3_bucket` fixture auto-provisioning `odoo-attachments` bucket; import test utilities from `localstack/localstack-core/localstack/testing/` |
| `tests/s3_integration/test_s3_attachment.py` | CREATE | `odoo/addons/base/tests/test_ir_attachment.py` | Create 6 test functions: `test_bucket_auto_creation`, `test_file_write`, `test_file_read_integrity`, `test_file_delete`, `test_missing_file_error`, `test_filesystem_fallback`; each test asserts ≤500ms via `time.monotonic()` delta |
| `.env.example` | CREATE | — | Document all 6 environment variables with dev/test defaults in `KEY=value` format with inline comments |
| `docker-compose.yml` | CREATE | — | Define `localstack` service using `localstack/localstack:latest` image, port mapping `4566:4566`, environment `SERVICES=s3`, health check on `/_localstack/health` |

### 0.5.2 Cross-File Dependencies

**Import Statement Updates:**

Only `odoo/addons/base/models/ir_attachment.py` requires new imports. No existing import statements are modified; new imports are added:

- ADD at top of file (after existing imports):
  - `import boto3`
  - `import botocore.exceptions`

**No existing import statements are changed.** The three `_file_*` methods gain conditional S3 logic that branches at the top of each method, falling through to the existing filesystem code when S3 mode is inactive.

**Configuration Updates for New Structure:**

| Configuration Area | File | Change |
|-------------------|------|--------|
| Git submodule | `.gitmodules` | Register `localstack/` → `https://github.com/localstack/localstack.git` |
| Git ignore | `.gitignore` | Add `.env`, `localstack/` build artifacts |
| Python deps | `requirements.txt` | Append `boto3>=1.34.0`, `localstack-client>=2.0.0` |
| Env documentation | `.env.example` | Document all required environment variables |
| Docker orchestration | `docker-compose.yml` | Optional LocalStack service definition |

**Test File Import Corrections:**

The new test files in `tests/s3_integration/` use standard pytest imports and do not import from Odoo's internal test infrastructure. They import directly from:
- `boto3` — S3 client for assertions
- `hashlib` — SHA1 verification
- `time` — Performance assertions
- `os` — Environment variable access
- `localstack.testing` — LocalStack test utilities (from submodule path)

### 0.5.3 Wildcard Patterns

Wildcard patterns are used sparingly and only with trailing patterns:

| Pattern | Purpose |
|---------|---------|
| `tests/s3_integration/*.py` | All new S3 integration test files |
| `odoo/addons/base/models/ir_attachment.py` | Single file, no wildcard needed |

No leading wildcard patterns (e.g., `**/models/**`) are used.

### 0.5.4 One-Phase Execution

The entire refactor is executed by Blitzy in **ONE phase**. All file modifications, creations, and configuration updates occur simultaneously. There is no phased rollout, no incremental migration, and no feature flags beyond the existing `IR_ATTACHMENT_STORAGE` environment variable that governs runtime behavior.

**Execution order within the single phase:**
- Modify `ir_attachment.py` with S3 conditional logic
- Update `requirements.txt` with new dependencies
- Create `.gitmodules` for LocalStack submodule
- Update `.gitignore` with new patterns
- Create `tests/s3_integration/` directory with all test files
- Create `.env.example` with environment variable documentation
- Create `docker-compose.yml` for optional orchestration


## 0.6 Dependency Inventory

### 0.6.1 Key Private and Public Packages

All packages are public (PyPI / public GitHub). No private dependencies are introduced.

| Registry | Package | Version | Purpose |
|----------|---------|---------|---------|
| PyPI | `boto3` | `>=1.34.0` | AWS SDK for Python — S3 client for `put_object`, `get_object`, `delete_object` operations |
| PyPI | `botocore` | (transitive via boto3) | Low-level AWS service interface; provides exception types (`ClientError`, `BucketAlreadyOwnedByYou`) |
| PyPI | `localstack-client` | `>=2.0.0` | Lightweight LocalStack Python client providing boto3 wrapper with auto-endpoint configuration |
| PyPI | `pytest` | `>=8.0` | Test framework for S3 integration test suite execution |
| PyPI | `pytest-odoo` | `>=2.0.0` | pytest plugin for running Odoo tests alongside S3 integration tests |
| PyPI | `s3transfer` | (transitive via boto3) | S3 transfer management library |
| PyPI | `jmespath` | (transitive via boto3) | JSON query language for AWS SDK response parsing |
| GitHub | `localstack/localstack` | `main` branch | Git submodule providing LocalStack Community Edition, CLI (`localstack/bin/localstack`), and test utilities (`localstack/localstack-core/localstack/testing/`) |

**Existing Dependencies (Unchanged):**

The following packages from `requirements.txt` are relevant to this refactor but require NO changes:

| Package | Version (Python 3.12) | Relevance |
|---------|----------------------|-----------|
| `psycopg2` | `==2.9.9` | PostgreSQL driver — unchanged, S3 does not affect DB layer |
| `Werkzeug` | `==3.0.1` | HTTP/WSGI framework — unchanged, used by `_to_http_stream` |
| `requests` | `==2.31.0` | HTTP library — potentially used for LocalStack health checks in `conftest.py` |
| `cryptography` | `==42.0.8` | Cryptographic library — unchanged, no S3 encryption at rest in scope |

### 0.6.2 Dependency Updates

**Import Refactoring:**

Only `odoo/addons/base/models/ir_attachment.py` requires new import additions:

| File | Import Change | Type |
|------|--------------|------|
| `odoo/addons/base/models/ir_attachment.py` | Add `import boto3` | New module-level import |
| `odoo/addons/base/models/ir_attachment.py` | Add `import botocore.exceptions` | New module-level import |
| `tests/s3_integration/conftest.py` | `import boto3`, `import pytest`, `import requests`, `import time`, `import os` | New file imports |
| `tests/s3_integration/test_s3_attachment.py` | `import boto3`, `import hashlib`, `import time`, `import os`, `import pytest` | New file imports |

No existing import statements in any file are modified or removed.

**External Reference Updates:**

| File | Update Type | Details |
|------|------------|---------|
| `requirements.txt` | Append two lines | `boto3>=1.34.0` and `localstack-client>=2.0.0` at end of file |
| `.gitmodules` | Create new | Register `localstack/` submodule pointing to `https://github.com/localstack/localstack.git` |
| `.gitignore` | Append patterns | Add `.env`, `localstack/.venv/`, `localstack/.cache/`, `localstack/volume/` |

**Build and CI Files (Informational — No Changes Required):**

| File | Status | Reason |
|------|--------|--------|
| `setup.py` | No change | `install_requires` does not include boto3; S3 is an optional runtime feature |
| `setup.cfg` | No change | Flake8/setuptools config unaffected |
| `ruff.toml` | No change | Lint config does not need updates for boto3 imports |
| `.github/PULL_REQUEST_TEMPLATE.md` | No change | PR template unaffected |

### 0.6.3 Version Verification

All specified package versions have been verified as valid on PyPI:

- `boto3>=1.34.0`: Version 1.34.0 released on PyPI; current latest is 1.42.53. The `>=1.34.0` floor ensures S3 `endpoint_url` support and modern API compatibility.
- `localstack-client>=2.0.0`: Version 2.0.0 released March 23, 2023; current latest is 2.11 (January 9, 2026). Supports Python 3.8–3.13.
- `pytest>=8.0`: Version 8.0.0 available on PyPI; currently installed at 9.0.2.
- `pytest-odoo>=2.0.0`: Version 2.0.0 available; latest is 2.1.3 (May 20, 2025). Supports Python 3.8–3.12.


## 0.7 Refactoring Rules

### 0.7.1 Refactoring-Specific Rules Explicitly Emphasized by the User

The user's prompt establishes the following non-negotiable rules governing this refactoring:

- **Maintain all public API contracts**: The method signatures `_file_write(bin_data, checksum)`, `_file_read(fname, bin_size)`, and `_file_delete(fname)` remain exactly unchanged. No parameters added, removed, or retyped.
- **Preserve all existing functionality**: When `IR_ATTACHMENT_STORAGE` is unset or set to any value other than `s3`, the existing filesystem behavior executes identically. Zero behavioral changes to the default Odoo experience.
- **Ensure all existing tests continue passing unmodified**: The file `odoo/addons/base/tests/test_ir_attachment.py` (475 lines) and all other existing Odoo tests must pass without any modification. The S3 integration tests are isolated in a separate `tests/s3_integration/` directory.
- **Minimal Change Mandate**: User Example: *"Make only the changes listed in the System Boundaries section above. Preserve all existing Odoo code, behavior, and interfaces exactly. Do not refactor unrelated code. Do not add features beyond S3 filestore switching. Do not modify existing tests. When multiple implementation approaches exist, choose the one requiring the fewest modifications to existing files."*
- **Inline documentation**: User Example: *"Document every change to `ir_attachment.py` with an inline comment: `# S3 storage backend — see IR_ATTACHMENT_STORAGE env var`."*

### 0.7.2 Special Instructions and Constraints

**S3 Backend Activation Logic:**
- The S3 backend MUST activate ONLY when `IR_ATTACHMENT_STORAGE=s3` is set in the environment
- All three `_file_*` methods MUST fall back to existing filesystem logic when `IR_ATTACHMENT_STORAGE != s3`
- The fallback logic must be the EXACT existing implementation — no modifications to the filesystem code path

**boto3 Client Configuration:**
- User-specified configuration pattern:
  ```
  boto3.client('s3',
      endpoint_url=os.environ.get('AWS_ENDPOINT_URL', 'http://localhost:4566'),
      aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
      aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
      region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
  ```
- The `endpoint_url` override makes the implementation portable between LocalStack and real AWS

**S3 Storage Interface Contracts:**
- `_file_write(bin_data, checksum)` → writes to S3 with key: `{checksum[:2]}/{checksum}`
- `_file_read(fname, bin_size)` → retrieves from S3 by key
- `_file_delete(fname)` → deletes from S3 by key
- Bucket auto-created on Odoo startup via idempotent `create_bucket` (no-op if exists)

**Validation Requirements:**
- All 6 test scenarios in `tests/s3_integration/test_s3_attachment.py` MUST pass (100% gate)
- `conftest.py` MUST call LocalStack health endpoint before any test runs
- If `http://localhost:4566/_localstack/health` does not return `s3: available` within 30 seconds, test suite MUST exit with `pytest.skip("LocalStack S3 not available")` — no hangs
- Each S3 operation in tests MUST complete in ≤500ms (assert via `time.monotonic()` delta)

**Performance Constraint:**
- S3 operation latency ≤500ms per call against local LocalStack container

**End-to-End Setup Constraint:**
- `git submodule update --init --recursive` + `localstack/bin/localstack start -d` + `pytest tests/s3_integration/` must execute end-to-end from a clean clone in ≤5 minutes
- LocalStack S3 bucket auto-provisioned on Odoo startup — zero manual setup steps

**Build Prerequisites:**
- Docker (for LocalStack container)
- Python 3.12
- git ≥2.13 (submodule support)

### 0.7.3 Immutable Interface Guarantees

| Interface | Contract | Enforcement |
|-----------|----------|-------------|
| `_file_write(bin_data, checksum)` | Signature unchanged; returns `fname` string | S3 mode returns same `{sha[:2]}/{sha}` key format |
| `_file_read(fname, bin_size)` | Signature unchanged; returns `bytes` | S3 mode returns binary content matching filesystem semantics |
| `_file_delete(fname)` | Signature unchanged; returns `None` | S3 mode deletes object directly (no GC spool) |
| XML-RPC endpoints | All behaviors unchanged | No RPC layer modifications |
| JSON-RPC endpoints | All behaviors unchanged | No RPC layer modifications |
| `ir.attachment` ORM fields | All field definitions unchanged | No schema changes |
| `store_fname` field format | `{sha[:2]}/{sha}` pattern preserved | S3 keys use identical format |


## 0.8 References

### 0.8.1 Repository Files and Folders Searched

The following files and folders were inspected during analysis to derive the conclusions documented in this Agent Action Plan:

**Files Retrieved and Analyzed:**

| File Path | Purpose of Inspection |
|-----------|----------------------|
| `requirements.txt` | Full read — identified all 98 Python dependencies with version-conditional pins for Python 3.10–3.13; confirmed `boto3` and `localstack-client` are NOT currently listed |
| `setup.py` | Full read — confirmed `install_requires` list, `python_requires` computed from `MIN_PY_VERSION`, `tests_require=['freezegun']`; no boto3 dependency |
| `odoo/addons/base/models/ir_attachment.py` | Full read (949 lines) — analyzed all methods: `_file_write` (L145–157), `_file_read` (L134–142), `_file_delete` (L160–162), `_get_path` (L118–131), `_mark_for_gc` (L164–175), `_gc_file_store` (L177–207), `_gc_file_store_unsafe` (L209–239), `_compute_datas` (L241–250), `_compute_raw` (L252–258), `_set_attachment_data` (L266–291), `_get_datas_related_values` (L293–309), `_to_http_stream` (L883–929), and all field definitions |
| `odoo/release.py` | Partial read — extracted `MIN_PY_VERSION = (3, 10)`, `version_info = (19, 0, 0, FINAL, 0, '')`, `series = '19.0'` |
| `.gitignore` | Full read (30 lines) — confirmed existing patterns; identified insertion point for new entries |

**Folders Explored:**

| Folder Path | Depth | Key Findings |
|-------------|-------|--------------|
| `/` (repository root) | Level 0 | 14 top-level children: `.weblate.json`, `CONTRIBUTING.md`, `LICENSE`, `README.md`, `SECURITY.md`, `requirements.txt`, `ruff.toml`, `setup.cfg`, `setup.py`, `doc/`, `addons/`, `odoo/`, `.github/`, `setup/`, `debian/` |
| `odoo/` | Level 1 | Core package: `__main__.py`, `exceptions.py`, `http.py`, `release.py`, `sql_db.py`, plus subpackages: `addons/`, `orm/`, `osv/`, `service/`, `tests/`, `tools/`, `_monkeypatches/`, `upgrade_code/`, `api/`, `cli/`, `fields/`, `models/`, `modules/` |
| `odoo/addons/` | Level 2 | Core addons: `base/` plus 23 test-oriented addons (`test_assetsbundle`, `test_http`, `test_orm`, etc.) |
| `odoo/addons/base/` | Level 3 | Standard addon layout: `models/`, `report/`, `security/`, `static/`, `tests/`, `data/`, `views/`, `wizard/` |
| `odoo/addons/base/models/` | Level 4 | 48 model files including `ir_attachment.py`, `assetsbundle.py`, `ir_actions.py`, `ir_http.py`, `res_users.py` |
| `odoo/addons/base/tests/` | Level 4 | 80+ test files including `test_ir_attachment.py` (475 lines), `common.py`, plus subfolders: `config/`, `file_template/`, `split_table/`, `test_install_addons/` |

**Cross-Codebase Searches Performed:**

| Search Query | Tool | Results |
|-------------|------|---------|
| `_file_write`, `_file_read`, `_file_delete` references across `addons/` and `odoo/` | bash grep | Found 2 external callers: `addons/mail/models/ir_model.py:68` and `odoo/addons/base/models/assetsbundle.py:161` |
| `boto3`, `aws_`, `s3_`, `S3`, `localstack` references | bash grep | No existing references found — confirms clean integration point |
| `store_fname`, `_filestore`, `_storage` references in `ir_attachment.py` | bash grep | Mapped all 30+ internal references to understand data flow |
| `.blitzyignore` files | bash find | None found in repository |

### 0.8.2 External References

| Resource | URL | Relevance |
|----------|-----|-----------|
| boto3 S3 API Documentation | `https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html` | Verified `put_object`, `get_object`, `delete_object`, `create_bucket` API signatures |
| localstack-client PyPI | `https://pypi.org/project/localstack-client/` | Confirmed latest version 2.11, Python 3.8–3.13 support |
| pytest-odoo PyPI | `https://pypi.org/project/pytest-odoo/` | Confirmed latest version 2.1.3, Odoo test harness integration |
| LocalStack GitHub | `https://github.com/localstack/localstack` | Source for git submodule, Community Edition S3 emulation |
| LocalStack Python Client GitHub | `https://github.com/localstack/localstack-python-client` | boto3 wrapper for endpoint auto-configuration |

### 0.8.3 Technical Specification Sections Reviewed

| Section | Key Information Extracted |
|---------|-------------------------|
| 1.1 Executive Summary | Odoo 19.0, LGPL-3 license, modular ERP platform with 300+ addons |
| 3.1 Programming Languages | Python 3.10–3.13 support range, MIN_PY_VERSION=(3,10), ORM architecture details |

### 0.8.4 Attachments

No user-provided attachments were included with this project. No Figma URLs or design files were referenced.


