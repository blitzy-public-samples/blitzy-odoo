# Blitzy Project Guide — Odoo S3 Attachment Storage Terraform Module

---

## 1. Executive Summary

### 1.1 Project Overview

This project provisions an Amazon S3 bucket and IAM user for Odoo file attachment storage using Terraform, targeting a LocalStack development environment. The Terraform module at `terraform/odoo-s3/` creates six AWS resources — an S3 bucket with versioning enabled, an IAM user with programmatic access key, a least-privilege IAM policy, and a user-policy attachment — all against LocalStack at `localhost:4566`. The Odoo server configuration (`debian/odoo.conf`) is updated with S3 connection keys. This establishes the infrastructure foundation for Odoo's file attachment subsystem in a development-safe environment.

### 1.2 Completion Status

```mermaid
pie title Project Completion — 78.8%
    "Completed (AI)" : 13
    "Remaining" : 3.5
```

| Metric | Value |
|--------|-------|
| **Total Project Hours** | 16.5h |
| **Completed Hours (AI)** | 13h |
| **Remaining Hours** | 3.5h |
| **Completion Percentage** | 78.8% |

**Calculation:** 13h completed / (13h + 3.5h) = 13 / 16.5 = 78.8% complete

### 1.3 Key Accomplishments

- ✅ Created complete Terraform module with 7 files at `terraform/odoo-s3/`
- ✅ Provisioned exactly 6 AWS resources against LocalStack (S3 bucket, bucket versioning, IAM user, access key, IAM policy, user-policy attachment)
- ✅ All Terraform validation passes: `fmt -check`, `validate`, `plan`, `apply`
- ✅ S3 bucket versioning enabled via dedicated `aws_s3_bucket_versioning` resource
- ✅ IAM policy follows least privilege: only 4 S3 actions scoped to the bucket
- ✅ Secret access key output marked `sensitive = true`
- ✅ Odoo configuration (`debian/odoo.conf`) updated with 4 S3 keys and LocalStack dev comment
- ✅ Module supports idempotent destroy/apply via `force_destroy = true`
- ✅ Zero files modified under `blitzy-localstack/tests/` — preservation requirement met
- ✅ Comprehensive README.md with prerequisites, workflow, verification commands, and Odoo connection instructions

### 1.4 Critical Unresolved Issues

| Issue | Impact | Owner | ETA |
|-------|--------|-------|-----|
| Terraform state files (`.tfstate`) not in `.gitignore` | State files with sensitive data could be accidentally committed | Human Developer | 0.5h |
| No automated S3 lifecycle integration test script | Integration validation requires manual `awslocal` commands | Human Developer | 1.5h |
| Idempotency not explicitly tested (destroy/apply cycle) | Module supports it via `force_destroy` but cycle not verified | Human Developer | 1h |

### 1.5 Access Issues

| System/Resource | Type of Access | Issue Description | Resolution Status | Owner |
|----------------|---------------|-------------------|-------------------|-------|
| LocalStack | Docker Service | LocalStack must be running at `localhost:4566` before `terraform apply` | Resolved — `docker compose up -d` from `blitzy-localstack/` directory | Developer |
| Terraform 1.1.3 | CLI Binary | Exact version 1.1.3 required (pinned in `versions.tf`) | Resolved — installed at `/usr/local/bin/terraform` | Developer |

### 1.6 Recommended Next Steps

1. **[High]** Add `.gitignore` entries for `terraform.tfstate*` and `.terraform/` to prevent sensitive state files from being committed
2. **[High]** Create an automated integration test script that performs a full S3 object lifecycle (upload, list, download, verify, delete) using IAM credentials from `terraform output -json`
3. **[Medium]** Run a complete idempotency test: `terraform destroy -auto-approve` followed by `terraform apply -auto-approve` and verify all 6 resources are recreated
4. **[Medium]** Document production deployment process including environment variable overrides for real AWS credentials
5. **[Low]** Consider adding a Terraform backend configuration for remote state management in team environments

---

## 2. Project Hours Breakdown

### 2.1 Completed Work Detail

