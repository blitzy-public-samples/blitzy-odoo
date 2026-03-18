output "bucket_name" {
  description = "Name of the S3 bucket for Odoo attachments"
  value       = aws_s3_bucket.odoo_attachments.bucket
}

output "iam_access_key_id" {
  description = "IAM access key ID for the odoo-s3 user"
  value       = aws_iam_access_key.odoo_s3_key.id
}

output "iam_secret_access_key" {
  description = "IAM secret access key for the odoo-s3 user"
  value       = aws_iam_access_key.odoo_s3_key.secret
  sensitive   = true
}
