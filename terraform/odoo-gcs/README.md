# Odoo GCS Terraform Module

A self-contained Terraform module that provisions Google Cloud Platform (GCP) infrastructure for **Odoo 19.0** to store file attachments externally in Google Cloud Storage (GCS), replacing or augmenting the default filesystem-based attachment storage.

## Overview

This module creates the following GCP resources:

| Resource | Terraform Type | Purpose |
|---|---|---|
| **GCS Bucket** | `google_storage_bucket` | Stores Odoo file attachments with versioning enabled and uniform bucket-level access |
| **Service Account** | `google_service_account` | Dedicated identity for Odoo to authenticate with GCS |
| **Service Account Key** | `google_service_account_key` | JSON key for programmatic access from the Odoo application |
| **IAM Binding** | `google_storage_bucket_iam_member` | Grants `roles/storage.objectAdmin` on the bucket to the service account |

## Prerequisites

Before using this module, ensure the following requirements are met:

1. **Google Cloud SDK** (`gcloud`) is installed and authenticated:

   ```bash
   gcloud auth application-default login
   ```

2. **A GCP project** with billing enabled. Note the project ID — you will need it as an input variable.

3. **Cloud Storage API** enabled on the project:

   ```bash
   gcloud services enable storage.googleapis.com
   ```

4. **IAM API** enabled on the project:

   ```bash
   gcloud services enable iam.googleapis.com
   ```

5. **Terraform CLI** installed (version >= 1.0 recommended). Verify with:

   ```bash
   terraform version
   ```

## Usage

Follow the standard Terraform workflow to provision the infrastructure:

```bash
# 1. Navigate to the module directory
cd terraform/odoo-gcs

# 2. Initialize the module and download the Google provider
terraform init

# 3. Preview the infrastructure changes
terraform plan -var="project=YOUR_GCP_PROJECT_ID"

# 4. Apply the infrastructure changes
terraform apply -var="project=YOUR_GCP_PROJECT_ID"
```

> **Note:** The `project` variable is **required** and has no default value. You must supply your GCP project ID via the `-var` flag, a `*.tfvars` file, or the `TF_VAR_project` environment variable. All other variables have sensible defaults specified in `terraform.tfvars`.

To destroy the provisioned resources when no longer needed:

```bash
terraform destroy -var="project=YOUR_GCP_PROJECT_ID"
```

> **Warning:** The GCS bucket is configured with `force_destroy = false`. You must manually empty the bucket before Terraform can destroy it. This is a safety measure to prevent accidental deletion of Odoo file attachments.

## Input Variables

| Variable | Type | Default | Required | Description |
|---|---|---|---|---|
| `project` | `string` | — | **Yes** | The GCP project ID where resources will be created |
| `region` | `string` | `us-central1` | No | The GCP region for the storage bucket |
| `bucket_name` | `string` | `odoo-attachments` | No | The name of the GCS bucket for Odoo attachments |
| `service_account_id` | `string` | `odoo-gcs` | No | The account ID for the GCP service account |
| `credentials_file` | `string` | `null` | No | Path to a GCP credentials JSON file; defaults to `null` to use Application Default Credentials (ADC) |

### Overriding Variables

You can override any variable using one of the following methods:

- **Command-line flag:**

  ```bash
  terraform apply -var="project=my-gcp-project" -var="region=europe-west1" -var="bucket_name=my-odoo-bucket"
  ```

- **Environment variables:**

  ```bash
  export TF_VAR_project="my-gcp-project"
  export TF_VAR_region="europe-west1"
  terraform apply
  ```

- **Edit `terraform.tfvars`** directly for persistent non-sensitive overrides.

## Outputs

| Output | Description | Sensitive |
|---|---|---|
| `bucket_name` | The name of the created GCS bucket | No |
| `service_account_email` | The email address of the created service account | No |
| `service_account_key` | The base64-encoded JSON key for the service account | **Yes** |
| `project` | The GCP project ID used for resource creation | No |

To view a specific output after applying:

```bash
terraform output bucket_name
terraform output service_account_email
terraform output project
```

> **Note:** The `service_account_key` output is marked as `sensitive` in Terraform. Use the `-raw` flag to retrieve its value (see the next section).

## Extracting the Service Account Key

The `google_service_account_key` resource produces a **base64-encoded** JSON private key. To decode and save it to a file:

```bash
terraform output -raw service_account_key | base64 --decode > sa-key.json
```

Verify the key was decoded correctly:

```bash
cat sa-key.json | python3 -m json.tool
```

