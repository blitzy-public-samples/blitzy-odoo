# -----------------------------------------------------------------------------
# Odoo S3 Attachment Storage — Core Infrastructure Resources
# -----------------------------------------------------------------------------
# This file provisions all AWS resources required for Odoo file attachment
# storage against a LocalStack development environment. It defines exactly
# 6 resources: an S3 bucket with versioning, and an IAM user with a
# least-privilege policy granting only the S3 actions needed by Odoo.
# -----------------------------------------------------------------------------

# ---------------------
# S3 Bucket Resources
# ---------------------

# Resource 1: S3 bucket for Odoo file attachments.
# The bucket name is driven by var.bucket_name (default: "odoo-attachments").
# Versioning is handled by a dedicated aws_s3_bucket_versioning resource below
# to maintain a clean separation of concerns and an explicit resource count.
resource "aws_s3_bucket" "odoo_attachments" {
  bucket        = var.bucket_name
  force_destroy = true
}

# Resource 2: Enable versioning on the Odoo attachments bucket.
# This is a separate resource (not inline) to ensure an explicit plan count
# of exactly 6 resource additions and to follow current Terraform AWS provider
# best practices for bucket sub-resource configuration.
resource "aws_s3_bucket_versioning" "odoo_attachments" {
  bucket = aws_s3_bucket.odoo_attachments.id

  versioning_configuration {
    status = "Enabled"
  }
}

# ---------------------
# IAM Resources
# ---------------------

# Resource 3: IAM user for programmatic S3 access from Odoo.
# The user name is driven by var.iam_user_name (default: "odoo-s3").
resource "aws_iam_user" "odoo_s3_user" {
  name = var.iam_user_name
}

# Resource 4: Programmatic access key for the IAM user.
# The generated key ID and secret are exposed via outputs.tf so that
# downstream tooling and the Odoo configuration can consume them.
resource "aws_iam_access_key" "odoo_s3_key" {
  user = aws_iam_user.odoo_s3_user.name
}

# Resource 5: Least-privilege IAM policy scoped to the Odoo attachments bucket.
# Two policy statements enforce the principle of least privilege:
#   - Statement 1 (object-level): s3:GetObject, s3:PutObject, s3:DeleteObject
#     scoped to all objects within the bucket (bucket ARN/*).
#   - Statement 2 (bucket-level): s3:ListBucket scoped to the bucket ARN itself.
# Uses jsonencode() for a clean, maintainable policy document.
resource "aws_iam_policy" "odoo_s3_policy" {
  name = "odoo-s3-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.odoo_attachments.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.odoo_attachments.arn
      }
    ]
  })
}

# Resource 6: Attach the S3 policy to the IAM user.
# This binding grants the odoo-s3 user the permissions defined above.
resource "aws_iam_user_policy_attachment" "odoo_s3_attach" {
  user       = aws_iam_user.odoo_s3_user.name
  policy_arn = aws_iam_policy.odoo_s3_policy.arn
}
