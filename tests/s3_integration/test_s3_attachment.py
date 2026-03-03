"""S3 integration tests for ``IrAttachment._file_write``, ``_file_read``,
and ``_file_delete``.

Every test invokes one of those three methods as its **primary action**
with Moto's ``mock_aws`` active, so Moto intercepts the ``boto3`` calls
that ``ir_attachment.py`` makes internally.

``boto3`` is used in tests **only** for setup (pre-writing objects to S3)
and assertions (verifying object existence / absence) — never as the
thing being tested.

Each test docstring states the specific bug in ``ir_attachment.py`` it
would catch and how.

Test command::

    pytest tests/s3_integration/ -v
"""

import hashlib
import time

import boto3
import pytest
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Constants — kept in sync with conftest.py ``aws_s3`` fixture
# ---------------------------------------------------------------------------
BUCKET_NAME = "odoo-attachments"


# ---------------------------------------------------------------------------
# Scenario 1 — Bucket auto-creation is idempotent
# ---------------------------------------------------------------------------
def test_bucket_auto_creation_idempotent(aws_s3, attachment):
    """Primary action: ``_file_write`` (invoked twice).

    Bug caught
    ~~~~~~~~~~
    If ``_get_s3_client()`` does **not** catch ``BucketAlreadyOwnedByYou``
    / ``BucketAlreadyExists`` from the ``create_bucket`` call that runs on
    every client instantiation, the *second* ``_file_write`` invocation
    would crash with an unhandled ``ClientError`` because the ``aws_s3``
    fixture already provisioned the bucket before the test started.

    How it catches the bug: Each ``_file_write`` call internally invokes
    ``self._get_s3_client()``, which attempts ``create_bucket``.  The
    bucket was already created by the fixture, so the ``except
    ClientError`` handler in ``_get_s3_client()`` must silently swallow
    ``BucketAlreadyOwnedByYou`` / ``BucketAlreadyExists``.  If that
    handler is missing or mis-coded, the test fails with an unhandled
    exception.
    """
    start = time.monotonic()

    data = b"idempotency test payload"
    checksum = hashlib.sha1(data).hexdigest()

    # First _file_write: internally calls _get_s3_client() → create_bucket
    # (bucket already exists from fixture — must not crash)
    attachment._file_write(data, checksum)

    # Second _file_write: another fresh client, another create_bucket attempt
    fname = attachment._file_write(data, checksum)

    # Verify the object is accessible (proves both calls succeeded)
    response = aws_s3.get_object(Bucket=BUCKET_NAME, Key=fname)
    assert response["Body"].read() == data, (
        "Object should be readable after two idempotent _file_write calls"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"Bucket auto-creation took {elapsed:.3f}s, exceeding 500 ms threshold"
    )


# ---------------------------------------------------------------------------
# Scenario 2 — File write to S3
# ---------------------------------------------------------------------------
def test_file_write_to_s3(aws_s3, attachment):
    """Primary action: ``_file_write``.

    Bug caught
    ~~~~~~~~~~
    If ``_file_write`` does not call ``put_object`` in its S3 branch, or
    uses the wrong key format (e.g. omitting the ``{checksum[:2]}/``
    prefix), or targets the wrong bucket, the object will not exist at the
    expected S3 key after the call.

    How it catches the bug: The test calls ``_file_write(bin_value,
    checksum)`` and then uses the **fixture** boto3 client to
    ``get_object`` at the key that ``_file_write`` returned.  A mismatch
    in key format, missing ``put_object`` call, or wrong bucket causes
    the ``get_object`` assertion to fail.
    """
    start = time.monotonic()

    bin_value = b"test file content for write scenario"
    checksum = hashlib.sha1(bin_value).hexdigest()
    expected_key = f"{checksum[:2]}/{checksum}"

    # PRIMARY ACTION — invoke the production method
    fname = attachment._file_write(bin_value, checksum)

    # Assert key format matches specification
    assert fname == expected_key, (
        f"Expected key '{expected_key}', got '{fname}'"
    )

    # Assert object content via fixture client (boto3 for assertion only)
    response = aws_s3.get_object(Bucket=BUCKET_NAME, Key=fname)
    stored_data = response["Body"].read()
    assert stored_data == bin_value, (
        "Stored content should match the original binary value"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"File write took {elapsed:.3f}s, exceeding 500 ms threshold"
    )


