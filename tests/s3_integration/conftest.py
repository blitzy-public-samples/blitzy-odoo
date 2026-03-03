"""Pytest fixtures for S3 integration tests.

Provides the ``aws_s3``, ``attachment``, and ``filesystem_attachment``
fixtures used by the S3 integration test suite.

* ``aws_s3``               — Moto ``mock_aws`` context with pre-provisioned
                             bucket; yields a ``boto3`` S3 client for
                             assertions.
* ``attachment``           — ``IrAttachment`` stub whose *real*
                             ``_file_write``, ``_file_read``,
                             ``_file_delete``, and ``_get_s3_client``
                             methods are bound so they execute production
                             code, while ``isinstance(stub, IrAttachment)``
                             returns ``True``.  Active inside the
                             ``mock_aws`` context provided by ``aws_s3``.
* ``filesystem_attachment`` — Same stub technique but with
                             ``IR_ATTACHMENT_STORAGE`` **unset** and the
                             Odoo-ORM filesystem helpers (``_get_path``,
                             ``_mark_for_gc``) mocked to work without a
                             running Odoo server.  ``mock_aws`` is still
                             active so the test can verify that no S3
                             object was created.
"""

import os
import types
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from odoo.addons.base.models.ir_attachment import IrAttachment

# ---------------------------------------------------------------------------
# Constants — bucket name shared with test_s3_attachment.py
# ---------------------------------------------------------------------------
BUCKET_NAME = "odoo-attachments"

# Real IrAttachment methods that are bound onto every stub.
_REAL_METHODS = ("_get_s3_client", "_file_write", "_file_read", "_file_delete")


# ---------------------------------------------------------------------------
# pytest-odoo override — skip Odoo ORM / database initialisation
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def load_registry():
    """Override pytest-odoo's ``load_registry`` to skip Odoo initialisation.

    The S3 integration tests run independently of the Odoo ORM and do not
    require a database connection or module registry.  Without this
    override, ``pytest-odoo``'s session-scoped ``load_registry`` fixture
    attempts to call ``odoo.tests.common.get_db_name()`` which fails in
    a standalone pytest context.
    """
    yield


# ---------------------------------------------------------------------------
# Internal helper — create a stub that passes isinstance(x, IrAttachment)
# ---------------------------------------------------------------------------
def _make_stub():
    """Return a ``MagicMock(spec=IrAttachment)`` with real S3 methods bound.

    ``MagicMock(spec=...)`` makes ``isinstance()`` return ``True`` for
    the spec class.  We then replace the auto-mocked attributes with
    the *real* unbound functions from ``IrAttachment``, bound as instance
    methods via ``types.MethodType``.  The result is an object that:

    * passes ``assert isinstance(self, IrAttachment)`` inside the methods
    * executes production code for S3 operations (``boto3`` calls)
    * does **not** require Odoo ORM, database, or registry
    """
    stub = MagicMock(spec=IrAttachment)
    for name in _REAL_METHODS:
        setattr(stub, name, types.MethodType(getattr(IrAttachment, name), stub))
    return stub


# ---------------------------------------------------------------------------
# Fixture: aws_s3 — Moto mock + pre-provisioned bucket + boto3 client
# ---------------------------------------------------------------------------
@pytest.fixture
def aws_s3(monkeypatch):
    """Activate Moto S3 mock with all required environment variables.

    This fixture:

    1. Sets every environment variable that ``_get_s3_client()`` and the
       conditional S3 branches in ``_file_write``, ``_file_read``, and
       ``_file_delete`` read at call time.
    2. **Deletes** ``AWS_ENDPOINT_URL`` to guarantee that no stale
       LocalStack (or other custom-endpoint) value bypasses Moto
       interception.
    3. Enters the ``mock_aws()`` context so that **every** ``boto3``
       client created while the context is active is transparently
       intercepted by Moto — including clients returned by
       ``_get_s3_client()`` inside the code under test.
    4. Creates the ``odoo-attachments`` bucket so that tests begin with
       a clean, pre-provisioned state.
    5. Yields the fixture's own S3 client for direct assertion queries.

    When the ``with mock_aws()`` block exits, all mock state is
    automatically torn down and ``monkeypatch`` restores every
    environment variable to its original value.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    monkeypatch.setenv("IR_ATTACHMENT_STORAGE", "s3")
    monkeypatch.setenv("AWS_S3_BUCKET", BUCKET_NAME)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET_NAME)
        yield client


# ---------------------------------------------------------------------------
# Fixture: attachment — IrAttachment stub with real S3 methods
# ---------------------------------------------------------------------------
@pytest.fixture
def attachment(aws_s3):
    """IrAttachment stub with real S3 methods, usable under active ``mock_aws``.

    Depends on ``aws_s3`` so that the Moto context and environment
    variables are already configured before the stub is created.  Tests
    receive both ``aws_s3`` (for assertions) and ``attachment`` (for
    calling the methods under test).
    """
    return _make_stub()


# ---------------------------------------------------------------------------
# Fixture: filesystem_attachment — fallback test (IR_ATTACHMENT_STORAGE unset)
# ---------------------------------------------------------------------------
@pytest.fixture
def filesystem_attachment(monkeypatch, tmp_path):
    """IrAttachment stub for filesystem-fallback testing.

    ``mock_aws`` **is** active so the test can query S3 and confirm that
    **no** objects were created.  ``IR_ATTACHMENT_STORAGE`` is deliberately
    **unset** so that the conditional branches in ``_file_write`` (and
    friends) fall through to the filesystem code path.

    Odoo-ORM helpers that the filesystem path calls (``_get_path``,
    ``_mark_for_gc``) are replaced with lightweight mocks backed by
    ``tmp_path`` so the methods execute successfully without a running
    Odoo server.

    Yields ``(stub, s3_client)`` so the test can call the production
    method **and** verify S3 state afterwards.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    monkeypatch.delenv("IR_ATTACHMENT_STORAGE", raising=False)
    monkeypatch.setenv("AWS_S3_BUCKET", BUCKET_NAME)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_ENDPOINT_URL", raising=False)

    with mock_aws():
        s3_client = boto3.client("s3", region_name="us-east-1")
        s3_client.create_bucket(Bucket=BUCKET_NAME)

        stub = _make_stub()

        # ----- mock Odoo-ORM filesystem helpers -----
        def _mock_get_path(bin_data, sha):
            """Replicate ``_get_path`` using ``tmp_path`` instead of Odoo filestore."""
            fname = sha[:2] + "/" + sha
            full_path = str(tmp_path / sha[:2] / sha)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            return fname, full_path

        stub._get_path = _mock_get_path
        stub._mark_for_gc = MagicMock()

        yield stub, s3_client
