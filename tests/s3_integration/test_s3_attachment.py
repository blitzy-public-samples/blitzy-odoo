"""
True Odoo-to-S3 integration tests for ``ir.attachment``.

Every test exercises the **actual** ``ir.attachment`` model methods
(``_file_write``, ``_file_read``, ``_file_delete``) through the Odoo ORM.
``boto3`` is used **only** for post-condition verification — never for the
operations under test.

All six AAP §0.7.3 scenarios are covered:

=====  =============================  ============================================
  #    Scenario                       How it is triggered
=====  =============================  ============================================
  1    Bucket auto-creation           ``ir.attachment.create(…)`` triggers
                                      ``_get_s3_client()`` which auto-creates the
                                      bucket idempotently.
  2    File write                     ``ir.attachment.create(…)`` — internally
                                      calls ``_file_write(raw, checksum)``.
  3    File read integrity            ``attach.raw`` access — triggers
                                      ``_file_read(store_fname)`` via ORM.
  4    File delete                    ``_file_delete(store_fname)`` called
                                      through the model.
  5    Missing file graceful error    ``_file_read(nonexistent_key)`` — returns
                                      ``b''`` without raising.
  6    Filesystem fallback            ``ir.attachment.create(…)`` with
                                      ``IR_ATTACHMENT_STORAGE`` unset — data
                                      lands on disk, **not** in S3.
=====  =============================  ============================================

Performance assertions
~~~~~~~~~~~~~~~~~~~~~~
Each operation is wrapped in a ``time.monotonic()`` delta check
(≤ 500 ms).  The timing covers the full ORM call, not a raw ``boto3``
call.

Prerequisites
~~~~~~~~~~~~~
* ``IR_ATTACHMENT_STORAGE=s3`` must be set in the process environment.
* LocalStack must be running (health-check fixture handles gating).
* Odoo base module must be installed in the test database
  (``--odoo-database``).
"""
# S3 storage backend — see IR_ATTACHMENT_STORAGE env var

import base64
import hashlib
import os
import time

import pytest
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Test 1: Bucket Auto-Creation
# ---------------------------------------------------------------------------

def test_bucket_auto_creation(odoo_env, s3_client, s3_bucket):
    """Bucket exists after an ORM create triggers the S3 backend; repeat
    calls are idempotent.

    Pass condition (AAP §0.7.3 scenario 1): Bucket exists after Odoo init,
    idempotent on repeat calls.
    """
    data = b"bucket auto-creation test payload"
    b64_data = base64.b64encode(data).decode()

    start = time.monotonic()
    odoo_env["ir.attachment"].create({
        "name": "test_bucket_auto_creation.txt",
        "datas": b64_data,
    })
    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"ORM create took {elapsed:.3f}s, exceeding 500 ms limit"
    )

    # Post-condition: the bucket must exist in S3
    buckets = s3_client.list_buckets()
    bucket_names = [b["Name"] for b in buckets["Buckets"]]
    assert s3_bucket in bucket_names, (
        f"Bucket '{s3_bucket}' not found after ORM create. Available: {bucket_names}"
    )

    # Idempotent: importing and calling the lazy initialiser again must not raise
    from odoo.addons.base.models.ir_attachment import _get_s3_client
    _get_s3_client()  # no-op — bucket already exists


# ---------------------------------------------------------------------------
# Test 2: File Write
# ---------------------------------------------------------------------------

def test_file_write(odoo_env, s3_client, s3_bucket):
    """S3 object exists at ``{checksum[:2]}/{checksum}`` after
    ``ir.attachment.create(…)``.

    Pass condition (AAP §0.7.3 scenario 2): Object exists in S3 at
    expected key after ``_file_write``.
    """
    data = b"s3 file write integration test data"
    b64_data = base64.b64encode(data).decode()
    checksum = hashlib.sha1(data).hexdigest()
    expected_key = f"{checksum[:2]}/{checksum}"

    start = time.monotonic()
    attach = odoo_env["ir.attachment"].create({
        "name": "test_file_write.bin",
        "datas": b64_data,
    })
    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"ORM create took {elapsed:.3f}s, exceeding 500 ms limit"
    )

    # The ORM record should reference the expected key
    assert attach.store_fname == expected_key, (
        f"store_fname mismatch: expected {expected_key!r}, got {attach.store_fname!r}"
    )

    # Post-condition: object exists in S3 at the expected key
    head = s3_client.head_object(Bucket=s3_bucket, Key=expected_key)
    assert head["ContentLength"] == len(data), (
        f"Expected ContentLength {len(data)}, got {head['ContentLength']}"
    )


# ---------------------------------------------------------------------------
# Test 3: File Read Integrity (SHA-1 verification)
# ---------------------------------------------------------------------------

def test_file_read_integrity(odoo_env, s3_client, s3_bucket):
    """Content read back through the ORM matches the original data via
    SHA-1 hash comparison.

    Round-trip:
      1. ``ir.attachment.create(…)``  →  data lands in S3
      2. ``attach.raw``               →  triggers ``_file_read``
      3. SHA-1(retrieved) == SHA-1(original)

    Pass condition (AAP §0.7.3 scenario 3): Content retrieved by
    ``_file_read`` matches original via SHA-1 hash comparison.
    """
    original_data = b"integrity check data for s3 read via odoo orm"
    b64_data = base64.b64encode(original_data).decode()
    original_checksum = hashlib.sha1(original_data).hexdigest()

    attach = odoo_env["ir.attachment"].create({
        "name": "test_read_integrity.dat",
        "datas": b64_data,
    })

    # Invalidate computed-field cache so _compute_raw triggers _file_read
    attach.invalidate_recordset(["raw"])

    # Read back through the ORM — this triggers _file_read from S3
    start = time.monotonic()
    retrieved_data = attach.raw
    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"ORM raw read took {elapsed:.3f}s, exceeding 500 ms limit"
    )

    # SHA-1 integrity verification
    retrieved_checksum = hashlib.sha1(retrieved_data).hexdigest()
    assert retrieved_checksum == original_checksum, (
        f"SHA-1 mismatch: expected {original_checksum}, got {retrieved_checksum}"
    )

    # Byte-exact equality
    assert retrieved_data == original_data, (
        "Retrieved bytes do not match the original data"
    )


