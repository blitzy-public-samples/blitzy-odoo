variable "project" {
  description = "The GCP project ID where resources will be created"
  type        = string
}

variable "region" {
  description = "The GCP region for the storage bucket"
  type        = string
  default     = "us-central1"
}

variable "bucket_name" {
  description = "The name of the GCS bucket for Odoo attachments"
  type        = string
  default     = "odoo-attachments"
}

variable "service_account_id" {
  description = "The account ID for the GCP service account"
  type        = string
  default     = "odoo-gcs"
}

variable "credentials_file" {
  description = "Path to the GCP credentials JSON file. Defaults to null to use Application Default Credentials (ADC)"
  type        = string
  default     = null
}
