# S3 storage backend — see IR_ATTACHMENT_STORAGE env var
"""Pytest fixtures for S3 integration tests against LocalStack."""

import contextlib
import os
import time

import boto3
import botocore.exceptions
import pytest
import requests

# Optional: attempt to import LocalStack testing utilities from the git submodule.
# These are not required — the core fixtures defined here are fully self-contained.
with contextlib.suppress(ImportError):
    from localstack.testing.pytest import fixtures  # noqa: F401


@pytest.fixture(autouse=True, scope="session")
def load_registry():
    """Override pytest-odoo's ``load_registry`` to prevent Odoo ORM initialization.

    The S3 integration tests are standalone and do **not** require Odoo's
    registry or database.  The ``pytest-odoo`` plugin (installed per
    AAP §0.6.1) registers an ``autouse=True, scope=session`` fixture of the
    same name that calls ``odoo.modules.registry.Registry(db_name)``; this
    override shadows it so that the S3 test session can run without an Odoo
    server.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var
    yield


@pytest.fixture(autouse=True, scope="module")
def enable_odoo_test_flag():
    """Override pytest-odoo's ``enable_odoo_test_flag`` to avoid accessing Odoo config.

    The ``pytest-odoo`` plugin registers a ``scope=module, autouse=True``
    fixture that sets ``odoo.tools.config['test_enable']``.  Since the S3
    integration tests do not use Odoo's tool chain, this override provides
    a no-op replacement preventing the ``AttributeError`` on ``odoo.tools``.
    """
    # S3 storage backend — see IR_ATTACHMENT_STORAGE env var
    yield


@pytest.fixture(autouse=True, scope="session")
def localstack_health_gate():
    """Gate all S3 integration tests on LocalStack S3 availability.

    Polls the LocalStack health endpoint at ``http://localhost:4566/_localstack/health``
    every second for up to 30 seconds. If the S3 service does not report
    ``"available"`` or ``"running"`` within the deadline the entire test session
    is skipped via ``pytest.skip``.

    This fixture is **autouse** and **session-scoped** so it executes once,
    before any test in the ``tests/s3_integration`` package runs.
    """
    health_url = "http://localhost:4566/_localstack/health"
    deadline = time.monotonic() + 30  # 30-second hard timeout

    while time.monotonic() < deadline:
        try:
            resp = requests.get(health_url, timeout=2)
            data = resp.json()
            s3_status = data.get("services", {}).get("s3")
            if s3_status in ("available", "running"):
                return  # S3 is ready — allow tests to proceed
        except (requests.ConnectionError, requests.Timeout, ValueError):
            # LocalStack not reachable yet or response not valid JSON — retry
            pass
        time.sleep(1)

    pytest.skip("LocalStack S3 not available")


@pytest.fixture(scope="session")
def s3_client():
    """Provide a session-scoped boto3 S3 client configured for LocalStack.

    All connection parameters are read from environment variables with
    dev/test defaults matching the AAP §0.4.4 configuration table:

    * ``AWS_ENDPOINT_URL``      → ``http://localhost:4566``
    * ``AWS_ACCESS_KEY_ID``     → ``test``
    * ``AWS_SECRET_ACCESS_KEY`` → ``test``
    * ``AWS_DEFAULT_REGION``    → ``us-east-1``

    The returned client works identically against LocalStack (dev/test) and
    real AWS (production) — only the environment variables differ.
    """
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


@pytest.fixture(scope="session")
def s3_bucket(s3_client):
    """Auto-provision the S3 bucket used for attachment storage.

    Creates the bucket named by ``AWS_S3_BUCKET`` (default ``odoo-attachments``)
    using an idempotent ``create_bucket`` call.  If the bucket already exists
    the ``BucketAlreadyOwnedByYou`` / ``BucketAlreadyExists`` client errors
    are silently suppressed so this fixture is safe to call on every session.

    Returns the bucket name string for use in test assertions.
    """
    bucket_name = os.environ.get("AWS_S3_BUCKET", "odoo-attachments")
    try:
        s3_client.create_bucket(Bucket=bucket_name)
    except botocore.exceptions.ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    return bucket_name
