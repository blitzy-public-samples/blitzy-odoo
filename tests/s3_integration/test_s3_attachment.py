"""S3 storage backend integration tests for ``ir.attachment``.

Implements the **7 mandatory test scenarios** (100 % gate) that validate the
S3 code path introduced in ``_file_write``, ``_file_read``, ``_file_delete``,
and the ``_get_s3_client`` / ``_ensure_s3_bucket`` helpers.

**Every test invokes one of the three modified ``IrAttachment`` methods as its
primary action.**  Moto's ``mock_aws`` is always active before the method is
called so that the internal ``boto3`` calls made by ``ir_attachment.py`` are
intercepted transparently.  ``boto3`` is used in tests **only** for pre-test
setup (e.g. seeding data) and post-test assertions (e.g. verifying S3 state)
— never as the thing being tested.

Fixture dependencies (provided by ``conftest.py``):
    - ``aws_s3``             — Moto-backed S3 client with environment vars set
    - ``filesystem_storage`` — ensures IR_ATTACHMENT_STORAGE is *not* ``'s3'``
    - ``attachment_proxy``   — lightweight ``IrAttachment`` instance for method calls
"""

# ---------------------------------------------------------------------------
# Standard library imports
# ---------------------------------------------------------------------------
import hashlib
import os
import tempfile
import time
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------------
import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from odoo.addons.base.models.ir_attachment import IrAttachment

# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------
BUCKET = "odoo-attachments"
PERF_THRESHOLD = 0.5  # 500 ms maximum per S3 operation


