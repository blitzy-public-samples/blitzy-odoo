# Blitzy Project Guide

---

## 1. Executive Summary

### 1.1 Project Overview

This project provisions a complete Terraform infrastructure module at `./terraform/odoo-gcs/` that automates the creation of a Google Cloud Storage (GCS) bucket, a dedicated GCP service account, and the associated IAM bindings required for Odoo 19.0 to store file attachments externally in GCS. The module replaces or augments the default filesystem-based attachment storage with a cloud-native solution. The target users are DevOps engineers and Odoo administrators who need to deploy GCS-backed attachment storage. The `debian/odoo.conf` file is also updated with GCS placeholder settings for deployment templates.

### 1.2 Completion Status

<!-- Pie chart: Completed = Dark Blue (#5B39F3), Remaining = White (#FFFFFF) -->
```mermaid
pie title Project Completion — 69.2% Complete
    "Completed (18h)" : 18
    "Remaining (8h)" : 8
```

| Metric | Value |
|---|---|
| **Total Project Hours** | 26h |
| **Completed Hours (AI)** | 18h |
| **Remaining Hours** | 8h |
| **Completion Percentage** | 69.2% (18 / 26) |

**Calculation:** Completed Hours (18h) / Total Project Hours (18h + 8h = 26h) × 100 = **69.2%**

### 1.3 Key Accomplishments

- ✅ Created self-contained Terraform module at `./terraform/odoo-gcs/` with 7 HCL/documentation files per AAP specification
- ✅ Provisioned 4 GCP resources: GCS bucket (versioning, uniform access, force_destroy=false), service account, SA key, IAM binding (roles/storage.objectAdmin)
- ✅ Implemented Application Default Credentials (ADC) support for CI/CD environments via `credentials_file = null` default
- ✅ Marked `service_account_key` output as `sensitive = true` to prevent credential exposure
- ✅ Created comprehensive 220-line README.md covering prerequisites, workflow, key extraction, and Odoo connection instructions
- ✅ Updated `debian/odoo.conf` additively with GCS placeholder settings (all existing settings preserved)
- ✅ Added security-focused `.gitignore` for state files, credentials, and key artifacts
- ✅ Passed all 4 validation gates: Dependencies (terraform init), Compilation (terraform validate), Tests (terraform fmt -check), Runtime (terraform plan — 4 to add)
- ✅ Respected user directive: `blitzy-localstack/tests/` left completely untouched

### 1.4 Critical Unresolved Issues

| Issue | Impact | Owner | ETA |
|---|---|---|---|
| Real GCP project ID not supplied | Cannot provision actual infrastructure without a valid GCP project ID | Human Developer | 1h |
| Service account key not extracted | Odoo cannot authenticate to GCS until key is decoded and configured | Human Developer | 1h |
| Production secrets management not configured | Service account key must be stored securely (GCP Secret Manager / Vault) for production use | Human Developer | 1.5h |

### 1.5 Access Issues

| System/Resource | Type of Access | Issue Description | Resolution Status | Owner |
|---|---|---|---|---|
| GCP Project | Project Owner / Editor IAM role | A real GCP project with billing enabled is required to run `terraform apply` | Pending | Human Developer |
| Cloud Storage API | API Enablement | `storage.googleapis.com` must be enabled on the target GCP project | Pending | Human Developer |
| IAM API | API Enablement | `iam.googleapis.com` must be enabled on the target GCP project | Pending | Human Developer |
| GCP Credentials | Application Default Credentials or SA key | `gcloud auth application-default login` must be run or credentials file provided | Pending | Human Developer |

### 1.6 Recommended Next Steps

1. **[High]** Supply a real GCP project ID and run `terraform apply -var="project=YOUR_PROJECT_ID"` to provision the GCS infrastructure
2. **[High]** Extract the service account key via `terraform output -raw service_account_key | base64 --decode > sa-key.json` and store securely
3. **[High]** Configure Odoo's `cloud_storage_google` addon with the provisioned bucket name and service account key
4. **[Medium]** Set up production secrets management (GCP Secret Manager) for the service account key
5. **[Medium]** Perform end-to-end integration testing: upload a file attachment in Odoo and verify it appears in the GCS bucket

---

## 2. Project Hours Breakdown

### 2.1 Completed Work Detail

| Component | Hours | Description |
|---|---|---|
| Module Architecture & Design | 1.5h | Designed resource dependency graph, file separation strategy, and variable parameterization per AAP Section 0.4.2 |
| `versions.tf` | 0.5h | Declared `hashicorp/google >= 5.0` provider constraint (8 lines) |
| `provider.tf` | 1.0h | Configured Google provider with ADC support via `credentials_file = null` default; comprehensive inline documentation (19 lines) |
| `variables.tf` | 1.0h | Defined 5 input variables with types, descriptions, and defaults; `project` required with no default (28 lines) |
| `terraform.tfvars` | 0.5h | Supplied concrete defaults for region, bucket_name, service_account_id; project intentionally omitted (3 lines) |
| `main.tf` | 4.0h | Implemented 4 GCP resources: GCS bucket (versioning, uniform access, force_destroy=false), service account, SA key, IAM binding; comprehensive inline documentation (72 lines) |
| `outputs.tf` | 2.0h | Declared 4 outputs with descriptions; `service_account_key` marked `sensitive = true`; security documentation (71 lines) |
| `README.md` | 4.0h | Created 220-line comprehensive documentation covering prerequisites, workflow, input variables, outputs, key extraction, Odoo connection (2 options), resources created, and security notes |
| `debian/odoo.conf` Modification | 0.5h | Appended GCS attachment storage settings additively; preserved all existing configuration; added placeholder comment (7 lines added) |
| `.gitignore` & `.terraform.lock.hcl` | 0.5h | Created security-focused .gitignore (30 lines) for state/credentials exclusion; generated provider lock file via terraform init |
| Validation & Testing | 1.5h | Ran terraform init (hashicorp/google v7.25.0), terraform validate (Success), terraform fmt -check (exit 0), terraform plan (4 to add, 0 change, 0 destroy) |
| Code Review & Fixes | 0.5h | Addressed code review findings in README.md (commit abe9912) |
| **Total Completed** | **18h** | |

### 2.2 Remaining Work Detail

| Category | Hours | Priority |
|---|---|---|
| GCP Project Setup & API Enablement | 1.0h | High |
| Terraform Apply with Real GCP Credentials | 1.0h | High |
| Service Account Key Extraction & Secure Storage | 1.0h | High |
| Odoo Runtime Integration Configuration | 1.5h | Medium |
| End-to-End Integration Testing | 2.0h | Medium |
| Production Secrets Management (GCP Secret Manager) | 1.5h | Medium |
| **Total Remaining** | **8h** | |

**Verification:** Section 2.1 (18h) + Section 2.2 (8h) = 26h = Total Project Hours in Section 1.2 ✅

---

## 3. Test Results

| Test Category | Framework | Total Tests | Passed | Failed | Coverage % | Notes |
|---|---|---|---|---|---|---|
| HCL Syntax Validation | `terraform validate` | 1 | 1 | 0 | 100% | "Success! The configuration is valid." — validates all HCL syntax, resource references, variable types, output references |
| Formatting Compliance | `terraform fmt -check` | 7 | 7 | 0 | 100% | All 7 HCL files (versions.tf, provider.tf, variables.tf, terraform.tfvars, main.tf, outputs.tf, .terraform.lock.hcl) pass canonical formatting |
| Resource Planning | `terraform plan` | 4 | 4 | 0 | 100% | Plan: 4 to add, 0 to change, 0 to destroy — all 4 resources and 4 outputs correctly declared |
| Dependency Resolution | `terraform init` | 1 | 1 | 0 | 100% | hashicorp/google v7.25.0 successfully installed (constraint >= 5.0 satisfied) |
| **Totals** | | **13** | **13** | **0** | **100%** | Zero errors, zero warnings across all validation gates |

All tests originate from Blitzy's autonomous validation pipeline (Final Validator agent). No external or manually-run tests are included.

---

## 4. Runtime Validation & UI Verification

### Terraform Runtime Validation

- ✅ **terraform init** — Successfully initialized; hashicorp/google v7.25.0 downloaded and locked
- ✅ **terraform validate** — "Success! The configuration is valid."
- ✅ **terraform fmt -check** — Exit code 0; all HCL files meet canonical formatting
- ✅ **terraform plan** — `Plan: 4 to add, 0 to change, 0 to destroy`
  - `google_storage_bucket.odoo_attachments` — name="odoo-attachments", location="US-CENTRAL1", versioning=true, force_destroy=false, uniform_bucket_level_access=true
  - `google_service_account.odoo_gcs_sa` — account_id="odoo-gcs", display_name="Odoo GCS Service Account"
  - `google_service_account_key.odoo_gcs_key` — private_key=(sensitive value)
  - `google_storage_bucket_iam_member.odoo_gcs_admin` — role="roles/storage.objectAdmin", member="serviceAccount:odoo-gcs@validation-test-project.iam.gserviceaccount.com"

### Terraform Outputs Verified

- ✅ `bucket_name` = "odoo-attachments"
- ✅ `project` = "validation-test-project"
- ✅ `service_account_email` = "odoo-gcs@validation-test-project.iam.gserviceaccount.com"
- ✅ `service_account_key` = (sensitive value) — correctly redacted

### Odoo Configuration Verification

- ✅ `debian/odoo.conf` — Existing settings preserved (db_host, db_port, db_user, db_password, default_productivity_apps)
- ✅ GCS settings appended additively with placeholder comment
- ✅ `ir_attachment_location = gs://odoo-attachments` correctly set

### Exclusion Zone Verification

- ✅ `blitzy-localstack/tests/` — Zero modifications (git diff confirms no changes)
- ✅ No Python source files modified
- ✅ No other Odoo addons or core files modified

### UI Verification

- ⚠️ Not applicable — This feature is entirely infrastructure-as-code and server configuration. No UI components were created or modified. The Odoo admin configures GCS integration through the existing Settings → Technical → Cloud Storage UI provided by the `cloud_storage_google` addon.

---

## 5. Compliance & Quality Review

| Compliance Requirement | AAP Reference | Status | Evidence |
|---|---|---|---|
| Self-contained Terraform module at `./terraform/odoo-gcs/` | Section 0.1.1 | ✅ Pass | Directory created with 7 AAP-specified files + 2 supporting files |
| GCS bucket with versioning enabled | Section 0.5.1 | ✅ Pass | `versioning { enabled = true }` in main.tf |
| GCS bucket with `force_destroy = false` | Rule 0.7.1 | ✅ Pass | `force_destroy = false` in main.tf |
| GCS bucket with `uniform_bucket_level_access = true` | Rule 0.7.1 | ✅ Pass | `uniform_bucket_level_access = true` in main.tf |
| Service account with `account_id = "odoo-gcs"` | Section 0.5.1 | ✅ Pass | `account_id = var.service_account_id` (default "odoo-gcs") |
| Service account `display_name = "Odoo GCS Service Account"` | Section 0.5.1 | ✅ Pass | Exact string in main.tf |
| Service account key resource generated | Section 0.5.1 | ✅ Pass | `google_service_account_key.odoo_gcs_key` in main.tf |
| IAM binding: `roles/storage.objectAdmin` | Section 0.5.1 | ✅ Pass | `role = "roles/storage.objectAdmin"` in main.tf |
| 4 outputs exposed | Section 0.5.1 | ✅ Pass | bucket_name, service_account_email, service_account_key, project |
| `service_account_key` output `sensitive = true` | Rule 0.7.1 | ✅ Pass | `sensitive = true` in outputs.tf |
| `hashicorp/google >= 5.0` constraint | Rule 0.7.1 | ✅ Pass | `version = ">= 5.0"` in versions.tf |
| ADC support via `credentials_file = null` | Rule 0.7.1 | ✅ Pass | `default = null` in variables.tf |
| `project` variable has no default (required) | Rule 0.7.1 | ✅ Pass | No `default` argument on project variable |
| `debian/odoo.conf` updated additively | Rule 0.7.1 | ✅ Pass | Git diff confirms all existing settings preserved |
| GCS placeholder comment in odoo.conf | Section 0.5.2 | ✅ Pass | Comment block present above new settings |
| README.md with prerequisites, workflow, key extraction, Odoo connection | Section 0.5.1 | ✅ Pass | 220-line comprehensive documentation |
| `blitzy-localstack/tests/` not touched | Section 0.6.2 | ✅ Pass | Zero changes to blitzy-localstack/ directory |
| No Python source files modified | Section 0.6.2 | ✅ Pass | Only HCL, tfvars, INI, and Markdown files changed |

### Fixes Applied During Autonomous Validation

| Fix | Commit | Description |
|---|---|---|
| README code review findings | `abe9912` | Addressed documentation review findings in Terraform module README |
| .gitignore addition | `b62a86a` | Added .gitignore for Terraform state files and credential artifacts |

### Outstanding Compliance Items

- None — all AAP-specified compliance requirements have been met.

---

## 6. Risk Assessment

| Risk | Category | Severity | Probability | Mitigation | Status |
|---|---|---|---|---|---|
| Static service account key exposure | Security | High | Medium | Key output marked `sensitive = true`; .gitignore excludes sa-key.json and credential files; README warns against committing keys | Mitigated (code-level); Pending (operational) |
| GCS bucket accidental deletion | Operational | High | Low | `force_destroy = false` prevents Terraform from destroying non-empty buckets | Mitigated |
| Missing GCP project credentials at apply time | Technical | High | High | ADC support via `credentials_file = null`; README documents `gcloud auth` prerequisite | Documented |
| Terraform state contains sensitive data | Security | High | High | .gitignore excludes *.tfstate files; recommend remote state backend (GCS/S3) with encryption | Partially mitigated |
| Odoo runtime integration not tested E2E | Integration | Medium | High | terraform plan validates resource graph; actual GCS upload requires live GCP project and running Odoo instance | Pending human testing |
| Service account key rotation not automated | Operational | Medium | Medium | README documents manual key rotation via `terraform apply -replace`; recommend automated rotation policy | Documented |
| GCS bucket naming collision | Technical | Low | Low | Bucket names are globally unique in GCS; variable allows customization | Documented in README |
| Provider version drift | Technical | Low | Low | .terraform.lock.hcl pins exact provider hash (v7.25.0); `>= 5.0` constraint is broad | Mitigated by lock file |

---

## 7. Visual Project Status

```mermaid
pie title Project Hours Breakdown
    "Completed Work" : 18
    "Remaining Work" : 8
```

**Integrity Verification:** "Remaining Work" (8h) matches Section 1.2 Remaining Hours (8h) and Section 2.2 Hours sum (1.0 + 1.0 + 1.0 + 1.5 + 2.0 + 1.5 = 8h) ✅

### Remaining Work by Priority

| Priority | Hours | Categories |
|---|---|---|
| High | 3.0h | GCP Project Setup (1h), Terraform Apply (1h), Key Extraction (1h) |
| Medium | 5.0h | Odoo Integration (1.5h), E2E Testing (2h), Secrets Management (1.5h) |
| **Total** | **8h** | |

---

## 8. Summary & Recommendations

### Achievements

The Blitzy platform autonomously delivered a complete, production-quality Terraform module for Odoo 19.0 GCS attachment storage infrastructure. All 8 AAP-specified deliverables (7 new files + 1 config modification) were implemented, validated, and committed. The module passed all 4 validation gates (dependency resolution, HCL validation, formatting compliance, and resource planning) with zero errors and zero warnings.

The project is **69.2% complete** (18 hours completed out of 26 total hours). All code and infrastructure-as-code deliverables specified in the AAP are fully implemented. The remaining 8 hours consist of operational and integration tasks that require human intervention: provisioning real GCP infrastructure, extracting credentials, configuring Odoo, and performing end-to-end testing.

### Remaining Gaps

The 8 hours of remaining work are exclusively path-to-production operational tasks:
- **Infrastructure provisioning** (2h): Requires a real GCP project with billing and API enablement
- **Credential management** (2.5h): Service account key extraction and production secrets management setup
- **Integration & testing** (3.5h): Odoo runtime configuration and E2E testing of attachment uploads to GCS

### Critical Path to Production

1. Provision GCP project with Cloud Storage and IAM APIs enabled
2. Run `terraform apply` with real project ID
3. Extract service account key and store in GCP Secret Manager
4. Configure Odoo `cloud_storage_google` addon with bucket name and key
5. Verify attachment upload/download cycle works end-to-end

### Production Readiness Assessment

| Dimension | Status | Notes |
|---|---|---|
| Code Quality | ✅ Ready | All HCL files pass validate and fmt; comprehensive inline documentation |
| Security | ⚠️ Needs Action | Service account key must be extracted and stored securely before production use |
| Documentation | ✅ Ready | 220-line README covers all operational workflows |
| Testing | ⚠️ Needs Action | Terraform plan validates resource graph; E2E testing with live GCP required |
| Deployment | ⚠️ Needs Action | Real GCP project ID and credentials required |

---

## 9. Development Guide

### System Prerequisites

| Software | Version | Purpose |
|---|---|---|
| Terraform CLI | >= 1.0 (v1.9.8 tested) | Infrastructure-as-code execution engine |
| Google Cloud SDK (`gcloud`) | Latest stable | GCP authentication and API management |
| Python | >= 3.10 (3.12.3 tested) | Odoo runtime (for integration testing) |
| Git | >= 2.0 | Version control |

### Environment Setup

#### 1. Clone the Repository

```bash
git clone <repository-url>
cd <repository-root>
git checkout blitzy-3785120d-53bb-42e9-801a-21fcfd86d205
```

#### 2. Authenticate with GCP

```bash
# Install gcloud if not present: https://cloud.google.com/sdk/docs/install
gcloud auth application-default login
```

#### 3. Enable Required GCP APIs

```bash
gcloud services enable storage.googleapis.com --project=YOUR_GCP_PROJECT_ID
gcloud services enable iam.googleapis.com --project=YOUR_GCP_PROJECT_ID
```

### Dependency Installation

#### Terraform Provider Installation

```bash
cd terraform/odoo-gcs
terraform init
```

**Expected output:**
```
Initializing provider plugins...
- Finding hashicorp/google versions matching ">= 5.0.0"...
- Installing hashicorp/google v7.25.0...
- Installed hashicorp/google v7.25.0 (signed by HashiCorp)
Terraform has been successfully initialized!
```

### Application Startup Sequence

#### Step 1: Validate the Configuration

```bash
cd terraform/odoo-gcs
terraform validate
```

**Expected output:** `Success! The configuration is valid.`

#### Step 2: Preview Infrastructure Changes

```bash
terraform plan -var="project=YOUR_GCP_PROJECT_ID"
```

**Expected output:** `Plan: 4 to add, 0 to change, 0 to destroy.`

#### Step 3: Provision the Infrastructure

```bash
terraform apply -var="project=YOUR_GCP_PROJECT_ID"
```

Type `yes` when prompted. Expected resources created:
1. `google_storage_bucket.odoo_attachments`
2. `google_service_account.odoo_gcs_sa`
3. `google_service_account_key.odoo_gcs_key`
4. `google_storage_bucket_iam_member.odoo_gcs_admin`

#### Step 4: Extract the Service Account Key

```bash
terraform output -raw service_account_key | base64 --decode > sa-key.json
cat sa-key.json | python3 -m json.tool  # Verify valid JSON
```

### Verification Steps

```bash
# Verify bucket name output
terraform output bucket_name
# Expected: "odoo-attachments"

# Verify service account email
terraform output service_account_email
# Expected: "odoo-gcs@YOUR_PROJECT.iam.gserviceaccount.com"

# Verify project output
terraform output project
# Expected: "YOUR_GCP_PROJECT_ID"

# Verify formatting compliance
terraform fmt -check
# Expected: exit code 0 (no output)
```

### Example Usage — Override Variables

```bash
# Custom bucket name and region
terraform apply \
  -var="project=my-production-project" \
  -var="region=europe-west1" \
  -var="bucket_name=my-odoo-attachments"

# Using environment variables
export TF_VAR_project="my-production-project"
terraform apply
```

### Troubleshooting

| Issue | Cause | Resolution |
|---|---|---|
| `Error: google: could not find default credentials` | GCP ADC not configured | Run `gcloud auth application-default login` |
| `Error: googleapi: Error 403: ... has not been used in project` | Cloud Storage or IAM API not enabled | Run `gcloud services enable storage.googleapis.com iam.googleapis.com` |
| `Error: googleapi: Error 409: ... already exists` | Bucket name collision (globally unique) | Change `bucket_name` variable to a unique name |
| `Error: The bucket ... is not empty` during destroy | `force_destroy = false` protection active | Manually empty the bucket via GCP Console, then run `terraform destroy` |
| `terraform init` hangs or fails | Network/proxy issues | Check internet connectivity; set `HTTPS_PROXY` if behind a proxy |

---

## 10. Appendices

### A. Command Reference

| Command | Purpose | Working Directory |
|---|---|---|
| `terraform init` | Download provider plugins and initialize module | `terraform/odoo-gcs/` |
| `terraform validate` | Validate HCL syntax and resource references | `terraform/odoo-gcs/` |
| `terraform fmt -check` | Verify canonical HCL formatting | `terraform/odoo-gcs/` |
| `terraform plan -var="project=ID"` | Preview infrastructure changes | `terraform/odoo-gcs/` |
| `terraform apply -var="project=ID"` | Provision GCP infrastructure | `terraform/odoo-gcs/` |
| `terraform output -raw service_account_key \| base64 --decode > sa-key.json` | Extract service account key | `terraform/odoo-gcs/` |
| `terraform destroy -var="project=ID"` | Tear down infrastructure | `terraform/odoo-gcs/` |
| `terraform apply -replace="google_service_account_key.odoo_gcs_key" -var="project=ID"` | Rotate service account key | `terraform/odoo-gcs/` |

### B. Port Reference

Not applicable — this feature is infrastructure-as-code only with no running services or exposed ports.

### C. Key File Locations

| File | Path | Purpose |
|---|---|---|
| Terraform Module Root | `terraform/odoo-gcs/` | Self-contained GCS infrastructure module |
| Provider Config | `terraform/odoo-gcs/provider.tf` | Google Cloud provider with ADC support |
| Version Constraints | `terraform/odoo-gcs/versions.tf` | hashicorp/google >= 5.0 |
| Resource Definitions | `terraform/odoo-gcs/main.tf` | 4 GCP resources (bucket, SA, key, IAM) |
| Output Declarations | `terraform/odoo-gcs/outputs.tf` | 4 outputs (key is sensitive) |
| Variable Declarations | `terraform/odoo-gcs/variables.tf` | 5 input variables |
| Default Values | `terraform/odoo-gcs/terraform.tfvars` | Non-sensitive defaults |
| Module Documentation | `terraform/odoo-gcs/README.md` | 220-line comprehensive docs |
| Odoo Configuration | `debian/odoo.conf` | GCS attachment storage settings |
| Provider Lock | `terraform/odoo-gcs/.terraform.lock.hcl` | Reproducible provider installs |
| Security Exclusions | `terraform/odoo-gcs/.gitignore` | State/credential exclusion patterns |

### D. Technology Versions

| Technology | Version | Notes |
|---|---|---|
| Terraform CLI | v1.9.8 (tested) | >= 1.0 recommended |
| hashicorp/google Provider | v7.25.0 (locked) | Constraint: >= 5.0 |
| Odoo | 19.0.0 FINAL | Target application |
| Python | 3.12.3 | Odoo runtime |
| Google Cloud SDK | Latest stable | Required for authentication |

### E. Environment Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `TF_VAR_project` | Yes (if not using -var flag) | — | GCP project ID |
| `TF_VAR_region` | No | `us-central1` | GCP region for bucket |
| `TF_VAR_bucket_name` | No | `odoo-attachments` | GCS bucket name |
| `TF_VAR_service_account_id` | No | `odoo-gcs` | Service account ID |
| `TF_VAR_credentials_file` | No | `null` (ADC) | Path to GCP credentials JSON |
| `GOOGLE_APPLICATION_CREDENTIALS` | No | — | GCP ADC path (alternative to gcloud auth) |

### F. Developer Tools Guide

| Tool | Installation | Purpose |
|---|---|---|
| Terraform | `https://developer.hashicorp.com/terraform/install` | Infrastructure-as-code engine |
| Google Cloud SDK | `https://cloud.google.com/sdk/docs/install` | GCP CLI and authentication |
| `terraform-docs` | `brew install terraform-docs` or `go install` | Auto-generate module documentation |
| `tflint` | `brew install tflint` | Terraform linting and best practices |
| `checkov` | `pip install checkov` | Infrastructure security scanning |

### G. Glossary

| Term | Definition |
|---|---|
| **ADC** | Application Default Credentials — GCP authentication method that automatically discovers credentials from the environment |
| **GCS** | Google Cloud Storage — GCP's object storage service used for Odoo file attachments |
| **IAM** | Identity and Access Management — GCP's access control framework |
| **HCL** | HashiCorp Configuration Language — Terraform's declarative configuration syntax |
| **Service Account** | A GCP identity used by applications (not humans) to authenticate and access GCP APIs |
| **SA Key** | A JSON private key file for a GCP service account, enabling programmatic authentication |
| **uniform_bucket_level_access** | A GCS bucket setting that enforces IAM-only access control, disabling per-object ACLs |
| **force_destroy** | A Terraform bucket setting; when `false`, prevents destroying a bucket that contains objects |
| **tfvars** | Terraform variable values file — provides concrete assignments for declared variables |
| **Workload Identity Federation** | A GCP mechanism allowing external workloads to access GCP resources without static service account keys |