# ---------------------------------------------------------------------------
# Scenario 3 — File read integrity via SHA-1
# ---------------------------------------------------------------------------
def test_file_read_integrity_sha1(aws_s3, attachment):
    """Primary action: ``_file_read``.

    Bug caught
    ~~~~~~~~~~
    If ``_file_read`` reads from the wrong S3 key, fails to call
    ``response['Body'].read()``, truncates the data, or returns stale /
    corrupted bytes, the SHA-1 digest of the returned content will not
    match the original checksum.

    How it catches the bug: The test first writes data via
    ``_file_write`` (setup), then reads it back via ``_file_read``
    (primary action) and recomputes SHA-1.  Any data corruption, wrong
    key lookup, or partial read causes the checksum comparison to fail.
    """
    start = time.monotonic()

    bin_value = b"integrity test data for SHA-1 verification"
    original_checksum = hashlib.sha1(bin_value).hexdigest()

    # Setup — write the object (so there is something to read)
    fname = attachment._file_write(bin_value, original_checksum)

    # PRIMARY ACTION — read via the production method
    read_data = attachment._file_read(fname)

    # Verify SHA-1 integrity
    read_checksum = hashlib.sha1(read_data).hexdigest()
    assert read_checksum == original_checksum, (
        f"SHA-1 mismatch: expected {original_checksum}, got {read_checksum}"
    )
    assert read_data == bin_value, (
        "Read-back bytes should be identical to the original payload"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"File read integrity check took {elapsed:.3f}s, exceeding 500 ms threshold"
    )


# ---------------------------------------------------------------------------
# Scenario 4 — File delete from S3
# ---------------------------------------------------------------------------
def test_file_delete_from_s3(aws_s3, attachment):
    """Primary action: ``_file_delete``.

    Bug caught
    ~~~~~~~~~~
    If ``_file_delete`` does not call ``delete_object`` in its S3 branch
    (e.g. it falls through to ``_mark_for_gc`` which only works on the
    local filesystem), or if it targets the wrong bucket / key, the
    object will persist in S3 after the call.

    How it catches the bug: The test writes an object via ``_file_write``
    (setup), invokes ``_file_delete(fname)`` (primary action), and then
    uses the fixture client to confirm the object is gone (``NoSuchKey``).
    If ``delete_object`` is never called, the final assertion fails
    because the object is still present.
    """
    start = time.monotonic()

    bin_value = b"data to be deleted"
    checksum = hashlib.sha1(bin_value).hexdigest()

    # Setup — write the object first
    fname = attachment._file_write(bin_value, checksum)

    # Verify object exists before deletion (sanity check via fixture client)
    pre_response = aws_s3.get_object(Bucket=BUCKET_NAME, Key=fname)
    assert pre_response["Body"].read() == bin_value, (
        "Object should be readable before deletion"
    )

    # PRIMARY ACTION — invoke the production delete method
    attachment._file_delete(fname)

    # Assert object is absent — must raise ClientError with NoSuchKey
    with pytest.raises(ClientError) as exc_info:
        aws_s3.get_object(Bucket=BUCKET_NAME, Key=fname)

    error_code = exc_info.value.response["Error"]["Code"]
    assert error_code == "NoSuchKey", (
        f"Expected 'NoSuchKey' error after deletion, got '{error_code}'"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"File delete took {elapsed:.3f}s, exceeding 500 ms threshold"
    )


# ---------------------------------------------------------------------------
# Scenario 5 — Missing file returns b'' (graceful error)
# ---------------------------------------------------------------------------
def test_missing_file_graceful_error(aws_s3, attachment):
    """Primary action: ``_file_read`` on a nonexistent S3 key.

    Bug caught
    ~~~~~~~~~~
    If ``_file_read`` does **not** wrap its ``get_object`` call in a
    ``try … except ClientError`` block, a missing S3 key will raise an
    unhandled ``ClientError`` instead of returning ``b''`` (which is the
    contract established by the filesystem code path on ``OSError``).

    How it catches the bug: The test calls ``_file_read`` with a key
    that was never written.  If the ``except ClientError`` handler is
    missing or incorrectly re-raises, the test fails with an unhandled
    exception rather than receiving ``b''``.
    """
    start = time.monotonic()

    # PRIMARY ACTION — read a key that does not exist in the bucket
    result = attachment._file_read("nonexistent/key")

    # Production _file_read must return b'' for missing keys (not raise)
    assert result == b"", (
        f"Expected b'' for missing S3 key, got {result!r}"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"Missing file error handling took {elapsed:.3f}s, exceeding 500 ms threshold"
    )


