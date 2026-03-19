# -----------------------------------------------------------------------------
# Google Cloud Provider Configuration
# -----------------------------------------------------------------------------
# Configures the Google Cloud provider for Terraform to authenticate and
# communicate with GCP APIs. Supports Application Default Credentials (ADC)
# for CI/CD environments by defaulting credentials to null.
#
# When var.credentials_file is null (the default), the provider falls back
# to ADC — the recommended authentication method for CI/CD pipelines running
# on GCP (e.g., Cloud Build, GitHub Actions with Workload Identity Federation).
# -----------------------------------------------------------------------------

provider "google" {
  project     = var.project
  region      = var.region
  credentials = var.credentials_file
}
