# Odoo S3 Attachment Storage — Terraform Module

This Terraform module provisions an Amazon S3 bucket (`odoo-attachments`) with versioning
enabled and an IAM user (`odoo-s3`) with least-privilege S3 access, targeting a
**LocalStack development environment** at `localhost:4566`.

Use this module to stand up the complete S3 attachment storage infrastructure required by
Odoo without needing a real AWS account.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Terraform 1.1.3** | Exact version required (pinned in `versions.tf`). Download from [releases.hashicorp.com](https://releases.hashicorp.com/terraform/1.1.3/). |
| **Running LocalStack instance** | Accessible at `http://localhost:4566`. Start via `docker compose up -d` from the `blitzy-localstack/` directory (see `blitzy-localstack/docker-compose.yml`). |
| **awslocal CLI** *(optional)* | Used for verification commands. Install with `pip install awscli-local`. |

---

## Module Structure

```
terraform/odoo-s3/
├── versions.tf        # Terraform and provider version constraints
├── provider.tf        # AWS provider targeting LocalStack (localhost:4566)
├── variables.tf       # Input variable declarations
├── terraform.tfvars   # Default variable values
├── main.tf            # All AWS resource definitions (6 resources)
├── outputs.tf         # Exported values (bucket name, IAM credentials)
└── README.md          # This file
```

---

## Provisioned Resources

The module creates exactly **6 AWS resources**:

| # | Resource | Terraform Name | Description |
|---|----------|----------------|-------------|
| 1 | `aws_s3_bucket` | `odoo_attachments` | S3 bucket named `odoo-attachments` for Odoo file attachment storage. |
| 2 | `aws_s3_bucket_versioning` | `odoo_attachments` | Enables versioning on the S3 bucket so object history is preserved. |
| 3 | `aws_iam_user` | `odoo_s3_user` | IAM user named `odoo-s3` for programmatic S3 access. |
| 4 | `aws_iam_access_key` | `odoo_s3_key` | Programmatic access key (ID + secret) for the IAM user. |
| 5 | `aws_iam_policy` | `odoo_s3_policy` | Least-privilege policy granting `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, and `s3:ListBucket` scoped to the bucket and its objects. |
| 6 | `aws_iam_user_policy_attachment` | `odoo_s3_attach` | Binds the S3 policy to the IAM user. |

---

## Usage

### Initialize, Plan, and Apply

```bash
cd terraform/odoo-s3

# Download the hashicorp/aws provider
terraform init

# Preview the 6 resources that will be created
terraform plan

# Create all resources (no interactive prompt)
terraform apply -auto-approve
```

`terraform plan` should report **6 to add, 0 to change, 0 to destroy**.

### Retrieve Outputs

```bash
# Bucket name
terraform output bucket_name

# IAM access key ID
terraform output iam_access_key_id

# IAM secret access key (sensitive — use -json to reveal)
terraform output -json iam_secret_access_key
```

---

## Verification

After applying, verify the provisioned resources using the `awslocal` CLI:

```bash
# Confirm the S3 bucket exists
awslocal s3 ls
# Expected output includes: odoo-attachments

# Confirm the IAM user exists
awslocal iam list-users
# Expected output includes user: odoo-s3

# Confirm versioning is enabled on the bucket
awslocal s3api get-bucket-versioning --bucket odoo-attachments
# Expected: { "Status": "Enabled" }
```

### Full S3 Lifecycle Test

Use credentials from `terraform output -json` to perform a complete object lifecycle test:

```bash
# Upload a test file
echo "hello" > /tmp/test.txt
awslocal s3 cp /tmp/test.txt s3://odoo-attachments/test.txt

# List bucket contents
awslocal s3 ls s3://odoo-attachments/

# Download and verify
awslocal s3 cp s3://odoo-attachments/test.txt /tmp/test-download.txt
cat /tmp/test-download.txt
# Expected: hello

# Clean up
awslocal s3 rm s3://odoo-attachments/test.txt
```

---

## Outputs

| Output | Description | Sensitive |
|--------|-------------|-----------|
| `bucket_name` | Name of the created S3 bucket (`odoo-attachments`). | No |
| `iam_access_key_id` | Access key ID for the `odoo-s3` IAM user. | No |
| `iam_secret_access_key` | Secret access key for the `odoo-s3` IAM user. Use `terraform output -json` to retrieve. | **Yes** |

---

## Odoo Connection

After applying the module, add the following keys to `debian/odoo.conf` under the
`[options]` section to connect Odoo to the provisioned S3 bucket:

```ini
; S3 storage – LocalStack dev defaults (override in production via env vars)
aws_access_key_id = test
aws_secret_access_key = test
aws_region = us-east-1
aws_s3_bucket = odoo-attachments
```

> **Note:** These are LocalStack development defaults. In production, override these
> values via environment variables with real AWS credentials and the appropriate region
> and bucket name.

---

## Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `bucket_name` | `string` | `"odoo-attachments"` | Name of the S3 bucket to create. |
| `iam_user_name` | `string` | `"odoo-s3"` | Name of the IAM user for programmatic access. |
| `aws_region` | `string` | `"us-east-1"` | AWS region for the provider configuration. |

Default values are set in `terraform.tfvars` and can be overridden at plan/apply time:

```bash
terraform apply -var="bucket_name=my-custom-bucket"
```

---

## Teardown

To destroy all resources provisioned by this module:

```bash
terraform destroy -auto-approve
```

The module is fully **idempotent** — `terraform destroy` followed by `terraform apply`
both complete without error. No manual cleanup is required.

---

## Security Notes

- The `iam_secret_access_key` output is marked `sensitive = true` in Terraform to
  prevent accidental exposure in logs and CLI output.
- The IAM policy follows the **principle of least privilege**: only `s3:GetObject`,
  `s3:PutObject`, `s3:DeleteObject`, and `s3:ListBucket` are granted, scoped
  exclusively to the `odoo-attachments` bucket and its objects.
- No wildcard `s3:*` or `iam:*` permissions are used.
- The LocalStack development credentials (`test`/`test`) must **never** be used in
  production. Always override via environment variables with real AWS credentials.