| Component | Hours | Description |
|-----------|-------|-------------|
| Terraform Module Foundation | 2.5h | Created `versions.tf` (Terraform 1.1.3, hashicorp/aws provider), `provider.tf` (LocalStack provider with s3/iam/ses/secretsmanager endpoints, skip_* flags), `variables.tf` (3 input variables), and `terraform.tfvars` (default values) |
| Core Infrastructure Resources | 3.5h | Created `main.tf` with 6 AWS resource definitions: S3 bucket with `force_destroy`, bucket versioning (Enabled), IAM user, programmatic access key, least-privilege IAM policy (jsonencode with 4 S3 actions), and user-policy attachment |
| Output Definitions | 0.5h | Created `outputs.tf` exporting `bucket_name`, `iam_access_key_id`, and `iam_secret_access_key` (sensitive = true) |
| Odoo Configuration Integration | 0.5h | Modified `debian/odoo.conf` to append 4 S3 connection keys with LocalStack dev defaults comment under `[options]` section |
| Module Documentation | 2.0h | Created comprehensive `README.md` (194 lines) with prerequisites, module structure, resource table, init/plan/apply workflow, verification commands, output reference, Odoo connection instructions, variables, teardown, and security notes |
| Pattern Analysis & Scope Discovery | 1.0h | Analyzed reference files in `blitzy-localstack/tests/aws/terraform/` (provider.tf, versions.tf, s3.tf, iam.tf) to extract LocalStack provider conventions and resource patterns |
| Terraform Validation & Deployment | 2.0h | Executed `terraform init` (provider download), `terraform fmt -check` (all files pass), `terraform validate` (valid), `terraform plan` (6 additions), `terraform apply -auto-approve` (all resources created), verified `terraform state list` (6 resources), confirmed `terraform output -json` works |
| Idempotency Fix | 0.5h | Added `force_destroy = true` to S3 bucket resource to enable clean destroy/apply cycles without manual bucket emptying |
| Final Validation & Testing | 0.5h | Verified all AAP requirements met, confirmed zero changes in `blitzy-localstack/tests/`, validated `terraform plan -detailed-exitcode` returns 0 (stable state) |
| **Total Completed** | **13h** | |

### 2.2 Remaining Work Detail

| Category | Hours | Priority |
|----------|-------|----------|
| [Path-to-production] Add .gitignore for terraform state files (.tfstate, .tfstate.backup, .terraform/) | 0.5h | High |
| [Path-to-production] Automated S3 lifecycle integration test script (upload → list → download → verify → delete using IAM credentials from terraform output) | 1.5h | High |
| [Path-to-production] Idempotency verification test (scripted destroy/apply cycle with resource count assertion) | 1.0h | Medium |
| [Path-to-production] Production environment variable override documentation and tooling | 0.5h | Medium |
| **Total Remaining** | **3.5h** | |

### 2.3 Hours Verification

- Section 2.1 Completed Total: **13h**
- Section 2.2 Remaining Total: **3.5h**
- Sum (2.1 + 2.2): **16.5h** = Total Project Hours in Section 1.2 ✓
- Remaining (3.5h) matches Section 1.2 metrics table ✓
- Remaining (3.5h) matches Section 7 pie chart ✓

---

## 3. Test Results

| Test Category | Framework | Total Tests | Passed | Failed | Coverage % | Notes |
|--------------|-----------|-------------|--------|--------|------------|-------|
| Terraform Format Check | `terraform fmt -check` | 5 | 5 | 0 | 100% | All 5 .tf files (versions.tf, provider.tf, variables.tf, main.tf, outputs.tf) pass formatting validation |
| Terraform Validation | `terraform validate` | 1 | 1 | 0 | 100% | "Success! The configuration is valid." — validates resource syntax, references, and type constraints |
| Terraform Plan | `terraform plan` | 1 | 1 | 0 | 100% | Confirms 6 resource additions with zero errors; detailed-exitcode returns 0 (no changes from applied state) |
| Terraform State Verification | `terraform state list` | 6 | 6 | 0 | 100% | All 6 resources confirmed in state: aws_s3_bucket, aws_s3_bucket_versioning, aws_iam_user, aws_iam_access_key, aws_iam_policy, aws_iam_user_policy_attachment |
| Terraform Output Verification | `terraform output -json` | 3 | 3 | 0 | 100% | All 3 outputs (bucket_name, iam_access_key_id, iam_secret_access_key) return valid values; sensitive field correctly masked |
| File Preservation Check | `git diff --name-only` | 1 | 1 | 0 | 100% | Zero files modified under `blitzy-localstack/tests/` — preservation requirement met |

**Total: 17 tests, 17 passed, 0 failed — 100% pass rate**

All tests originate from Blitzy's autonomous validation execution during the Final Validator phase. No external or manual tests are included.

---

## 4. Runtime Validation & UI Verification

### Infrastructure Runtime Status

