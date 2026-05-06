"""Shared fixtures.

The integration tests assume the LocalStack stack is already up and
provisioned — we don't lifecycle Docker from inside pytest, so the
test runtime stays fast and the failure mode is obvious ("LocalStack
not running") instead of a 30-second mystery timeout.
"""
import os

import pytest

# Make sure boto3 always points at LocalStack during tests.
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")


@pytest.fixture(autouse=True)
def _clear_aws_clients():
    """boto3 clients are cached per-process — clear between tests so
    overrides to env vars take effect."""
    from claims_processor import aws
    aws.client.cache_clear()
    aws.resource.cache_clear()
    yield
