"""
Pytest fixtures for S3 integration testing against LocalStack.

Provides session-scoped fixtures for:
- Health-check readiness gate (polls LocalStack health endpoint)
- boto3 S3 client configured for LocalStack endpoint
- Idempotent S3 bucket provisioning

These fixtures are consumed by test_s3_attachment.py and any other tests
in the tests/s3_integration/ directory.

Environment variables (all optional with dev/test defaults):
    AWS_ENDPOINT_URL     — LocalStack endpoint (default: http://localhost:4566)
    AWS_ACCESS_KEY_ID    — AWS access key (default: test)
    AWS_SECRET_ACCESS_KEY — AWS secret key (default: test)
    AWS_DEFAULT_REGION   — AWS region (default: us-east-1)
    AWS_S3_BUCKET        — Target S3 bucket name (default: odoo-attachments)
"""

import os
import time

import boto3
import pytest
import requests
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# pytest-odoo Plugin Neutralisation
# ---------------------------------------------------------------------------
# The ``pytest-odoo`` plugin (registered as the ``odoo`` pytest11 entrypoint)
# ships session- and module-scoped autouse fixtures that attempt to initialise
# the full Odoo registry against a PostgreSQL database.  These fixtures are
# irrelevant (and harmful) for the standalone S3 integration tests which
# require only a LocalStack endpoint.  Overriding them here prevents
# ``AttributeError: module 'odoo' has no attribute 'tests'`` and similar
# failures when running ``pytest tests/s3_integration/ -v`` with the plugin
# installed.  # S3 storage backend — see IR_ATTACHMENT_STORAGE env var


@pytest.fixture(scope="session", autouse=True)
def load_registry():
    """Override pytest-odoo ``load_registry`` — S3 tests don't need Odoo registry."""
    yield


@pytest.fixture(scope="module", autouse=True)
def enable_odoo_test_flag():
    """Override pytest-odoo ``enable_odoo_test_flag`` — S3 tests don't need Odoo config."""
    yield


# ---------------------------------------------------------------------------
# Fixture 1: LocalStack S3 Readiness Gate
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def localstack_s3_ready():
    """Poll LocalStack health endpoint until S3 is available (30s timeout).

    This fixture runs automatically before any test in the session.  It
    queries the ``/_localstack/health`` endpoint and waits for the ``s3``
    service to report an *available*, *running*, or *ready* status.

    If the health check does not succeed within 30 seconds the entire test
    session is gracefully skipped via ``pytest.skip`` — no hanging.
    """
    endpoint_base = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    health_url = endpoint_base.rstrip("/") + "/_localstack/health"
    timeout = 30  # seconds
    poll_interval = 1  # seconds

    start = time.monotonic()
    last_error = None

    while time.monotonic() - start < timeout:
        try:
            resp = requests.get(health_url, timeout=5)
            if resp.ok:
                health = resp.json()
                services = health.get("services", {})
                s3_status = services.get("s3")
                if s3_status in ("available", "running", "ready"):
                    return  # S3 is ready — allow tests to proceed
        except requests.ConnectionError as exc:
            last_error = exc
        except requests.Timeout as exc:
            last_error = exc
        except ValueError as exc:
            # Malformed JSON response — retry
            last_error = exc
        time.sleep(poll_interval)

    # Timeout exhausted — skip the entire test session gracefully
    skip_msg = "LocalStack S3 not available"
    if last_error is not None:
        skip_msg += f" (last error: {last_error!r})"
    pytest.skip(skip_msg)


# ---------------------------------------------------------------------------
# Fixture 2: boto3 S3 Client
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def s3_client():
    """Create a boto3 S3 client configured for LocalStack.

    The client is constructed using environment variables with sensible
    dev/test defaults that target a local LocalStack instance:

    * ``endpoint_url``        — from ``AWS_ENDPOINT_URL`` (default ``http://localhost:4566``)
    * ``aws_access_key_id``   — from ``AWS_ACCESS_KEY_ID`` (default ``test``)
    * ``aws_secret_access_key`` — from ``AWS_SECRET_ACCESS_KEY`` (default ``test``)
    * ``region_name``         — from ``AWS_DEFAULT_REGION`` (default ``us-east-1``)

    Returns:
        botocore.client.S3: A configured S3 client instance.
    """
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


# ---------------------------------------------------------------------------
# Fixture 3: Idempotent S3 Bucket Provisioning
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def s3_bucket(s3_client):
    """Create the S3 bucket idempotently and return its name.

    Uses ``create_bucket`` and silently handles the case where the bucket
    already exists (``BucketAlreadyOwnedByYou`` or ``BucketAlreadyExists``
    error codes).

    The bucket name is read from the ``AWS_S3_BUCKET`` environment variable,
    defaulting to ``odoo-attachments``.

    Args:
        s3_client: The boto3 S3 client fixture.

    Returns:
        str: The bucket name (e.g. ``odoo-attachments``).
    """
    bucket_name = os.environ.get("AWS_S3_BUCKET", "odoo-attachments")
    try:
        s3_client.create_bucket(Bucket=bucket_name)
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    return bucket_name