# ---------------------------------------------------------------------------
# Scenario 6 — Filesystem fallback when IR_ATTACHMENT_STORAGE is unset
# ---------------------------------------------------------------------------
def test_filesystem_fallback(filesystem_attachment):
    """Primary action: ``_file_write`` with ``IR_ATTACHMENT_STORAGE`` unset.

    Bug caught
    ~~~~~~~~~~
    If the conditional check in ``_file_write`` is wrong — for example,
    using a truthy check (``if os.environ.get('IR_ATTACHMENT_STORAGE')``)
    instead of the strict equality
    (``== 's3'``), or if the check is accidentally inverted — the S3
    code path would execute even when the environment variable is absent.

    How it catches the bug: The test calls ``_file_write`` **without**
    ``IR_ATTACHMENT_STORAGE`` set, then verifies via the fixture's boto3
    client that **zero** objects exist in S3.  If the S3 branch fires
    incorrectly, at least one S3 object will be found and the assertion
    fails.  The test does **not** assert boolean expressions about
    environment variables — it calls the real method and inspects S3
    state.
    """
    stub, s3_client = filesystem_attachment
    start = time.monotonic()

    data = b"filesystem fallback test data"
    checksum = hashlib.sha1(data).hexdigest()

    # PRIMARY ACTION — call _file_write (filesystem path expected)
    fname = stub._file_write(data, checksum)

    # fname should be the filesystem-style key, not an error
    expected_fname = f"{checksum[:2]}/{checksum}"
    assert fname == expected_fname, (
        f"Filesystem _file_write should return '{expected_fname}', got '{fname}'"
    )

    # ASSERTION — verify NO S3 object was created
    objects = s3_client.list_objects_v2(Bucket=BUCKET_NAME)
    key_count = objects.get("KeyCount", 0)
    assert key_count == 0, (
        f"S3 should have 0 objects when IR_ATTACHMENT_STORAGE is unset, "
        f"found {key_count} — the S3 branch executed incorrectly"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"Filesystem fallback check took {elapsed:.3f}s, exceeding 500 ms threshold"
    )


# ---------------------------------------------------------------------------
# Scenario 7 — Moto interception confirmed across clients
# ---------------------------------------------------------------------------
def test_moto_interception_confirmed(aws_s3, attachment):
    """Primary action: ``_file_write``.

    Bug caught
    ~~~~~~~~~~
    If ``_get_s3_client()`` caches the ``boto3`` client at module load
    time, at class level, or at instance level (instead of creating a
    fresh client per call), the client may have been instantiated
    **outside** the active ``mock_aws`` context.  In that case Moto
    cannot intercept the ``put_object`` call, and the object will not
    appear in the mock S3 state shared by the fixture's client.

    How it catches the bug: The test calls ``_file_write`` via the
    ``attachment`` stub (which internally calls ``_get_s3_client()`` →
    ``boto3.client('s3', …)`` each time).  It then reads the written
    object back using the **fixture** client (``aws_s3``).  If both
    clients do not share the same Moto mock state — meaning per-call
    instantiation is broken — the fixture client will get ``NoSuchKey``
    and the assertion fails.
    """
    start = time.monotonic()

    data = b"moto-interception-payload"
    checksum = hashlib.sha1(data).hexdigest()

    # PRIMARY ACTION — write via the production method
    fname = attachment._file_write(data, checksum)

    # Read the same object back via the FIXTURE client
    response = aws_s3.get_object(Bucket=BUCKET_NAME, Key=fname)
    body = response["Body"].read()
    assert body == data, (
        f"Expected {data!r} from fixture client, got {body!r} — "
        "Moto interception is NOT working: the client created by "
        "_get_s3_client() does not share mock state with the fixture client"
    )

    elapsed = time.monotonic() - start
    assert elapsed <= 0.5, (
        f"Moto interception test took {elapsed:.3f}s, exceeding 500 ms threshold"
    )
