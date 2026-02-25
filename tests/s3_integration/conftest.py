"""Pytest fixtures for S3 integration tests.

Provides the ``aws_s3`` and ``filesystem_storage`` fixtures used by the
S3 integration test suite.  The ``aws_s3`` fixture activates Moto's
in-process AWS mock, provisions a test bucket, and yields a boto3 S3
client for assertions.  The ``filesystem_storage`` fixture ensures the
S3 backend is *not* activated so that the original filesystem code path
executes.
"""

import boto3
import pytest
from moto import mock_aws


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
    monkeypatch.setenv('IR_ATTACHMENT_STORAGE', 's3')
    monkeypatch.setenv('AWS_S3_BUCKET', 'odoo-attachments')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'test')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'test')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.delenv('AWS_ENDPOINT_URL', raising=False)

    with mock_aws():
        client = boto3.client('s3', region_name='us-east-1')
        client.create_bucket(Bucket='odoo-attachments')
        yield client


@pytest.fixture
def filesystem_storage(monkeypatch):
    """Ensure the S3 backend is *not* activated.

    Removes ``IR_ATTACHMENT_STORAGE`` from the environment (if present)
    so the conditional check ``os.environ.get('IR_ATTACHMENT_STORAGE')
    == 's3'`` evaluates to ``False``, causing the original filesystem
    code path to execute.

    Used exclusively by ``test_filesystem_fallback`` to validate that
    the S3 branch is never entered when the environment variable is
    absent.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var.
    monkeypatch.delenv('IR_ATTACHMENT_STORAGE', raising=False)
    yield
