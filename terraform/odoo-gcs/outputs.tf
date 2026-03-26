# -----------------------------------------------------------------------------
# Odoo GCS Attachment Storage — Output Declarations
#
# Exports four critical resource attributes from the provisioned GCP
# infrastructure.  These outputs are consumed by Odoo configuration workflows,
# CI/CD pipelines, and operators who need to wire the GCS bucket into the
# Odoo 19.0 attachment storage subsystem.
#
# Outputs:
#   bucket_name           — Name of the GCS bucket (non-sensitive)
#   service_account_email — Email of the dedicated service account (non-sensitive)
#   service_account_key   — Base64-encoded JSON private key (SENSITIVE)
#   project               — GCP project ID that was targeted (non-sensitive)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# 1. Bucket Name
#
# The name of the provisioned GCS bucket where Odoo stores file attachments.
# Downstream consumers use this value to set the `cloud_storage_google_bucket_name`
# system parameter in Odoo or the `ir_attachment_location` config directive.
# -----------------------------------------------------------------------------
output "bucket_name" {
  description = "The name of the created GCS bucket"
  value       = google_storage_bucket.odoo_attachments.name
}

# -----------------------------------------------------------------------------
# 2. Service Account Email
#
# The email address of the dedicated GCP service account created for Odoo.
# This email can be referenced in additional IAM policies or audit logging
# configurations outside this module.
# -----------------------------------------------------------------------------
output "service_account_email" {
  description = "The email address of the created service account"
  value       = google_service_account.odoo_gcs_sa.email
}

# -----------------------------------------------------------------------------
# 3. Service Account Key (SENSITIVE)
#
# The base64-encoded JSON private key for the service account.  This key is
# used by Odoo's cloud_storage_google addon to authenticate against GCS.
#
# SECURITY: Marked sensitive = true to prevent the key from appearing in
# Terraform plan/apply output, CI/CD logs, or state file diffs.  Retrieve
# the decoded key with:
#
#   terraform output -raw service_account_key | base64 --decode > sa-key.json
#
# Store the decoded key securely (GCP Secret Manager, HashiCorp Vault, etc.)
# and never commit it to version control.
# -----------------------------------------------------------------------------
output "service_account_key" {
  description = "The base64-encoded JSON key for the service account"
  value       = google_service_account_key.odoo_gcs_key.private_key
  sensitive   = true
}

# -----------------------------------------------------------------------------
# 4. Project
#
# The GCP project ID that was targeted during this Terraform run.  Useful for
# downstream scripts and documentation that need to reference the project
# without re-reading the variable or Terraform state.
# -----------------------------------------------------------------------------
output "project" {
  description = "The GCP project ID"
  value       = var.project
}