> **⚠ Security Warning:** The service account key grants programmatic access to the GCS bucket. Handle it with the same care as a password:
>
> - **Never** commit the decoded key (`sa-key.json`) to version control.
> - Store the key securely using [GCP Secret Manager](https://cloud.google.com/secret-manager) or [HashiCorp Vault](https://www.vaultproject.io/).
> - Rotate the key periodically and delete old keys from GCP.
> - In CI/CD pipelines, inject the key via environment variables or secret stores rather than persisting it on disk.

## Odoo Connection

After provisioning the infrastructure, configure Odoo to use the GCS bucket for attachment storage.

### Option 1: Configure via Odoo Settings UI (Recommended)

1. Install and enable the `cloud_storage_google` addon in your Odoo instance.

2. Navigate to **Settings → Technical → System Parameters** and set the following:

   | Parameter | Value |
   |---|---|
   | `cloud_storage_google_bucket_name` | The `bucket_name` output (e.g., `odoo-attachments`) |
   | `cloud_storage_google_account_info` | The full decoded contents of `sa-key.json` |

3. Retrieve the values from Terraform outputs:

   ```bash
   # Get the bucket name
   terraform output bucket_name

   # Get the decoded service account key JSON
   terraform output -raw service_account_key | base64 --decode
   ```

4. Paste the bucket name and the decoded key JSON into the corresponding system parameters in Odoo.

### Option 2: Configure via `debian/odoo.conf` (Deployment Templates)

For automated deployments, the `debian/odoo.conf` file includes placeholder settings for GCS integration:

```ini
; GCS attachment storage settings (placeholders — override in production)
ir_attachment_location = gs://odoo-attachments
google_drive_client_id =
google_drive_client_secret =
google_drive_token =
```

These placeholders are intended to be overridden in production environments via:

- Environment variables
- GCP Secret Manager
- Configuration management tools (Ansible, Chef, Puppet)
- Kubernetes ConfigMaps and Secrets

> **Note:** The `ir_attachment_location` setting in `odoo.conf` serves as a deployment template. The actual runtime behavior is controlled by the `ir.config_parameter` database record named `ir_attachment.location`. Ensure the corresponding system parameter is set in the Odoo database.

## Resources Created

This module provisions the following four GCP resources:

### `google_storage_bucket` — GCS Bucket

- **Name:** Configurable via `bucket_name` variable (default: `odoo-attachments`)
- **Location:** Configurable via `region` variable (default: `us-central1`)
- **Versioning:** Enabled — protects against accidental deletions and overwrites
- **Uniform Bucket-Level Access:** Enabled — enforces IAM-based access control instead of ACLs
- **Force Destroy:** Disabled (`false`) — prevents Terraform from destroying a bucket that contains objects

### `google_service_account` — Service Account

- **Account ID:** Configurable via `service_account_id` variable (default: `odoo-gcs`)
- **Display Name:** `Odoo GCS Service Account`
- **Purpose:** Provides a dedicated identity for Odoo to authenticate with GCS, following the principle of least privilege

### `google_service_account_key` — Service Account Key

- **Service Account:** References the service account created above
- **Key Type:** JSON (default)
- **Output:** Base64-encoded private key exposed as a sensitive Terraform output
- **Usage:** Decoded and provided to Odoo as the `cloud_storage_google_account_info` system parameter

### `google_storage_bucket_iam_member` — IAM Binding

- **Bucket:** References the GCS bucket created above
- **Role:** `roles/storage.objectAdmin` — grants full CRUD permissions on objects within the bucket
- **Member:** The service account created above
- **Scope:** Bucket-level only — does not grant project-wide storage access

## Security Notes

- **Sensitive Output:** The `service_account_key` output is marked with `sensitive = true` in Terraform. This prevents the private key from being displayed in `terraform plan` or `terraform apply` output and in CI/CD logs.

- **Key Management:** Never commit the decoded service account key to version control. In production environments, use [GCP Secret Manager](https://cloud.google.com/secret-manager) or [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation) instead of static service account keys.

- **Bucket Protection:** The `force_destroy = false` setting on the GCS bucket prevents accidental deletion of buckets containing Odoo file attachments. To destroy the bucket, you must first remove all objects from it.

- **IAM Best Practices:** The module follows the principle of least privilege by granting `roles/storage.objectAdmin` only on the specific bucket (not project-wide) and only to the dedicated service account.

- **Application Default Credentials (ADC):** The `credentials_file` variable defaults to `null`, which causes the Google provider to use ADC. This is the recommended authentication method for CI/CD pipelines running on GCP (e.g., Cloud Build, GitHub Actions with Workload Identity Federation).

## License

This Terraform module is part of the Odoo 19.0 repository and is subject to the same licensing terms as the parent project.
