# -----------------------------------------------------------------------
# main.tf — Core GCP resource definitions for Odoo GCS attachment storage
#
# This file provisions the following GCP infrastructure:
#   1. A Google Cloud Storage bucket for Odoo file attachments
#   2. A dedicated GCP service account for programmatic access
#   3. A service account key for authentication from Odoo
#   4. An IAM binding granting the service account object-admin on the bucket
#
# Resource dependency graph:
#   google_storage_bucket (independent)
#   google_service_account (independent)
#     └── google_service_account_key (depends on SA)
#   google_storage_bucket_iam_member (depends on bucket + SA)
# -----------------------------------------------------------------------

# ---------- 1. GCS Bucket ----------
# Provisions the Cloud Storage bucket where Odoo stores file attachments.
# - Versioning is enabled to protect against accidental overwrites/deletions.
# - force_destroy is false so Terraform will refuse to destroy a bucket that
#   still contains objects, preventing catastrophic data loss.
# - Uniform bucket-level access enforces IAM-only permissions (no ACLs),
#   aligning with GCP security best practices.
resource "google_storage_bucket" "odoo_attachments" {
  name                        = var.bucket_name
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# ---------- 2. Service Account ----------
# Creates a dedicated GCP service account that Odoo uses to authenticate
# against the Cloud Storage API.  Scoping credentials to a single-purpose
# service account follows the principle of least privilege.
resource "google_service_account" "odoo_gcs_sa" {
  account_id   = var.service_account_id
  display_name = "Odoo GCS Service Account"
}

# ---------- 3. Service Account Key ----------
# Generates a JSON private key for the service account.  The key material
# is stored in Terraform state and exposed as a sensitive output so it can
# be injected into Odoo's configuration (or a secret manager) without
# appearing in plan/apply logs.
resource "google_service_account_key" "odoo_gcs_key" {
  service_account_id = google_service_account.odoo_gcs_sa.name
}

# ---------- 4. IAM Binding ----------
# Grants the service account the "roles/storage.objectAdmin" role on the
# provisioned bucket.  This role includes all storage.objects.* permissions
# (create, read, update, delete, list) scoped exclusively to this bucket,
# without granting any project-wide storage access.
resource "google_storage_bucket_iam_member" "odoo_gcs_admin" {
  bucket = google_storage_bucket.odoo_attachments.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.odoo_gcs_sa.email}"
}
