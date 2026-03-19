output "bucket_name" {
  description = "The name of the created GCS bucket"
  value       = google_storage_bucket.odoo_attachments.name
}

output "service_account_email" {
  description = "The email address of the created service account"
  value       = google_service_account.odoo_gcs_sa.email
}

output "service_account_key" {
  description = "The base64-encoded JSON key for the service account"
  value       = google_service_account_key.odoo_gcs_key.private_key
  sensitive   = true
}

output "project" {
  description = "The GCP project ID"
  value       = var.project
}
