# -----------------------------------------------------------------------------
# Odoo GCS Attachment Storage — Core Resource Definitions
#
# This file provisions four GCP resources required for Odoo 19.0 to store
# file attachments externally in Google Cloud Storage (GCS):
#
#   1. google_storage_bucket        — GCS bucket for attachment objects
#   2. google_service_account       — Dedicated service account for Odoo
#   3. google_service_account_key   — JSON key for programmatic access
#   4. google_storage_bucket_iam_member — IAM binding granting objectAdmin
#
# Resource dependency graph:
#   bucket ──────────────────────┐
#   service_account ──┬──────────┼──> iam_member
#                     └──> key   │
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# 1. GCS Bucket
#
# Provisions the Cloud Storage bucket where Odoo file attachments are stored.
# - Versioning is enabled to protect against accidental overwrites/deletions.
# - Uniform bucket-level access enforces IAM-only access control (no ACLs).
# - force_destroy is false to prevent Terraform from deleting a non-empty bucket.
# -----------------------------------------------------------------------------
resource "google_storage_bucket" "odoo_attachments" {
  name                        = var.bucket_name
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# -----------------------------------------------------------------------------
# 2. GCP Service Account
#
# Creates a dedicated service account for Odoo to authenticate against GCS.
# This service account is granted object-level CRUD permissions on the bucket
# via the IAM member binding below.
# -----------------------------------------------------------------------------
resource "google_service_account" "odoo_gcs_sa" {
  account_id   = var.service_account_id
  display_name = "Odoo GCS Service Account"
}

# -----------------------------------------------------------------------------
# 3. Service Account Key
#
# Generates a JSON private key for the service account, enabling programmatic
# access from the Odoo application. The key material is exposed as a sensitive
# output in outputs.tf and must be securely stored (e.g., GCP Secret Manager).
# -----------------------------------------------------------------------------
resource "google_service_account_key" "odoo_gcs_key" {
  service_account_id = google_service_account.odoo_gcs_sa.name
}

# -----------------------------------------------------------------------------
# 4. IAM Member Binding
#
# Grants the service account the roles/storage.objectAdmin role on the GCS
# bucket. This role provides full CRUD permissions on objects within the bucket
# (storage.objects.*) without granting project-wide storage access, following
# the principle of least privilege.
# -----------------------------------------------------------------------------
resource "google_storage_bucket_iam_member" "odoo_gcs_admin" {
  bucket = google_storage_bucket.odoo_attachments.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.odoo_gcs_sa.email}"
}
