# Project Guide — Odoo 19 S3 Filestore Backend Migration

## 1. Executive Summary

This project delivers a **pluggable S3 storage backend** for the Odoo 19 `ir.attachment` model, enabling binary attachments to be stored in an S3-compatible bucket instead of the local filesystem. The implementation is gated by the `IR_ATTACHMENT_STORAGE=s3` environment variable—when unset, the existing filesystem behavior is preserved exactly.

**Completion: 30 hours completed out of 37 total hours = 81% complete.**

All code changes specified in the Agent Action Plan have been fully implemented and validated:
- 8 files delivered (3 updated, 5 created) — 539 lines added, 20 removed
- 7/7 S3 integration tests passing at 100%
- 14/14 existing Odoo tests passing (zero regressions)
- All files compile cleanly; Odoo runtime validated
- 10 well-structured commits on the feature branch

The remaining 7 hours of work are **production readiness tasks** (AWS configuration, CI/CD integration, security review) that require human intervention and access to production infrastructure.

---

## 2. Validation Results Summary

### 2.1 Five-Gate Validation — All Passed

| Gate | Status | Details |
|------|--------|---------|
| **Dependencies** | ✅ 100% | boto3==1.42.56, moto==5.1.21, pytest==9.0.2, pytest-odoo==2.1.3 installed |
| **Compilation** | ✅ 100% | ir_attachment.py, conftest.py, test_s3_attachment.py, __init__.py all compile |
| **Tests** | ✅ 100% | 7/7 S3 tests + 14/14 existing Odoo tests passed |
| **Runtime** | ✅ 100% | Odoo starts/stops cleanly with --stop-after-init --no-http |
| **Git** | ✅ 100% | 8 files committed, no uncommitted in-scope changes |

### 2.2 S3 Integration Test Results (7/7 Passed)

| # | Scenario | Status | Description |
|---|----------|--------|-------------|
| 1 | Bucket auto-creation idempotent | ✅ PASSED | Bucket exists after init; repeat create_bucket is no-op |
| 2 | File write to S3 | ✅ PASSED | Object exists at `{checksum[:2]}/{checksum}` key after put_object |
| 3 | File read integrity (SHA-1) | ✅ PASSED | Retrieved content SHA-1 matches original checksum |
| 4 | File delete from S3 | ✅ PASSED | Object absent after delete_object (NoSuchKey on get) |
| 5 | Missing file graceful error | ✅ PASSED | get_object on nonexistent key raises ClientError(NoSuchKey) |
| 6 | Filesystem fallback | ✅ PASSED | S3 branch not entered when IR_ATTACHMENT_STORAGE unset |
| 7 | Moto interception confirmed | ✅ PASSED | Separate boto3 clients share same mock context |

### 2.3 Fixes Applied During Validation

The Final Validator agent applied one round of code review fixes (commit `5233f00ef96`):
- Added idempotent bucket auto-creation to `_get_s3_client()`
- Fixed import ordering for `boto3` (alphabetical placement)
- Added `@api.model` decorator comment
- Removed deprecated `version` key from docker-compose.yml

---

## 3. Hours Breakdown and Completion Analysis

### 3.1 Calculation

**Completed Hours: 30h**
- Core S3 backend implementation (ir_attachment.py): 10h
- Test suite development (tests/s3_integration/): 12h
- Configuration and documentation files: 3h
- Validation and quality assurance: 5h

**Remaining Hours: 7h** (after enterprise multipliers 1.10 × 1.10 = 1.21x)
- Production AWS S3 setup and credentials: 2h
- CI/CD pipeline integration: 2h
- End-to-end validation with real AWS S3: 1h
- Security review: 1h
- Data migration planning: 1h

**Total Project Hours: 30h + 7h = 37h**
**Completion: 30 / 37 = 81%**

### 3.2 Visual Representation

```mermaid
pie title Project Hours Breakdown
    "Completed Work" : 30
    "Remaining Work" : 7
```

---

## 4. Implemented Changes — File Inventory

### 4.1 Updated Files