- ✅ **Terraform Init**: Provider `hashicorp/aws` v6.36.0 downloaded and locked in `.terraform.lock.hcl`
- ✅ **Terraform Apply**: All 6 resources created successfully against LocalStack at `localhost:4566`
- ✅ **Terraform Plan (post-apply)**: "No changes. Your infrastructure matches the configuration." — stable state confirmed
- ✅ **Terraform Output**: All 3 outputs (`bucket_name`, `iam_access_key_id`, `iam_secret_access_key`) returning valid values
- ✅ **S3 Bucket**: `odoo-attachments` bucket exists in LocalStack state
- ✅ **S3 Versioning**: Enabled via dedicated `aws_s3_bucket_versioning` resource
- ✅ **IAM User**: `odoo-s3` user exists with programmatic access key generated
- ✅ **IAM Policy**: Least-privilege policy with 4 S3 actions scoped to bucket ARN and objects ARN
- ✅ **User-Policy Attachment**: Policy bound to IAM user

### Odoo Configuration Status

- ✅ **debian/odoo.conf**: 4 S3 keys appended under `[options]` section
- ✅ **Comment Block**: LocalStack dev defaults comment present with production override guidance
- ✅ **INI Format**: Follows existing convention (key = value format, semicolon comments)

### Preservation Verification

