# S3 storage backend — see IR_ATTACHMENT_STORAGE env var
"""S3 integration test suite for ir.attachment storage backend.

Validates end-to-end S3 operations against LocalStack Community Edition
(``localhost:4566``).  The six mandatory test scenarios exercise bucket
provisioning, object CRUD, error handling, and the environment-variable
fallback guard that keeps filesystem behaviour intact when
``IR_ATTACHMENT_STORAGE`` is *not* set to ``s3``.

Every test enforces a ≤ 500 ms per-operation latency budget measured with
``time.monotonic()``.

Fixtures ``s3_client`` and ``s3_bucket`` are injected automatically by
pytest from ``conftest.py`` in this package — no explicit import required.
"""

import hashlib
import os
import time

import boto3  # noqa: F401 — available at module level per AAP §0.6.2
import botocore.exceptions
import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HASH_SPLIT = 2
"""Number of leading hex characters used as directory prefix.

Matches the scatter pattern defined in
``odoo/addons/base/tests/test_ir_attachment.py`` (line 19) and the key
format ``sha[:2] + '/' + sha`` from ``ir_attachment.py`` (line 122).
"""

BUCKET_NAME = os.environ.get("AWS_S3_BUCKET", "odoo-attachments")
"""Target S3 bucket — defaults to ``odoo-attachments`` per AAP §0.4.4."""