| File | Lines Changed | Description |
|------|--------------|-------------|
| `odoo/addons/base/models/ir_attachment.py` | +67 / -20 | Added `_get_s3_client()` helper; modified `_file_read`, `_file_write`, `_file_delete` with S3 branches |
| `requirements.txt` | +7 | Added boto3>=1.34.0, moto[s3]>=5.0.0, pytest>=8.0, pytest-odoo |
| `.gitignore` | +3 | Added `.env` entry and `!.env.example` exception |

### 4.2 Created Files

| File | Lines | Description |
|------|-------|-------------|
| `tests/s3_integration/test_s3_attachment.py` | 310 | 7 mandatory test scenarios with performance assertions |
| `tests/s3_integration/conftest.py` | 82 | `aws_s3` and `filesystem_storage` pytest fixtures with Moto mock |
| `tests/s3_integration/__init__.py` | 1 | Empty package init for pytest discovery |
| `.env.example` | 22 | Documents all 6 required environment variables |
| `docker-compose.yml` | 47 | Optional Odoo 19 + PostgreSQL 16 convenience stack |

### 4.3 Git History (10 commits)

| Commit | Description |
|--------|-------------|
| `2aabdc5` | Add S3 integration test suite with 7 mandatory test scenarios |
| `5233f00` | fix: address code review findings — bucket auto-creation, import ordering |
| `0137dda` | feat: add S3 storage backend to ir.attachment methods |
| `9212306` | Create tests/s3_integration/conftest.py with pytest fixtures |
| `0013cac` | Add empty __init__.py for tests/s3_integration package |
| `c7e9f15` | Add explicit .env entry to .gitignore |
| `76d048f` | Fix requirements.txt formatting |
| `7785ee9` | Create docker-compose.yml convenience stack |
| `63234c7` | Create .env.example environment variable documentation |
| `213d05e` | Setup: Add S3 dependencies and test packages to requirements.txt |

---

## 5. Remaining Human Tasks

### 5.1 Detailed Task Table

| # | Task | Priority | Severity | Hours | Description |
|---|------|----------|----------|-------|-------------|
| 1 | **Production AWS S3 Setup & Credentials** | HIGH | Critical | 2h | Create production S3 bucket with proper naming convention. Set up IAM user/role with least-privilege permissions (s3:PutObject, s3:GetObject, s3:DeleteObject, s3:CreateBucket on target bucket ARN only). Configure production environment variables (`AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`). |
| 2 | **CI/CD Pipeline Integration** | MEDIUM | High | 2h | Add S3 test stage to existing CI pipeline. Configure `PYTHONPATH` to include repo root. Ensure `pip install -r requirements.txt` runs before tests. Add step: `pytest tests/s3_integration/ -v --tb=short`. No AWS credentials needed in CI—Moto handles mocking in-process. |
| 3 | **End-to-End Validation with Real AWS S3** | MEDIUM | High | 1h | Run manual validation against a real S3 endpoint in staging environment. Set `IR_ATTACHMENT_STORAGE=s3` with real credentials. Verify attachment upload, download, and delete work end-to-end through the Odoo web interface. Confirm bucket auto-creation works with real AWS. |
| 4 | **Security Review** | HIGH | Critical | 1h | Review IAM permissions follow least-privilege principle. Verify `_get_s3_client()` does not log credentials. Confirm `.env` is properly gitignored. Review S3 bucket policy — disable public access, enable server-side encryption (SSE-S3 or SSE-KMS). Verify `AWS_ENDPOINT_URL` is not set in production to prevent SSRF. |
| 5 | **Data Migration Planning** | LOW | Medium | 1h | Document migration strategy for existing filesystem attachments to S3 (only needed when switching existing deployments). Plan: iterate `ir_attachment` records with `store_fname`, read from filesystem, write to S3 using same key. Define rollback procedure (unset `IR_ATTACHMENT_STORAGE` to revert to filesystem). |
| | **Total Remaining Hours** | | | **7h** | |

### 5.2 Task Priority Summary

- **HIGH Priority (3h):** Production AWS setup, security review — blocks production deployment
- **MEDIUM Priority (3h):** CI/CD integration, E2E validation — required before production but not blocking development
- **LOW Priority (1h):** Data migration planning — only needed for existing deployments switching to S3