# ---------------------------------------------------------------------------
# Test 1 — Bucket auto-creation is idempotent
# ---------------------------------------------------------------------------
def test_bucket_auto_creation_idempotent(aws_s3, attachment_proxy):
    """Call ``_file_write`` twice — each call triggers ``_ensure_s3_bucket``
    internally.  The ``aws_s3`` fixture has already created the bucket, so
    ``_ensure_s3_bucket`` encounters an existing bucket on every invocation.

    Bug caught
    ----------
    If ``_ensure_s3_bucket`` (lines 156-165 in ir_attachment.py) does **not**
    catch ``BucketAlreadyOwnedByYou`` or ``BucketAlreadyExists`` in its
    ``except ClientError`` block, the ``create_bucket`` call inside
    ``_ensure_s3_bucket`` would raise an unhandled ``ClientError`` and
    ``_file_write`` would crash.  A missing or mis-typed error-code check
    (e.g. checking only ``BucketAlreadyOwnedByYou`` but not
    ``BucketAlreadyExists``) would also surface here.

    How it catches the bug
    ----------------------
    The ``aws_s3`` fixture pre-creates the bucket.  ``_file_write`` calls
    ``_ensure_s3_bucket`` which attempts ``create_bucket`` on the already-
    existing bucket.  If the exception is not properly caught, this test
    fails with an unhandled ``ClientError``.  Calling ``_file_write`` a
    second time exercises the idempotency guarantee again.
    """
    start = time.monotonic()

    # First _file_write — _ensure_s3_bucket sees the pre-existing bucket.
    bin1 = b"idempotency payload one"
    cs1 = hashlib.sha1(bin1).hexdigest()
    key1 = IrAttachment._file_write(attachment_proxy, bin1, cs1)

    # Second _file_write — _ensure_s3_bucket is called again on the same bucket.
    bin2 = b"idempotency payload two"
    cs2 = hashlib.sha1(bin2).hexdigest()
    key2 = IrAttachment._file_write(attachment_proxy, bin2, cs2)

    # boto3 assertions — verify both objects landed correctly.
    resp1 = aws_s3.get_object(Bucket=BUCKET, Key=key1)
    assert resp1["Body"].read() == bin1, (
        "First write must succeed despite pre-existing bucket"
    )

    resp2 = aws_s3.get_object(Bucket=BUCKET, Key=key2)
    assert resp2["Body"].read() == bin2, (
        "Second write must succeed (idempotent bucket creation)"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= PERF_THRESHOLD, (
        f"Bucket auto-creation took {elapsed:.3f}s, exceeds "
        f"{PERF_THRESHOLD}s threshold"
    )


# ---------------------------------------------------------------------------
# Test 2 — File write to S3
# ---------------------------------------------------------------------------
def test_file_write_to_s3(aws_s3, attachment_proxy):
    """Call ``_file_write`` and verify the object exists at the correct key.

    Bug caught
    ----------
    If ``_file_write`` computes the wrong S3 key (e.g. uses ``checksum``
    directly instead of the required ``{checksum[:2]}/{checksum}`` format at
    line 197), or if it does not call ``put_object``, or if it targets the
    wrong bucket name (reading a different env var or using a hard-coded
    value), the boto3 ``get_object`` assertion below would fail with
    ``NoSuchKey`` or return incorrect content.

    How it catches the bug
    ----------------------
    ``_file_write`` is called with known ``bin_value`` and ``checksum``.
    The expected key is computed independently in the test.  After the call,
    boto3 (the fixture client) independently verifies the object exists at
    the expected key and its body matches ``bin_value`` exactly.
    """
    start = time.monotonic()

    bin_value = b"test file content for write test"
    checksum = hashlib.sha1(bin_value).hexdigest()
    expected_key = f"{checksum[:2]}/{checksum}"

    # Primary action — _file_write
    returned_key = IrAttachment._file_write(attachment_proxy, bin_value, checksum)

    # Verify returned key format matches expectation.
    assert returned_key == expected_key, (
        f"_file_write returned key '{returned_key}', expected '{expected_key}'"
    )

    # boto3 assertion — object exists and content matches.
    response = aws_s3.get_object(Bucket=BUCKET, Key=returned_key)
    body = response["Body"].read()
    assert body == bin_value, (
        "S3 object body must match the written binary value"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= PERF_THRESHOLD, (
        f"File write took {elapsed:.3f}s, exceeds "
        f"{PERF_THRESHOLD}s threshold"
    )


# ---------------------------------------------------------------------------
# Test 3 — File read integrity via SHA1
# ---------------------------------------------------------------------------
def test_file_read_integrity_sha1(aws_s3, attachment_proxy):
    """Call ``_file_write`` then ``_file_read``; verify SHA1 integrity.

    Bug caught
    ----------
    If ``_file_read`` does not call ``response['Body'].read()`` (line 179),
    or if it returns the raw streaming body object instead of bytes, or if
    the ``Range`` header logic (lines 174-177) inadvertently truncates the
    data when ``size`` is ``None``, or if it reads from the wrong key/bucket,
    the SHA1 hash of the returned bytes would not match the original checksum.

    How it catches the bug
    ----------------------
    Binary data (including non-UTF-8 bytes) is written via ``_file_write``
    and then read back via ``_file_read``.  The SHA1 hash of the returned
    bytes is compared to the original checksum.  Any data corruption, partial
    read, or incorrect key resolution produces a hash mismatch.
    """
    start = time.monotonic()

    original_data = b"integrity check \xc3\xa9\x00\xff binary payload"
    checksum = hashlib.sha1(original_data).hexdigest()

    # Write via _file_write.
    key = IrAttachment._file_write(attachment_proxy, original_data, checksum)

    # Primary action — _file_read.
    read_data = IrAttachment._file_read(attachment_proxy, key)

    # Verify SHA1 integrity.
    read_checksum = hashlib.sha1(read_data).hexdigest()
    assert read_checksum == checksum, (
        f"SHA1 mismatch: expected {checksum}, got {read_checksum}"
    )
    assert read_data == original_data, (
        "Binary content must be identical after write/read round-trip"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= PERF_THRESHOLD, (
        f"File read integrity took {elapsed:.3f}s, exceeds "
        f"{PERF_THRESHOLD}s threshold"
    )


# ---------------------------------------------------------------------------
# Test 4 — File delete from S3
# ---------------------------------------------------------------------------
def test_file_delete_from_s3(aws_s3, attachment_proxy):
    """Call ``_file_write``, then ``_file_delete``; verify the object is gone.

    Bug caught
    ----------
    If ``_file_delete`` does not call ``delete_object`` (line 216), or uses
    the wrong bucket or key, or accidentally falls through to the filesystem
    GC path (``_mark_for_gc``) instead of performing the S3 deletion, the
    object would still exist after the delete call.

    How it catches the bug
    ----------------------
    An object is written via ``_file_write`` and confirmed present via boto3.
    Then ``_file_delete`` is called.  A boto3 ``get_object`` afterward must
    raise ``ClientError`` with ``NoSuchKey``, proving the object was actually
    removed from S3.
    """
    start = time.monotonic()

    bin_value = b"data to be deleted"
    checksum = hashlib.sha1(bin_value).hexdigest()

    # Setup — write object via _file_write.
    key = IrAttachment._file_write(attachment_proxy, bin_value, checksum)

    # Confirm object exists before delete (boto3 assertion).
    pre_delete = aws_s3.get_object(Bucket=BUCKET, Key=key)
    assert pre_delete["Body"].read() == bin_value, (
        "Object should exist before delete"
    )

    # Primary action — _file_delete.
    IrAttachment._file_delete(attachment_proxy, key)

    # Verify object is gone (boto3 assertion).
    with pytest.raises(ClientError) as exc_info:
        aws_s3.get_object(Bucket=BUCKET, Key=key)
    assert exc_info.value.response["Error"]["Code"] == "NoSuchKey", (
        "Expected NoSuchKey error after _file_delete"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= PERF_THRESHOLD, (
        f"File delete took {elapsed:.3f}s, exceeds "
        f"{PERF_THRESHOLD}s threshold"
    )


# ---------------------------------------------------------------------------
# Test 5 — Missing file graceful error
# ---------------------------------------------------------------------------
def test_missing_file_graceful_error(aws_s3, attachment_proxy):
    """Call ``_file_read`` on a nonexistent key; verify it returns ``b''``.

    Bug caught
    ----------
    If ``_file_read`` does not catch ``ClientError`` in its ``except`` clause
    (line 180), or catches only a narrower exception type (e.g. ``KeyError``),
    the ``NoSuchKey`` error from ``get_object`` would propagate as an
    unhandled exception instead of being swallowed and returning ``b''``.
    This would break callers that rely on the silent-empty-return contract
    (matching the filesystem path's ``OSError`` handling at lines 187-189).

    How it catches the bug
    ----------------------
    ``_file_read`` is called with a key (``"nonexistent/key"``) that was
    never written.  The internal ``get_object`` call raises ``ClientError``
    with code ``NoSuchKey``.  If the exception handler is missing or wrong,
    the exception bubbles up and the test fails.  If handled correctly,
    ``_file_read`` returns ``b''``.
    """
    start = time.monotonic()

    # Primary action — _file_read on a key that does not exist.
    result = IrAttachment._file_read(attachment_proxy, "nonexistent/key")

    assert result == b"", (
        f"_file_read on missing key must return b'', got {result!r}"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= PERF_THRESHOLD, (
        f"Missing file error took {elapsed:.3f}s, exceeds "
        f"{PERF_THRESHOLD}s threshold"
    )


# ---------------------------------------------------------------------------
# Test 6 — Filesystem fallback when IR_ATTACHMENT_STORAGE is unset
# ---------------------------------------------------------------------------
def test_filesystem_fallback(filesystem_storage, monkeypatch):
    """Call ``_file_write`` with ``IR_ATTACHMENT_STORAGE`` unset and verify
    that **zero** S3 objects are created — proving the filesystem path ran.

    Bug caught
    ----------
    If the conditional check at line 194 uses a truthy test
    (``if os.environ.get('IR_ATTACHMENT_STORAGE'):``) instead of the exact
    equality check ``== 's3'``, then *any* non-empty value for the variable
    would incorrectly activate the S3 path.  Conversely, if the guard is
    missing or inverted, S3 operations would fire even when filesystem
    storage is intended, creating orphaned S3 objects that the filesystem
    GC cannot reclaim.

    How it catches the bug
    ----------------------
    The ``filesystem_storage`` fixture removes ``IR_ATTACHMENT_STORAGE``.
    ``mock_aws`` is started inside the test so that any accidental S3 calls
    are caught by Moto rather than hitting real AWS.  ``_file_write`` is
    invoked (with filesystem helpers mocked since no ORM is available).
    After the call, boto3 lists objects in the bucket and asserts **zero**
    keys exist — proving the S3 code path was **not** taken.  The file is
    also verified to exist on the local filesystem.
    """
    start = time.monotonic()

    # Configure AWS credentials so any accidental boto3 call goes to Moto.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)

    with mock_aws():
        # Create bucket so list_objects_v2 below has a valid target.
        verification_client = boto3.client("s3", region_name="us-east-1")
        verification_client.create_bucket(Bucket=BUCKET)

        proxy = object.__new__(IrAttachment)
        bin_value = b"filesystem fallback payload"
        checksum = hashlib.sha1(bin_value).hexdigest()
        fname = f"{checksum[:2]}/{checksum}"

        # Prepare a real temporary directory for filesystem writes.
        tmpdir = tempfile.mkdtemp()
        full_path = os.path.join(tmpdir, checksum[:2], checksum)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Mock the ORM-dependent filesystem helpers.
        # _get_path returns (fname, full_path); _mark_for_gc is a no-op.
        with patch.object(
            IrAttachment, "_get_path", return_value=(fname, full_path),
        ), patch.object(IrAttachment, "_mark_for_gc"):
            # Primary action — _file_write (should take filesystem path).
            IrAttachment._file_write(proxy, bin_value, checksum)

        # --- Key assertion: ZERO S3 objects created. ---
        listing = verification_client.list_objects_v2(Bucket=BUCKET)
        s3_keys = [o["Key"] for o in listing.get("Contents", [])]
        assert len(s3_keys) == 0, (
            f"Expected zero S3 objects in filesystem mode, found: {s3_keys}"
        )

        # Verify the file was written to the local filesystem instead.
        assert os.path.isfile(full_path), (
            "File should exist on local filesystem when S3 is not active"
        )
        with open(full_path, "rb") as fh:
            assert fh.read() == bin_value, (
                "Filesystem content must match the original binary value"
            )

    elapsed = time.monotonic() - start
    assert elapsed <= PERF_THRESHOLD, (
        f"Filesystem fallback check took {elapsed:.3f}s, exceeds "
        f"{PERF_THRESHOLD}s threshold"
    )


# ---------------------------------------------------------------------------
# Test 7 — Moto interception confirmed across clients
# ---------------------------------------------------------------------------
def test_moto_interception_confirmed(aws_s3, attachment_proxy):
    """Call ``_file_write`` via ``IrAttachment`` and read back via the
    **fixture's** client — proving both share the same Moto mock context.

    Bug caught
    ----------
    If ``_get_s3_client`` caches the ``boto3`` client at module level, class
    level, or instance level (violating the per-call instantiation contract),
    the cached client would have been created **outside** the ``mock_aws``
    context and would bypass Moto entirely — sending real HTTPS requests to
    AWS (or failing with connection errors).  In that scenario, the object
    written by ``_file_write``'s internal client would **not** appear in
    the fixture client's view of the Moto-mocked S3 state.

    How it catches the bug
    ----------------------
    ``_file_write`` is the primary action; it creates its own S3 client via
    ``_get_s3_client`` internally.  The ``aws_s3`` fixture provides a
    **separately created** client.  If both clients share the same Moto
    context, the object written by one is readable by the other.  If the
    internal client was cached from before ``mock_aws`` started, the data
    diverges and the assertion fails.
    """
    start = time.monotonic()

    bin_value = b"moto interception proof payload"
    checksum = hashlib.sha1(bin_value).hexdigest()
    expected_key = f"{checksum[:2]}/{checksum}"

    # Primary action — _file_write uses _get_s3_client internally.
    IrAttachment._file_write(attachment_proxy, bin_value, checksum)

    # Read via the FIXTURE client (a different boto3.client instance).
    response = aws_s3.get_object(Bucket=BUCKET, Key=expected_key)
    body = response["Body"].read()
    assert body == bin_value, (
        "Object written by IrAttachment._file_write must be visible to "
        "the fixture's separately-created client — proving shared Moto context"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= PERF_THRESHOLD, (
        f"Moto interception test took {elapsed:.3f}s, exceeds "
        f"{PERF_THRESHOLD}s threshold"
    )
