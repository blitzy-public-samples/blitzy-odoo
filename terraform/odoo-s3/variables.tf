variable "bucket_name" {
  description = "Name of the S3 bucket for Odoo attachments"
  type        = string
}

variable "iam_user_name" {
  description = "Name of the IAM user for S3 access"
  type        = string
}

variable "aws_region" {
  description = "AWS region for the provider"
  type        = string
  default     = "us-east-1"
}