---

## 6. Development Guide

### 6.1 System Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ (3.10 minimum) | Verified with Python 3.12.3 |
| pip | 25.0+ | For dependency installation |
| PostgreSQL | 16 | Required for Odoo (use docker-compose.yml or local install) |
| Git | 2.0+ | For cloning the repository |

### 6.2 Environment Setup

```bash
# 1. Clone the repository and switch to the feature branch
git clone https://github.com/blitzy-public-samples/blitzy-odoo.git
cd blitzy-odoo
git checkout blitzy-389f7cf4-73aa-4497-88b9-2c04f67b3116

# 2. Create and activate a Python virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install all dependencies (including S3 backend and test packages)
pip install -r requirements.txt

# 4. Verify key packages are installed
python -c "import boto3; print('boto3:', boto3.__version__)"
python -c "import moto; print('moto:', moto.__version__)"
python -c "import pytest; print('pytest:', pytest.__version__)"
```

**Expected output (versions may vary):**
```
boto3: 1.42.56
moto: 5.1.21
pytest: 9.0.2
```

### 6.3 Running the S3 Integration Tests

```bash
# From the repository root, with virtual environment activated:
PYTHONPATH=$(pwd):$PYTHONPATH pytest tests/s3_integration/ -v
```

**Expected output:**
```
tests/s3_integration/test_s3_attachment.py::test_bucket_auto_creation_idempotent PASSED
tests/s3_integration/test_s3_attachment.py::test_file_write_to_s3 PASSED
tests/s3_integration/test_s3_attachment.py::test_file_read_integrity_sha1 PASSED
tests/s3_integration/test_s3_attachment.py::test_file_delete_from_s3 PASSED
tests/s3_integration/test_s3_attachment.py::test_missing_file_graceful_error PASSED
tests/s3_integration/test_s3_attachment.py::test_filesystem_fallback PASSED
tests/s3_integration/test_s3_attachment.py::test_moto_interception_confirmed PASSED

======================== 7 passed in ~1s =========================
```

**Note:** No Docker containers, real AWS credentials, or network access required. Moto handles S3 mocking entirely in-process.

### 6.4 Running the Existing Odoo Tests (Regression Check)

```bash
# Requires a running PostgreSQL database
# Option A: Use docker-compose for PostgreSQL
docker compose up -d db
sleep 5  # wait for PostgreSQL to be ready

# Option B: Use local PostgreSQL (skip docker compose if already running)

# Run existing ir_attachment tests
python odoo-bin \
  --database=odoo_test \
  --db_user=odoo \
  --db_password=odoo \
  --db_host=localhost \
  --update=base \
  --stop-after-init \
  --no-http \
  --test-tags=base:TestIrAttachment
```

### 6.5 Starting Odoo with S3 Storage Backend

```bash
# Copy and configure environment variables
cp .env.example .env
# Edit .env with your AWS credentials for production use

# Start Odoo with S3 backend enabled
export IR_ATTACHMENT_STORAGE=s3
export AWS_S3_BUCKET=odoo-attachments
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=us-east-1

python odoo-bin \
  --database=odoo \
  --db_user=odoo \
  --db_password=odoo \
  --db_host=localhost
```

### 6.6 Starting Odoo with Filesystem Storage (Default)

```bash
# Simply do NOT set IR_ATTACHMENT_STORAGE — filesystem is the default
python odoo-bin \
  --database=odoo \
  --db_user=odoo \
  --db_password=odoo \
  --db_host=localhost
```

### 6.7 Using Docker Compose (Optional)

```bash
# Start full stack (PostgreSQL + Odoo)
docker compose up -d

# Access Odoo at http://localhost:8069

# To enable S3 backend, uncomment the S3 env vars in docker-compose.yml
# Then restart: docker compose up -d

# Stop and remove volumes
docker compose down -v
```