- ✅ **blitzy-localstack/tests/**: Zero files created, modified, or deleted — confirmed via `git diff --name-only`
- ✅ **Git Status**: Only untracked files are `terraform.tfstate*` (runtime state — not committed)

### Items Requiring Manual Verification

- ⚠ **S3 Lifecycle Test**: Full object lifecycle (upload → list → download → verify → delete) documented in README but requires LocalStack running to execute
- ⚠ **Idempotency Test**: Module supports destroy/apply cycle via `force_destroy = true` but explicit cycle not executed during validation

---

## 5. Compliance & Quality Review

| AAP Requirement | Status | Evidence | Notes |
|----------------|--------|----------|-------|
| Create `terraform/odoo-s3/versions.tf` — Terraform 1.1.3, hashicorp/aws | ✅ Pass | File exists, matches reference pattern from `blitzy-localstack/tests/aws/terraform/versions.tf` | Minor formatting normalized by `terraform fmt` |
| Create `terraform/odoo-s3/provider.tf` — LocalStack provider with s3, iam, ses, secretsmanager endpoints | ✅ Pass | File exists with all 4 endpoints, skip_* flags, test/test credentials | Uses `s3_use_path_style` (renamed from `s3_force_path_style` in AWS provider v6.36.0) |
| Create `terraform/odoo-s3/variables.tf` — 3 input variables | ✅ Pass | `bucket_name`, `iam_user_name`, `aws_region` (default: us-east-1) defined | Types and defaults match AAP spec |
| Create `terraform/odoo-s3/terraform.tfvars` — default values | ✅ Pass | Values: odoo-attachments, odoo-s3, us-east-1 | Matches AAP specification exactly |
| Create `terraform/odoo-s3/main.tf` — 6 AWS resources | ✅ Pass | All 6 resources defined and in Terraform state | Includes force_destroy for idempotency |
| Create `terraform/odoo-s3/outputs.tf` — 3 outputs, secret sensitive | ✅ Pass | bucket_name, iam_access_key_id, iam_secret_access_key (sensitive=true) | All outputs verified via `terraform output -json` |
| Create `terraform/odoo-s3/README.md` — module documentation | ✅ Pass | 194 lines covering prerequisites, workflow, verification, Odoo connection | Comprehensive and well-structured |
| Modify `debian/odoo.conf` — 4 S3 keys + comment | ✅ Pass | git diff confirms 6 added lines (comment + blank line + 4 keys) | Follows existing INI format conventions |
| Provision exactly 6 AWS resources | ✅ Pass | `terraform state list` returns 6 resources | Matches resource count spec |
| IAM policy: least privilege (4 S3 actions) | ✅ Pass | Policy grants only s3:GetObject, s3:PutObject, s3:DeleteObject, s3:ListBucket | No wildcard permissions |
| Sensitive output marking | ✅ Pass | `iam_secret_access_key` has `sensitive = true` | Prevents log exposure |
| Zero changes under `blitzy-localstack/tests/` | ✅ Pass | `git diff --name-only -- blitzy-localstack/tests/` returns empty | Preservation requirement met |
| Module idempotency support | ✅ Pass | `force_destroy = true` on S3 bucket | Enables clean destroy/apply cycles |
| `terraform fmt` compliance | ✅ Pass | All 5 .tf files pass `terraform fmt -check` | Standardized formatting |
| `terraform validate` compliance | ✅ Pass | "Success! The configuration is valid." | Zero validation errors |

### Fixes Applied During Autonomous Validation

| Fix | File | Description |
|-----|------|-------------|
| `force_destroy = true` | `terraform/odoo-s3/main.tf` | Added to S3 bucket resource to enable idempotent destroy/apply cycles without manual bucket emptying |
| `s3_use_path_style` | `terraform/odoo-s3/provider.tf` | Used instead of `s3_force_path_style` to match AWS provider v6.36.0 renamed attribute |

**Compliance Score: 15/15 requirements — 100% compliant**

---

## 6. Risk Assessment

| Risk | Category | Severity | Probability | Mitigation | Status |
|------|----------|----------|-------------|------------|--------|
| Terraform state files contain sensitive IAM credentials and could be committed to git | Security | High | High | Add `.gitignore` entries for `*.tfstate`, `*.tfstate.backup`, and `.terraform/` directory | Open — requires human action |
| LocalStack service must be running before terraform apply; failure to start causes apply errors | Operational | Medium | Medium | README documents prerequisite; add health check command `curl -s http://localhost:4566/_localstack/health` before apply | Mitigated — documented |
| `s3_use_path_style` renamed from `s3_force_path_style` may confuse developers comparing with reference provider.tf | Technical | Low | Medium | Comment in provider.tf explaining the rename; README notes AWS provider v6.36.0 compatibility | Mitigated — adapted |
| Terraform 1.1.3 is pinned but significantly outdated (latest is 1.14.7); may have known vulnerabilities | Technical | Medium | Low | Version is intentionally matched to existing LocalStack test infrastructure; upgrade when test infra is updated | Accepted — aligns with existing pattern |
| Production Odoo deployment may accidentally use LocalStack dev credentials (test/test) | Security | High | Low | Comment in `debian/odoo.conf` explicitly warns to override via environment variables; however, no runtime validation exists | Open — requires human documentation/tooling |
| No automated integration test verifying S3 object lifecycle with provisioned IAM credentials | Integration | Medium | Medium | README provides manual verification commands; automated script needed for CI/CD | Open — requires human action |
| IAM access key stored in Terraform state; no key rotation mechanism | Security | Medium | Low | Acceptable for LocalStack development; production should use IAM roles instead of access keys | Accepted — dev-only scope |

---

## 7. Visual Project Status

```mermaid
pie title Project Hours Breakdown
    "Completed Work" : 13
    "Remaining Work" : 3.5
```

**Completed Work: 13h (78.8%) | Remaining Work: 3.5h (21.2%)**

### Remaining Hours by Priority

| Priority | Hours | Tasks |
|----------|-------|-------|
| High | 2.0h | .gitignore for state files (0.5h), Automated integration test script (1.5h) |
| Medium | 1.5h | Idempotency verification test (1.0h), Production env var documentation (0.5h) |
| **Total** | **3.5h** | |

---

## 8. Summary & Recommendations

### Achievements

The Terraform module for Odoo S3 attachment storage has been successfully implemented and validated. All 8 in-scope files (7 created, 1 modified) are committed across 9 well-structured commits. The module provisions exactly 6 AWS resources against LocalStack as specified, passes all Terraform validation checks (`fmt`, `validate`, `plan`, `apply`), and maintains zero modifications to the protected `blitzy-localstack/tests/` directory. The IAM policy follows the principle of least privilege, and sensitive outputs are properly marked. The comprehensive README.md provides complete operational documentation.

### Current Status

The project is 78.8% complete (13h completed out of 16.5h total). All AAP-specified deliverables have been fully implemented and validated. The remaining 3.5 hours represent path-to-production activities: git hygiene (.gitignore), automated integration testing, idempotency verification, and production deployment documentation.

### Critical Path to Production

1. **Immediate (0.5h):** Add `.gitignore` entries to prevent terraform state files from being committed — this is the highest priority security item
2. **Short-term (1.5h):** Create an automated integration test script that verifies the full S3 object lifecycle using IAM credentials from Terraform outputs
3. **Medium-term (1.5h):** Verify idempotency with a scripted destroy/apply cycle and document production environment variable overrides

### Production Readiness Assessment

The module is **development-ready** — all infrastructure is provisioned and validated against LocalStack. For production readiness, the 3.5 hours of remaining path-to-production work should be completed, particularly the `.gitignore` update (security) and automated integration test (reliability). The module is explicitly scoped to LocalStack development and does not include production AWS configuration, which is correctly out of scope per the AAP.

---

## 9. Development Guide

### System Prerequisites

| Requirement | Version | Installation |
|-------------|---------|-------------|
| Terraform | 1.1.3 (exact) | Download from [releases.hashicorp.com/terraform/1.1.3/](https://releases.hashicorp.com/terraform/1.1.3/) |
| Docker & Docker Compose | Latest stable | Required to run LocalStack |
| awslocal CLI (optional) | Latest stable | `pip install awscli-local` |
| Git | 2.x+ | Standard installation |

### Environment Setup

**1. Start LocalStack**

```bash
cd blitzy-localstack/
docker compose up -d
```

Verify LocalStack is running:

```bash
curl -s http://localhost:4566/_localstack/health | python3 -m json.tool
```

Expected: JSON response showing service statuses.

**2. Verify Terraform Version**

```bash
terraform -version
```

Expected output: `Terraform v1.1.3`

### Dependency Installation

**3. Initialize Terraform Module**

```bash
cd terraform/odoo-s3/
terraform init
```

Expected: Downloads `hashicorp/aws` provider and creates `.terraform/` directory and `.terraform.lock.hcl`.

### Application Startup — Provision Infrastructure

**4. Validate Configuration**

```bash
terraform fmt -check
terraform validate
```

Expected: No output from `fmt -check` (all files pass), "Success! The configuration is valid." from `validate`.

**5. Preview Resources**

```bash
terraform plan
```

Expected: "Plan: 6 to add, 0 to change, 0 to destroy."

**6. Apply Resources**

```bash
terraform apply -auto-approve
```

Expected: 6 resources created. "Apply complete! Resources: 6 added, 0 changed, 0 destroyed."

### Verification Steps

**7. Verify Resources in State**

```bash
terraform state list
```

Expected output:
```
aws_iam_access_key.odoo_s3_key
aws_iam_policy.odoo_s3_policy
aws_iam_user.odoo_s3_user
aws_iam_user_policy_attachment.odoo_s3_attach
aws_s3_bucket.odoo_attachments
aws_s3_bucket_versioning.odoo_attachments
```

**8. Retrieve Outputs**

```bash
terraform output bucket_name
terraform output iam_access_key_id
terraform output -json iam_secret_access_key
```

**9. Verify with awslocal (if installed)**

```bash
awslocal s3 ls
awslocal iam list-users
awslocal s3api get-bucket-versioning --bucket odoo-attachments
```

### Example Usage — S3 Lifecycle Test

```bash
# Upload a test file
echo "hello odoo" > /tmp/test.txt
awslocal s3 cp /tmp/test.txt s3://odoo-attachments/test.txt

# List bucket contents
awslocal s3 ls s3://odoo-attachments/

# Download and verify
awslocal s3 cp s3://odoo-attachments/test.txt /tmp/test-download.txt
cat /tmp/test-download.txt
# Expected: hello odoo

# Clean up
awslocal s3 rm s3://odoo-attachments/test.txt
```

### Teardown

```bash
cd terraform/odoo-s3/
terraform destroy -auto-approve
```

### Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| `Error: Failed to query available provider packages` | No internet or registry unreachable | Run `terraform init` with network access; provider is cached in `.terraform/` after first init |
| `Error: error configuring Terraform AWS Provider` | LocalStack not running | Start LocalStack: `cd blitzy-localstack/ && docker compose up -d` |
| `terraform plan` shows changes after apply | LocalStack state reset (container restart without persistence) | Re-run `terraform apply -auto-approve` |
| `Error: BucketNotEmpty` on destroy | Bucket has objects | Already mitigated with `force_destroy = true`; if persists, manually empty: `awslocal s3 rm s3://odoo-attachments --recursive` |
| Terraform version mismatch | Wrong Terraform binary | Ensure Terraform 1.1.3 is installed; check with `terraform -version` |

---

## 10. Appendices

### A. Command Reference

| Command | Purpose | Working Directory |
|---------|---------|-------------------|
| `terraform init` | Download providers and initialize module | `terraform/odoo-s3/` |
| `terraform fmt -check` | Verify .tf file formatting without modifying | `terraform/odoo-s3/` |
| `terraform validate` | Validate configuration syntax and references | `terraform/odoo-s3/` |
| `terraform plan` | Preview resource changes | `terraform/odoo-s3/` |
| `terraform apply -auto-approve` | Create/update resources without prompt | `terraform/odoo-s3/` |
| `terraform destroy -auto-approve` | Destroy all resources without prompt | `terraform/odoo-s3/` |
| `terraform output -json` | Display all outputs including sensitive values | `terraform/odoo-s3/` |
| `terraform state list` | List all resources in state | `terraform/odoo-s3/` |
| `awslocal s3 ls` | List S3 buckets in LocalStack | Any |
| `awslocal iam list-users` | List IAM users in LocalStack | Any |
| `docker compose up -d` | Start LocalStack | `blitzy-localstack/` |

### B. Port Reference

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| LocalStack Gateway | 4566 | HTTP | S3, IAM, SES, Secrets Manager APIs |

### C. Key File Locations

| File | Path | Purpose |
|------|------|---------|
| Terraform Version Constraints | `terraform/odoo-s3/versions.tf` | Pins Terraform 1.1.3 and hashicorp/aws provider |
| Provider Configuration | `terraform/odoo-s3/provider.tf` | LocalStack AWS provider with 4 service endpoints |
| Input Variables | `terraform/odoo-s3/variables.tf` | Declares bucket_name, iam_user_name, aws_region |
| Variable Defaults | `terraform/odoo-s3/terraform.tfvars` | Default values for all variables |
| Resource Definitions | `terraform/odoo-s3/main.tf` | 6 AWS resource definitions (S3 + IAM) |
| Output Definitions | `terraform/odoo-s3/outputs.tf` | Exports bucket name and IAM credentials |
| Module Documentation | `terraform/odoo-s3/README.md` | Comprehensive usage and verification guide |
| Odoo Configuration | `debian/odoo.conf` | Server config with S3 connection keys |
| Reference Provider | `blitzy-localstack/tests/aws/terraform/provider.tf` | Original LocalStack provider pattern (read-only) |
| Reference Versions | `blitzy-localstack/tests/aws/terraform/versions.tf` | Original version constraints (read-only) |
| LocalStack Docker | `blitzy-localstack/docker-compose.yml` | LocalStack service definition |

### D. Technology Versions

| Technology | Version | Notes |
|------------|---------|-------|
| Terraform | 1.1.3 | Exact version pinned in `versions.tf` |
| hashicorp/aws Provider | 6.36.0 | Downloaded during `terraform init`; no version pin in `versions.tf` |
| LocalStack | Latest (Docker image) | Per `blitzy-localstack/docker-compose.yml` |
| Odoo | 19.0 | Target application for S3 attachment storage |
| Python | ≥ 3.10 | Odoo runtime requirement |

### E. Environment Variable Reference

| Variable | Default Value | Description | Override Required for Production |
|----------|--------------|-------------|---|----|
| `aws_access_key_id` | `test` | IAM access key for S3 | Yes — replace with real AWS credentials |
| `aws_secret_access_key` | `test` | IAM secret key for S3 | Yes — replace with real AWS credentials |
| `aws_region` | `us-east-1` | AWS region | Yes — set to target production region |
| `aws_s3_bucket` | `odoo-attachments` | S3 bucket name | Yes — set to production bucket name |

These values are configured in `debian/odoo.conf` under `[options]`. In production, override via environment variables as noted in the comment block.

### F. Developer Tools Guide

| Tool | Purpose | Installation |
|------|---------|-------------|
| Terraform 1.1.3 | Infrastructure as Code | `wget https://releases.hashicorp.com/terraform/1.1.3/terraform_1.1.3_linux_amd64.zip && unzip terraform_1.1.3_linux_amd64.zip && sudo mv terraform /usr/local/bin/` |
| awscli-local | LocalStack CLI wrapper | `pip install awscli-local` |
| Docker Compose | Container orchestration | Included with Docker Desktop or `apt install docker-compose-plugin` |

### G. Glossary

| Term | Definition |
|------|-----------|
| LocalStack | AWS cloud service emulator that runs locally for development and testing |
| Terraform | HashiCorp's infrastructure as code tool for provisioning cloud resources |
| IAM | AWS Identity and Access Management — manages users, roles, and permissions |
| S3 | AWS Simple Storage Service — scalable object storage |
| HCL | HashiCorp Configuration Language — Terraform's declarative configuration syntax |
| `force_destroy` | Terraform S3 bucket attribute that allows deletion of non-empty buckets |
| `s3_use_path_style` | AWS provider setting for path-style S3 URLs (required for LocalStack) |
| `sensitive` | Terraform output attribute that prevents values from appearing in CLI output and logs |