# ---------------------------------------------------------------------------
# Test 4: File Delete
# ---------------------------------------------------------------------------

def test_file_delete(odoo_env, s3_client, s3_bucket):
    """S3 object is absent after ``_file_delete``.

    Sequence:
      1. ``ir.attachment.create(…)``  →  data lands in S3
      2. Confirm the object exists    (post-condition ``head_object``)
      3. ``_file_delete(store_fname)``
      4. Confirm the object is absent (``head_object`` raises 404)

    Pass condition (AAP §0.7.3 scenario 4): Object absent from S3 after
    ``_file_delete``.
    """
    data = b"data to be deleted via odoo _file_delete"
    b64_data = base64.b64encode(data).decode()
    checksum = hashlib.sha1(data).hexdigest()
    expected_key = f"{checksum[:2]}/{checksum}"

    attach = odoo_env["ir.attachment"].create({
        "name": "test_file_delete.bin",
        "datas": b64_data,
    })

    # Pre-condition: object must exist in S3 after create
    s3_client.head_object(Bucket=s3_bucket, Key=expected_key)  # must not raise

    # Delete through the ORM model method
    start = time.monotonic()
    odoo_env["ir.attachment"]._file_delete(expected_key)
    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"_file_delete took {elapsed:.3f}s, exceeding 500 ms limit"
    )

    # Post-condition: object must be absent in S3
    with pytest.raises(ClientError) as exc_info:
        s3_client.head_object(Bucket=s3_bucket, Key=expected_key)

    error_code = exc_info.value.response["Error"]["Code"]
    assert error_code in ("404", "NoSuchKey"), (
        f"Expected 404/NoSuchKey after delete, got error code: {error_code}"
    )


# ---------------------------------------------------------------------------
# Test 5: Missing File Graceful Error
# ---------------------------------------------------------------------------

def test_missing_file_error(odoo_env):
    """``_file_read`` on a nonexistent S3 key returns ``b''`` — not an
    unhandled exception.

    The S3 backend in ``_file_read`` catches ``ClientError`` with code
    ``NoSuchKey`` and degrades gracefully to ``b''``, mirroring the
    existing filesystem behaviour.

    Pass condition (AAP §0.7.3 scenario 5): ``_file_read`` on nonexistent
    key raises graceful error, not unhandled exception.
    """
    missing_key = "ff/ffffffffffffffffffffffffffffffffffffffff"

    start = time.monotonic()
    result = odoo_env["ir.attachment"]._file_read(missing_key)
    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"_file_read (missing key) took {elapsed:.3f}s, exceeding 500 ms limit"
    )

    assert result == b"", (
        f"Expected b'' for missing S3 key, got: {result!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: Filesystem Fallback (no S3 calls when env var is unset)
# ---------------------------------------------------------------------------

def test_filesystem_fallback(odoo_env, s3_client, s3_bucket):
    """When ``IR_ATTACHMENT_STORAGE`` is **not** ``'s3'``, the attachment
    data lands on the local filesystem and **no** S3 object is created.

    Sequence:
      1. Remove ``IR_ATTACHMENT_STORAGE`` from the process environment
      2. ``ir.attachment.create(…)``  →  data goes to the local filestore
      3. ``head_object`` on the would-be S3 key confirms absence (404)

    Pass condition (AAP §0.7.3 scenario 6): When ``IR_ATTACHMENT_STORAGE``
    is unset, existing filesystem path executes and S3 is not called.
    """
    original_value = os.environ.pop("IR_ATTACHMENT_STORAGE", None)

    try:
        data = b"filesystem fallback test data - no s3"
        b64_data = base64.b64encode(data).decode()
        checksum = hashlib.sha1(data).hexdigest()
        expected_key = f"{checksum[:2]}/{checksum}"

        start = time.monotonic()
        attach = odoo_env["ir.attachment"].create({
            "name": "test_filesystem_fallback.txt",
            "datas": b64_data,
        })
        elapsed = time.monotonic() - start
        assert elapsed <= 0.5, (
            f"ORM create (filesystem path) took {elapsed:.3f}s, exceeding 500 ms limit"
        )

        # The store_fname should still be set (filesystem uses same format)
        assert attach.store_fname, "store_fname should be set for filesystem storage"

        # Post-condition: the object must NOT exist in S3
        with pytest.raises(ClientError) as exc_info:
            s3_client.head_object(Bucket=s3_bucket, Key=expected_key)

        error_code = exc_info.value.response["Error"]["Code"]
        assert error_code in ("404", "NoSuchKey"), (
            f"Expected S3 object to be absent (404/NoSuchKey), got: {error_code}"
        )

    finally:
        # Restore the original environment variable
        if original_value is not None:
            os.environ["IR_ATTACHMENT_STORAGE"] = original_value