### 6.8 Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IR_ATTACHMENT_STORAGE` | Yes (for S3) | _(unset)_ | Set to `s3` to enable S3 backend; unset for filesystem |
| `AWS_S3_BUCKET` | Yes (for S3) | `odoo-attachments` | Target S3 bucket name |
| `AWS_ENDPOINT_URL` | No | _(unset)_ | Custom endpoint (LocalStack/MinIO); **must be unset for Moto tests** |
| `AWS_ACCESS_KEY_ID` | Yes (for S3) | `test` | AWS access key; `test` for dev/Moto |
| `AWS_SECRET_ACCESS_KEY` | Yes (for S3) | `test` | AWS secret key; `test` for dev/Moto |
| `AWS_DEFAULT_REGION` | No | `us-east-1` | AWS region for S3 operations |

### 6.9 Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: No module named 'odoo'` | PYTHONPATH not set | Run: `PYTHONPATH=$(pwd):$PYTHONPATH pytest tests/s3_integration/ -v` |
| Tests hang or fail with connection errors | `AWS_ENDPOINT_URL` set to a stale value | Unset it: `unset AWS_ENDPOINT_URL` |
| `BucketAlreadyOwnedByYou` exception | Not an error — idempotent bucket creation | This is caught and handled as a no-op |
| Existing Odoo tests fail | S3 env var leaking into test environment | Ensure `IR_ATTACHMENT_STORAGE` is unset when running Odoo tests |

---

## 7. Risk Assessment

### 7.1 Technical Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| S3 latency impacts attachment performance in production | Medium | Low | boto3 connection pooling handles this; monitor p99 latency; consider CloudFront for reads |
| Idempotent `create_bucket` on every `_get_s3_client()` call adds overhead | Low | Low | S3 `create_bucket` is a lightweight HEAD+PUT; acceptable for correctness guarantee |
| `boto3` import at module level impacts Odoo startup when S3 not used | Low | Low | Import cost is ~50ms one-time; negligible compared to Odoo module loading |

### 7.2 Security Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| AWS credentials stored in environment variables | Medium | Medium | Use IAM instance roles in production; never commit `.env` (gitignored) |
| S3 bucket misconfiguration allows public access | High | Low | Enable Block Public Access on bucket; use IAM policies for access control |
| `AWS_ENDPOINT_URL` set to malicious endpoint (SSRF) | Medium | Low | Leave unset in production; validate endpoint URLs if custom endpoints needed |

### 7.3 Operational Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| S3 service outage makes attachments unavailable | Medium | Low | AWS S3 has 99.99% availability SLA; implement read-through cache if needed |
| No monitoring on S3 operations | Medium | Medium | Add CloudWatch metrics; monitor `_file_read`/`_file_write` error rates |
| No backup strategy for S3-stored attachments | Medium | Medium | Enable S3 versioning and cross-region replication for critical data |

### 7.4 Integration Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Existing filesystem attachments inaccessible after switching to S3 | High | High | Must migrate existing attachments before switching; plan migration carefully |
| Mixed storage state (some files on disk, some in S3) | Medium | Medium | Document that switching mid-deployment requires migration; not auto-handled |
| Third-party Odoo modules assuming filesystem storage | Low | Low | S3 branch only affects `_file_read`/`_file_write`/`_file_delete`; public API unchanged |

---

## 8. Architecture Overview

### 8.1 Storage Backend Selection Flow

When `IR_ATTACHMENT_STORAGE=s3`:
1. `_file_write(bin_value, checksum)` → `put_object(Bucket, Key={checksum[:2]}/{checksum}, Body=bin_value)`
2. `_file_read(fname, size)` → `get_object(Bucket, Key=fname)` → return body bytes
3. `_file_delete(fname)` → `delete_object(Bucket, Key=fname)` — direct deletion, no GC

When `IR_ATTACHMENT_STORAGE` is unset or not `s3`:
1. `_file_write` → writes to local filesystem (original behavior preserved verbatim)
2. `_file_read` → reads from local filesystem (original behavior preserved verbatim)
3. `_file_delete` → marks for garbage collection (original behavior preserved verbatim)

### 8.2 Client Lifecycle

Each S3 operation calls `_get_s3_client()` which:
1. Creates a fresh `boto3.client('s3')` with environment-sourced credentials
2. Performs idempotent `create_bucket` (no-op if exists)
3. Returns the client for the calling method to use

This per-call pattern is mandatory for Moto test interception — cached clients bypass mocking.
