"""Pytest fixtures for the S3 integration test suite.

Provides ``aws_s3``, ``filesystem_storage``, and ``attachment_proxy`` fixtures
that configure environment variables, start/stop the Moto ``mock_aws``
context, provision the test bucket, and yield a boto3 S3 client for direct
assertions.

All S3 mocking is handled entirely in-process by Moto — no Docker or real
AWS infrastructure is required.
"""

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(scope='session', autouse=True)
def load_registry():
    """Override pytest-odoo's ``load_registry`` session fixture.

    The S3 integration tests exercise boto3/Moto operations directly
    and do not require the Odoo ORM registry or a PostgreSQL database.
    This no-op override prevents pytest-odoo from attempting to
    initialise the Odoo registry at session start.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    yield


@pytest.fixture(scope='module', autouse=True)
def enable_odoo_test_flag():
    """Override pytest-odoo's ``enable_odoo_test_flag`` module fixture.

    The S3 integration tests do not use Odoo's ``tools.config`` and
    therefore do not need the ``test_enable`` flag toggled.  This
    no-op override avoids the ``AttributeError`` that occurs when
    ``odoo.tools`` is not fully initialised.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    yield


@pytest.fixture(scope='module', autouse=True)
def load_http():
    """Override pytest-odoo's ``load_http`` module fixture.

    The S3 integration tests do not start or require an Odoo HTTP
    server.  This no-op override skips server startup entirely.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    yield


@pytest.fixture
def aws_s3(monkeypatch):
    """Fixture that provides a Moto-backed S3 client with all environment
    variables configured for the S3 storage backend.

    The fixture performs the following in strict order:
    1. Sets all required AWS / Odoo environment variables via ``monkeypatch``
    2. Explicitly removes ``AWS_ENDPOINT_URL`` to prevent stale LocalStack
       values from bypassing Moto interception
    3. Enters the ``mock_aws()`` context so every subsequent ``boto3.client``
       call is intercepted by Moto's in-process mock
    4. Creates a fresh boto3 S3 client **inside** the active mock context
       (per-call instantiation — never cached)
    5. Provisions the ``odoo-attachments`` bucket so tests start with a
       clean, pre-provisioned state
    6. Yields the client for test assertions
    7. On teardown the ``mock_aws`` context exits, discarding all mock state,
       and ``monkeypatch`` restores the original environment variables

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Built-in pytest fixture for safe environment variable manipulation.

    Yields
    ------
    botocore.client.S3
        A boto3 S3 client connected to the Moto in-process mock.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    monkeypatch.setenv('IR_ATTACHMENT_STORAGE', 's3')
    monkeypatch.setenv('AWS_S3_BUCKET', 'odoo-attachments')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'test')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'test')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    # CRITICAL: Remove AWS_ENDPOINT_URL to prevent stale LocalStack values
    # from bypassing Moto interception.  When set, boto3 reaches out to
    # that address instead of being intercepted by Moto.
    monkeypatch.delenv('AWS_ENDPOINT_URL', raising=False)

    with mock_aws():
        # Client MUST be created inside the active mock_aws() context.
        # Cached or pre-existing clients bypass Moto entirely.
        client = boto3.client('s3', region_name='us-east-1')
        # Idempotent bucket provisioning — tests begin with a clean bucket.
        client.create_bucket(Bucket='odoo-attachments')
        yield client


@pytest.fixture
def filesystem_storage(monkeypatch):
    """Fixture that ensures the S3 storage backend is **not** activated.

    Removes ``IR_ATTACHMENT_STORAGE`` from the environment so the
    conditional branch ``os.environ.get('IR_ATTACHMENT_STORAGE') == 's3'``
    evaluates to ``False``, forcing the filesystem fallback path.

    No ``mock_aws`` context is started because S3 mocking is unnecessary
    when the filesystem backend is in effect.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Built-in pytest fixture for safe environment variable manipulation.

    Yields
    ------
    None
        No client is needed for filesystem fallback testing.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    monkeypatch.delenv('IR_ATTACHMENT_STORAGE', raising=False)
    yield


@pytest.fixture
def attachment_proxy():
    """Provide a lightweight ``IrAttachment`` instance for calling
    ``_file_write``, ``_file_read``, and ``_file_delete`` without a
    running Odoo ORM or PostgreSQL database.

    The instance is created via ``object.__new__(IrAttachment)`` which
    bypasses ``__init__`` but satisfies the ``isinstance(self, IrAttachment)``
    assertions inside the S3 code path.  The real method implementations
    on the class (``_get_s3_client``, ``_ensure_s3_bucket``, etc.) are
    inherited automatically and fully functional for the S3 branch.

    Yields
    ------
    IrAttachment
        A bare ``IrAttachment`` instance suitable for unbound method calls.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    from odoo.addons.base.models.ir_attachment import IrAttachment  # noqa: PLC0415
    yield object.__new__(IrAttachment)
