provider "aws" {
  region                      = var.aws_region
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  s3_use_path_style           = true

  endpoints {
    iam            = "http://localhost:4566"
    s3             = "http://localhost:4566"
    ses            = "http://localhost:4566"
    secretsmanager = "http://localhost:4566"
  }
}