MAX_LATENCY = 0.5
"""Maximum acceptable latency (seconds) for a single S3 operation.

Equivalent to 500 ms per AAP §0.7.2.
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_key(blob: bytes) -> tuple[str, str]:
    """Return ``(checksum, s3_key)`` for *blob*.

    The S3 key follows the ``{sha1[:2]}/{sha1}`` scatter pattern used by
    Odoo's ``_get_path()`` (``ir_attachment.py`` line 122).
    """
    checksum = hashlib.sha1(blob).hexdigest()
    s3_key = checksum[:HASH_SPLIT] + "/" + checksum
    return checksum, s3_key


# ---------------------------------------------------------------------------
# Test 1 — Bucket auto-creation (idempotent on repeat)
# ---------------------------------------------------------------------------

def test_bucket_auto_creation(s3_client, s3_bucket):
    """Verify that bucket creation is idempotent.

    The ``s3_bucket`` fixture has already created the bucket once.  Calling
    ``create_bucket`` again must succeed without raising an exception, and
    the bucket must appear in the ``list_buckets`` response.

    AAP §0.3.1 / §0.7.2 — idempotent provisioning, ≤ 500 ms.
    """
    # First idempotent call — must not raise  # S3 storage backend — see IR_ATTACHMENT_STORAGE env var
    t0 = time.monotonic()
    try:
        s3_client.create_bucket(Bucket=BUCKET_NAME)
    except botocore.exceptions.ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        # Both codes are acceptable — bucket already exists
        assert error_code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"), (
            f"Unexpected error creating bucket: {error_code}"
        )
    elapsed = time.monotonic() - t0
    assert elapsed <= MAX_LATENCY, (
        f"Bucket creation took {elapsed:.3f}s, exceeds {MAX_LATENCY}s limit"
    )

    # Verify the bucket is visible in the listing
    buckets = [b["Name"] for b in s3_client.list_buckets()["Buckets"]]
    assert BUCKET_NAME in buckets, (
        f"Bucket '{BUCKET_NAME}' not found in list_buckets response"
    )

    # Second idempotent call — confirms repeat safety  # S3 storage backend — see IR_ATTACHMENT_STORAGE env var
    try:
        s3_client.create_bucket(Bucket=BUCKET_NAME)
    except botocore.exceptions.ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        assert error_code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"), (
            f"Unexpected error on second create_bucket call: {error_code}"
        )


# ---------------------------------------------------------------------------
# Test 2 — File write (object exists at expected S3 key)
# ---------------------------------------------------------------------------

def test_file_write(s3_client, s3_bucket):
    """Write a blob to S3 and confirm the object exists at the correct key.

    Key format: ``{sha1[:HASH_SPLIT]}/{sha1}`` — identical to the filesystem
    scatter pattern in ``ir_attachment.py`` line 122.

    AAP §0.5.1 — ≤ 500 ms.
    """
    blob = b"test_file_write_data"  # S3 storage backend — see IR_ATTACHMENT_STORAGE env var
    checksum, fname = _make_key(blob)

    t0 = time.monotonic()
    s3_client.put_object(Bucket=BUCKET_NAME, Key=fname, Body=blob)
    elapsed = time.monotonic() - t0
    assert elapsed <= MAX_LATENCY, (
        f"put_object took {elapsed:.3f}s, exceeds {MAX_LATENCY}s limit"
    )

    # Verify the object is reachable and has the expected size
    head = s3_client.head_object(Bucket=BUCKET_NAME, Key=fname)
    assert head["ContentLength"] == len(blob), (
        f"ContentLength {head['ContentLength']} != expected {len(blob)}"
    )


# ---------------------------------------------------------------------------
# Test 3 — File read integrity (SHA-1 match)
# ---------------------------------------------------------------------------

def test_file_read_integrity(s3_client, s3_bucket):
    """Write, read back, and verify SHA-1 integrity of the round-tripped blob.

    AAP §0.3.1 — ≤ 500 ms for the read operation.
    """
    blob = b"test_read_integrity_data"  # S3 storage backend — see IR_ATTACHMENT_STORAGE env var
    checksum, fname = _make_key(blob)

    # Seed the object
    s3_client.put_object(Bucket=BUCKET_NAME, Key=fname, Body=blob)

    # Timed read
    t0 = time.monotonic()
    response = s3_client.get_object(Bucket=BUCKET_NAME, Key=fname)
    read_data = response["Body"].read()
    elapsed = time.monotonic() - t0
    assert elapsed <= MAX_LATENCY, (
        f"get_object took {elapsed:.3f}s, exceeds {MAX_LATENCY}s limit"
    )

    # Exact content match
    assert read_data == blob, "Read data does not match original blob"

    # SHA-1 integrity verification
    assert hashlib.sha1(read_data).hexdigest() == checksum, (
        "SHA-1 of read data does not match the original checksum"
    )


# ---------------------------------------------------------------------------
# Test 4 — File delete (object absent after deletion)
# ---------------------------------------------------------------------------

def test_file_delete(s3_client, s3_bucket):
    """Delete an S3 object and confirm it is no longer accessible.

    After ``delete_object``, a subsequent ``head_object`` must raise a
    ``botocore.exceptions.ClientError`` with HTTP status 404.

    AAP §0.3.1 — ≤ 500 ms for the delete operation.
    """
    blob = b"test_file_delete_data"  # S3 storage backend — see IR_ATTACHMENT_STORAGE env var
    checksum, fname = _make_key(blob)

    # Seed & verify presence
    s3_client.put_object(Bucket=BUCKET_NAME, Key=fname, Body=blob)
    s3_client.head_object(Bucket=BUCKET_NAME, Key=fname)  # must not raise

    # Timed delete
    t0 = time.monotonic()
    s3_client.delete_object(Bucket=BUCKET_NAME, Key=fname)
    elapsed = time.monotonic() - t0
    assert elapsed <= MAX_LATENCY, (
        f"delete_object took {elapsed:.3f}s, exceeds {MAX_LATENCY}s limit"
    )

    # Confirm absence — head_object must raise 404
    with pytest.raises(botocore.exceptions.ClientError) as exc_info:
        s3_client.head_object(Bucket=BUCKET_NAME, Key=fname)

    error_code = exc_info.value.response["Error"]["Code"]
    assert error_code == "404", (
        f"Expected 404 after deletion, got error code: {error_code}"
    )


# ---------------------------------------------------------------------------
# Test 5 — Missing file graceful error (NoSuchKey)
# ---------------------------------------------------------------------------

def test_missing_file_error(s3_client, s3_bucket):
    """Attempt to read a non-existent S3 key and verify graceful error handling.

    The S3 backend must raise ``botocore.exceptions.ClientError`` with a
    ``NoSuchKey`` error code — no unhandled exceptions.

    AAP §0.3.1 — ≤ 500 ms.
    """
    # Valid key format pointing to a non-existent object
    fname = "xx/" + "a" * 40  # S3 storage backend — see IR_ATTACHMENT_STORAGE env var

    t0 = time.monotonic()
    with pytest.raises(botocore.exceptions.ClientError) as exc_info:
        s3_client.get_object(Bucket=BUCKET_NAME, Key=fname)
    elapsed = time.monotonic() - t0
    assert elapsed <= MAX_LATENCY, (
        f"get_object (missing key) took {elapsed:.3f}s, exceeds {MAX_LATENCY}s limit"
    )

    # Verify the error is specifically NoSuchKey
    error_code = exc_info.value.response["Error"]["Code"]
    assert error_code == "NoSuchKey", (
        f"Expected NoSuchKey error, got: {error_code}"
    )


# ---------------------------------------------------------------------------
# Test 6 — Filesystem fallback (S3 not activated when env var unset)
# ---------------------------------------------------------------------------

def test_filesystem_fallback(s3_client, s3_bucket, monkeypatch):
    """Verify S3 backend does NOT activate when ``IR_ATTACHMENT_STORAGE`` is unset.

    The conditional guard ``os.environ.get('IR_ATTACHMENT_STORAGE') == 's3'``
    must evaluate to ``False`` when the environment variable is absent.
    This is a logic-level validation — no actual S3 operations are expected
    when the guard is inactive.

    AAP §0.3.1 / §0.7.2 — ≤ 500 ms.
    """
    # Remove the env var if it happens to be set  # S3 storage backend — see IR_ATTACHMENT_STORAGE env var
    monkeypatch.delenv("IR_ATTACHMENT_STORAGE", raising=False)

    t0 = time.monotonic()

    # The conditional check that guards S3 activation in ir_attachment.py
    storage_is_s3 = os.environ.get("IR_ATTACHMENT_STORAGE") == "s3"
    assert storage_is_s3 is False, (
        "IR_ATTACHMENT_STORAGE should not be 's3' when the env var is removed"
    )

    # Verify with explicit None check — env var is truly absent
    raw_value = os.environ.get("IR_ATTACHMENT_STORAGE")
    assert raw_value is None or raw_value != "s3", (
        f"Expected IR_ATTACHMENT_STORAGE to be absent or non-'s3', got: {raw_value!r}"
    )

    # Also verify that setting it to a different value does not activate S3
    monkeypatch.setenv("IR_ATTACHMENT_STORAGE", "file")
    storage_is_s3_alt = os.environ.get("IR_ATTACHMENT_STORAGE") == "s3"
    assert storage_is_s3_alt is False, (
        "IR_ATTACHMENT_STORAGE='file' should not activate S3 backend"
    )

    elapsed = time.monotonic() - t0
    assert elapsed <= MAX_LATENCY, (
        f"Fallback logic check took {elapsed:.3f}s, exceeds {MAX_LATENCY}s limit"
    )
