#!/usr/bin/env bash
# =============================================================================
# Odoo S3 Terraform Module — Comprehensive Validation Script
# =============================================================================
# This script performs end-to-end validation of the Terraform-provisioned S3
# bucket and IAM resources running against a LocalStack development environment.
#
# Validation gates executed:
#   1. INFRASTRUCTURE — Verify bucket, IAM user, versioning via awslocal
#   2. LIFECYCLE       — Full S3 object lifecycle using IAM credentials from
#                        terraform output -json (upload → list → download →
#                        verify → delete)
#   3. IDEMPOTENCY     — terraform destroy + terraform apply round-trip with
#                        6-resource assertion
#
# Prerequisites:
#   - Terraform 1.1.3 installed and on PATH
#   - LocalStack running at localhost:4566
#   - awslocal (awscli-local) and jq installed
#   - terraform init already executed in this directory
#
# Exit codes:
#   0  — All checks passed
#   1  — One or more checks failed
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS_COUNT=0
FAIL_COUNT=0
TOTAL_CHECKS=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Print a formatted check result and update counters.
check_pass() {
    local label="$1"
    PASS_COUNT=$((PASS_COUNT + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo "  [PASS] ${label}"
}

check_fail() {
    local label="$1"
    local detail="${2:-}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    echo "  [FAIL] ${label}"
    if [[ -n "${detail}" ]]; then
        echo "         Detail: ${detail}"
    fi
}

section() {
    echo ""
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

# ---------------------------------------------------------------------------
# Gate 1: Infrastructure Verification
# ---------------------------------------------------------------------------
gate_infrastructure() {
    section "Gate 1: Infrastructure Verification"

    # 1a. S3 bucket exists
    local s3_ls
    s3_ls="$(awslocal s3 ls 2>&1)" || true
    if echo "${s3_ls}" | grep -q "odoo-attachments"; then
        check_pass "S3 bucket 'odoo-attachments' exists"
    else
        check_fail "S3 bucket 'odoo-attachments' NOT found in 'awslocal s3 ls'" "${s3_ls}"
    fi

    # 1b. IAM user exists
    local iam_users
    iam_users="$(awslocal iam list-users --output json 2>&1)" || true
    if echo "${iam_users}" | jq -e '.Users[] | select(.UserName=="odoo-s3")' >/dev/null 2>&1; then
        check_pass "IAM user 'odoo-s3' exists"
    else
        check_fail "IAM user 'odoo-s3' NOT found in 'awslocal iam list-users'" "${iam_users}"
    fi

    # 1c. Bucket versioning enabled
    local versioning
    versioning="$(awslocal s3api get-bucket-versioning --bucket odoo-attachments --output json 2>&1)" || true
    if echo "${versioning}" | jq -e '.Status == "Enabled"' >/dev/null 2>&1; then
        check_pass "Bucket versioning status is 'Enabled'"
    else
        check_fail "Bucket versioning status is NOT 'Enabled'" "${versioning}"
    fi

    # 1d. IAM policy exists
    local policies
    policies="$(awslocal iam list-policies --scope Local --output json 2>&1)" || true
    if echo "${policies}" | jq -e '.Policies[] | select(.PolicyName=="odoo-s3-policy")' >/dev/null 2>&1; then
        check_pass "IAM policy 'odoo-s3-policy' exists"
    else
        check_fail "IAM policy 'odoo-s3-policy' NOT found" "${policies}"
    fi
}

# ---------------------------------------------------------------------------
# Gate 2: S3 Lifecycle using Terraform-output Credentials
# ---------------------------------------------------------------------------
gate_lifecycle() {
    section "Gate 2: S3 Object Lifecycle (using Terraform credentials)"

    # Extract credentials from terraform output
    cd "${SCRIPT_DIR}"
    local tf_output
    tf_output="$(terraform output -json 2>&1)"

    local access_key_id secret_access_key bucket_name
    access_key_id="$(echo "${tf_output}" | jq -r '.iam_access_key_id.value')"
    secret_access_key="$(echo "${tf_output}" | jq -r '.iam_secret_access_key.value')"
    bucket_name="$(echo "${tf_output}" | jq -r '.bucket_name.value')"

    if [[ -z "${access_key_id}" || "${access_key_id}" == "null" ]]; then
        check_fail "Failed to extract iam_access_key_id from terraform output" "${tf_output}"
        return
    fi
    check_pass "Extracted IAM credentials from terraform output"

    # Configure AWS CLI environment for the lifecycle test
    export AWS_ACCESS_KEY_ID="${access_key_id}"
    export AWS_SECRET_ACCESS_KEY="${secret_access_key}"
    export AWS_DEFAULT_REGION="us-east-1"
    local ENDPOINT="--endpoint-url=http://localhost:4566"

    # 2a. Upload a test object
    local test_file="/tmp/odoo_s3_validate_test.txt"
    echo "Hello from Odoo S3 validation — $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${test_file}"

    if aws s3 cp "${test_file}" "s3://${bucket_name}/validate-test.txt" ${ENDPOINT} --no-sign-request=false 2>&1 | grep -q "upload"; then
        check_pass "Upload: validate-test.txt uploaded to s3://${bucket_name}/"
    else
        # Retry with path style
        if aws s3 cp "${test_file}" "s3://${bucket_name}/validate-test.txt" ${ENDPOINT} 2>&1; then
            check_pass "Upload: validate-test.txt uploaded to s3://${bucket_name}/ (retry)"
        else
            check_fail "Upload: Failed to upload validate-test.txt"
            return
        fi
    fi

    # 2b. List objects and verify test file appears
    local list_output
    list_output="$(aws s3 ls "s3://${bucket_name}/" ${ENDPOINT} 2>&1)" || true
    if echo "${list_output}" | grep -q "validate-test.txt"; then
        check_pass "List: validate-test.txt found in bucket listing"
    else
        check_fail "List: validate-test.txt NOT found in bucket listing" "${list_output}"
    fi

    # 2c. Download the object and verify content integrity
    local download_file="/tmp/odoo_s3_validate_download.txt"
    rm -f "${download_file}"
    if aws s3 cp "s3://${bucket_name}/validate-test.txt" "${download_file}" ${ENDPOINT} 2>&1 | grep -q "download"; then
        check_pass "Download: validate-test.txt downloaded successfully"
    else
        if aws s3 cp "s3://${bucket_name}/validate-test.txt" "${download_file}" ${ENDPOINT} 2>&1; then
            check_pass "Download: validate-test.txt downloaded successfully (retry)"
        else
            check_fail "Download: Failed to download validate-test.txt"
        fi
    fi

    # 2d. Verify content matches
    if [[ -f "${download_file}" ]]; then
        local original_hash downloaded_hash
        original_hash="$(md5sum "${test_file}" | awk '{print $1}')"
        downloaded_hash="$(md5sum "${download_file}" | awk '{print $1}')"
        if [[ "${original_hash}" == "${downloaded_hash}" ]]; then
            check_pass "Verify: Downloaded content matches uploaded content (MD5: ${original_hash})"
        else
            check_fail "Verify: Content mismatch — uploaded MD5=${original_hash}, downloaded MD5=${downloaded_hash}"
        fi
    else
        check_fail "Verify: Downloaded file does not exist at ${download_file}"
    fi

    # 2e. Delete the test object
    if aws s3 rm "s3://${bucket_name}/validate-test.txt" ${ENDPOINT} 2>&1 | grep -q "delete"; then
        check_pass "Delete: validate-test.txt removed from bucket"
    else
        if aws s3 rm "s3://${bucket_name}/validate-test.txt" ${ENDPOINT} 2>&1; then
            check_pass "Delete: validate-test.txt removed from bucket (retry)"
        else
            check_fail "Delete: Failed to remove validate-test.txt"
        fi
    fi

    # 2f. Confirm object is gone
    local post_delete_list
    post_delete_list="$(aws s3 ls "s3://${bucket_name}/" ${ENDPOINT} 2>&1)" || true
    if echo "${post_delete_list}" | grep -q "validate-test.txt"; then
        check_fail "Post-delete: validate-test.txt still present in bucket"
    else
        check_pass "Post-delete: validate-test.txt confirmed removed"
    fi

    # Clean up temp files
    rm -f "${test_file}" "${download_file}"

    # Unset credential overrides
    unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION
}

# ---------------------------------------------------------------------------
# Gate 3: Idempotency — destroy + apply round-trip
# ---------------------------------------------------------------------------
gate_idempotency() {
    section "Gate 3: Idempotency (destroy → apply round-trip)"

    cd "${SCRIPT_DIR}"

    # 3a. Destroy all resources
    local destroy_output
    destroy_output="$(terraform destroy -auto-approve -no-color 2>&1)"
    if echo "${destroy_output}" | grep -q "Destroy complete!"; then
        local destroyed_count
        destroyed_count="$(echo "${destroy_output}" | grep -oP '\d+ destroyed' | grep -oP '^\d+')" || destroyed_count="0"
        check_pass "Destroy: terraform destroy completed (${destroyed_count} destroyed)"
    else
        check_fail "Destroy: terraform destroy did not complete successfully" "$(echo "${destroy_output}" | tail -5)"
        return
    fi

    # 3b. Re-apply all resources
    local apply_output
    apply_output="$(terraform apply -auto-approve -no-color 2>&1)"
    if echo "${apply_output}" | grep -q "Apply complete!"; then
        local added_count
        added_count="$(echo "${apply_output}" | grep -oP '\d+ added' | grep -oP '^\d+')" || added_count="0"
        if [[ "${added_count}" == "6" ]]; then
            check_pass "Apply: terraform apply completed with exactly 6 resources added"
        else
            check_fail "Apply: Expected 6 resources added, got ${added_count}" "$(echo "${apply_output}" | grep -E 'added|changed|destroyed')"
        fi
    else
        check_fail "Apply: terraform apply did not complete successfully" "$(echo "${apply_output}" | tail -5)"
    fi

    # 3c. Verify resources exist again after re-apply
    local s3_ls
    s3_ls="$(awslocal s3 ls 2>&1)" || true
    if echo "${s3_ls}" | grep -q "odoo-attachments"; then
        check_pass "Post-apply: S3 bucket 'odoo-attachments' exists after round-trip"
    else
        check_fail "Post-apply: S3 bucket 'odoo-attachments' NOT found after round-trip"
    fi

    local iam_users
    iam_users="$(awslocal iam list-users --output json 2>&1)" || true
    if echo "${iam_users}" | jq -e '.Users[] | select(.UserName=="odoo-s3")' >/dev/null 2>&1; then
        check_pass "Post-apply: IAM user 'odoo-s3' exists after round-trip"
    else
        check_fail "Post-apply: IAM user 'odoo-s3' NOT found after round-trip"
    fi

    local versioning
    versioning="$(awslocal s3api get-bucket-versioning --bucket odoo-attachments --output json 2>&1)" || true
    if echo "${versioning}" | jq -e '.Status == "Enabled"' >/dev/null 2>&1; then
        check_pass "Post-apply: Bucket versioning 'Enabled' after round-trip"
    else
        check_fail "Post-apply: Bucket versioning NOT 'Enabled' after round-trip"
    fi
}

# ---------------------------------------------------------------------------
# Gate 4: Odoo Configuration Verification
# ---------------------------------------------------------------------------
gate_odoo_config() {
    section "Gate 4: Odoo Configuration (debian/odoo.conf)"

    local conf_file="${SCRIPT_DIR}/../../debian/odoo.conf"
    if [[ ! -f "${conf_file}" ]]; then
        check_fail "debian/odoo.conf not found at ${conf_file}"
        return
    fi

    # 4a. aws_access_key_id present
    if grep -q "^aws_access_key_id" "${conf_file}"; then
        check_pass "odoo.conf contains 'aws_access_key_id'"
    else
        check_fail "odoo.conf missing 'aws_access_key_id'"
    fi

    # 4b. aws_secret_access_key present
    if grep -q "^aws_secret_access_key" "${conf_file}"; then
        check_pass "odoo.conf contains 'aws_secret_access_key'"
    else
        check_fail "odoo.conf missing 'aws_secret_access_key'"
    fi

    # 4c. aws_region present
    if grep -q "^aws_region" "${conf_file}"; then
        check_pass "odoo.conf contains 'aws_region'"
    else
        check_fail "odoo.conf missing 'aws_region'"
    fi

    # 4d. aws_s3_bucket present
    if grep -q "^aws_s3_bucket" "${conf_file}"; then
        check_pass "odoo.conf contains 'aws_s3_bucket'"
    else
        check_fail "odoo.conf missing 'aws_s3_bucket'"
    fi

    # 4e. LocalStack dev comment present
    if grep -q "LocalStack dev" "${conf_file}"; then
        check_pass "odoo.conf contains LocalStack dev comment"
    else
        check_fail "odoo.conf missing LocalStack dev comment"
    fi
}

# ---------------------------------------------------------------------------
# Gate 5: Test Preservation
# ---------------------------------------------------------------------------
gate_preservation() {
    section "Gate 5: Test Preservation (blitzy-localstack/tests/)"

    cd "${SCRIPT_DIR}/../.."
    local changed_tests
    changed_tests="$(git diff --name-only -- blitzy-localstack/tests/ 2>&1)" || true
    if [[ -z "${changed_tests}" ]]; then
        check_pass "Zero files modified under blitzy-localstack/tests/"
    else
        check_fail "Files modified under blitzy-localstack/tests/" "${changed_tests}"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo "============================================================"
    echo "  Odoo S3 Terraform Module — Validation Suite"
    echo "  Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "============================================================"

    gate_infrastructure
    gate_lifecycle
    gate_idempotency
    gate_odoo_config
    gate_preservation

    echo ""
    echo "============================================================"
    echo "  SUMMARY"
    echo "============================================================"
    echo "  Total checks : ${TOTAL_CHECKS}"
    echo "  Passed       : ${PASS_COUNT}"
    echo "  Failed       : ${FAIL_COUNT}"
    echo "  Completed    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "============================================================"

    if [[ "${FAIL_COUNT}" -gt 0 ]]; then
        echo ""
        echo "  *** VALIDATION FAILED — ${FAIL_COUNT} check(s) did not pass ***"
        echo ""
        exit 1
    else
        echo ""
        echo "  *** ALL CHECKS PASSED — Module is fully validated ***"
        echo ""
        exit 0
    fi
}

main "$@"
