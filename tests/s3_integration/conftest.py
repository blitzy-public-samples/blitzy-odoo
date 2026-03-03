"""
Pytest fixtures for S3 integration testing through the Odoo ORM against LocalStack.

This conftest lets pytest-odoo load the **full Odoo registry** against a real
PostgreSQL instance.  The ``load_registry`` and ``enable_odoo_test_flag``
fixtures shipped by the ``pytest-odoo`` plugin are intentionally **not**
overridden — they initialize the registry and enable the test flag exactly
as they do for normal Odoo addon tests.

Provided fixtures
-----------------
* ``localstack_s3_ready``  — session-scoped, autouse health-check readiness gate
* ``s3_client``            — session-scoped boto3 S3 client (post-condition only)
* ``s3_bucket``            — session-scoped bucket name (post-condition only)
* ``odoo_env``             — function-scoped transactional Odoo ``env``; rolls back
  after each test so the database stays clean

Environment variables (all optional with dev/test defaults)::

    IR_ATTACHMENT_STORAGE  — must be ``s3`` to activate the S3 backend
    AWS_ENDPOINT_URL       — LocalStack endpoint (default ``http://localhost:4566``)
    AWS_ACCESS_KEY_ID      — AWS access key     (default ``test``)
    AWS_SECRET_ACCESS_KEY  — AWS secret key      (default ``test``)
    AWS_DEFAULT_REGION     — AWS region           (default ``us-east-1``)
    AWS_S3_BUCKET          — target bucket name   (default ``odoo-attachments``)
"""
# S3 storage backend — see IR_ATTACHMENT_STORAGE env var

import os
import time

import boto3
import pytest
import requests
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Fixture 1: LocalStack S3 Readiness Gate
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def localstack_s3_ready():
    """Poll LocalStack health endpoint until S3 is available (30 s timeout).

    Queries ``/_localstack/health`` and waits for the ``s3`` service to
    report an *available*, *running*, or *ready* status.  If the health
    check does not succeed within 30 seconds the entire test session is
    gracefully skipped via ``pytest.skip`` — no hanging.
    """
    endpoint_base = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    health_url = endpoint_base.rstrip("/") + "/_localstack/health"
    timeout = 30  # seconds
    poll_interval = 1  # seconds

    start = time.monotonic()
    last_error: Exception | None = None

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
            # Malformed JSON — retry
            last_error = exc
        time.sleep(poll_interval)

    # Timeout exhausted — skip the entire session gracefully
    skip_msg = "LocalStack S3 not available"
    if last_error is not None:
        skip_msg += f" (last error: {last_error!r})"
    pytest.skip(skip_msg)


# ---------------------------------------------------------------------------
# Fixture 2: boto3 S3 Client (post-condition verification ONLY)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def s3_client():
    """Create a boto3 S3 client configured for LocalStack.

    This client is intended **exclusively** for post-condition verification
    (e.g. ``head_object`` to confirm an object exists or is absent after
    an ORM call).  Tests must **never** call ``put_object`` /
    ``get_object`` / ``delete_object`` directly.

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
# Fixture 3: S3 Bucket Name
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def s3_bucket():
    """Return the configured S3 bucket name.

    The bucket is auto-created by ``_get_s3_client()`` inside
    ``ir_attachment.py`` on the first ORM call that touches the S3
    backend, so no explicit creation is required here.

    Returns:
        str: The bucket name (e.g. ``odoo-attachments``).
    """
    return os.environ.get("AWS_S3_BUCKET", "odoo-attachments")


# ---------------------------------------------------------------------------
# Fixture 4: Transactional Odoo Environment
# ---------------------------------------------------------------------------

@pytest.fixture()
def odoo_env():
    """Yield a transactional Odoo ``env`` with ``ir.attachment`` available.

    A new database cursor is opened against the test database (configured
    via ``--odoo-database``).  The cursor is **rolled back** after the test
    body finishes — this keeps the PostgreSQL database clean between tests
    while still exercising real ORM write / read / delete paths.

    .. note::

       S3 operations are **not** transactional.  Objects written to S3
       during a test persist even after the DB rollback.  Because each
       test uses unique data (different SHA-1 checksums) this does not
       affect test isolation.

    Yields:
        odoo.api.Environment: A fully-initialised Odoo environment bound
        to a fresh, uncommitted database transaction.
    """
    import odoo  # noqa: E402 — available after pytest-odoo loads the registry
    from odoo.tests.common import get_db_name

    db_name = get_db_name()
    registry = odoo.modules.registry.Registry(db_name)
    cr = registry.cursor()
    try:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        yield env
    finally:
        cr.rollback()
        cr.close()
