"""Centralised boto3 client/resource factory.

The whole point: a *single* place that decides whether to hit LocalStack
or real AWS. Application code never branches on environment. Flipping
between LocalStack and a real AWS account is a config change, not a
code change — which is the property that makes LocalStack worth using.
"""
from __future__ import annotations

import os
from functools import lru_cache

import boto3


def _endpoint() -> str | None:
    """Return the AWS endpoint URL, or None for real AWS."""
    return os.environ.get("AWS_ENDPOINT_URL") or None


@lru_cache(maxsize=None)
def client(service: str):
    return boto3.client(service, endpoint_url=_endpoint())


@lru_cache(maxsize=None)
def resource(service: str):
    return boto3.resource(service, endpoint_url=_endpoint())
