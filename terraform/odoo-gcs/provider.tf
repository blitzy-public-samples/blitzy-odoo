# -----------------------------------------------------------------------------
# Google Cloud Provider Configuration
# -----------------------------------------------------------------------------
# Configures Terraform to communicate with Google Cloud Platform APIs.
#
# Authentication:
#   - When var.credentials_file is set to a path, Terraform uses that JSON key
#     file to authenticate against GCP.
#   - When var.credentials_file is null (the default), Terraform falls back to
#     Application Default Credentials (ADC). This is the recommended
#     authentication method for CI/CD pipelines running on GCP (e.g., Cloud
#     Build, GitHub Actions with Workload Identity Federation).
# -----------------------------------------------------------------------------

provider "google" {
  project     = var.project
  region      = var.region
  credentials = var.credentials_file
}
