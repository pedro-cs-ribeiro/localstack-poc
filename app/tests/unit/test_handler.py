"""Unit tests for the Lambda handler.

The handler is pure-ish — fast unit tests with `moto` cover the
parsing/validation logic without needing LocalStack at all. This is the
two-layer testing strategy enterprises usually want:

  • unit tests (here)        — runs in milliseconds, no Docker, in CI
  • integration tests (LocalStack) — runs end-to-end before merge

Both layers test against the same boto3 API, just different fakes.
"""
import importlib
import json
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws


pytestmark = pytest.mark.unit

LAMBDA_DIR = Path(__file__).resolve().parents[3] / "lambdas" / "claim_processor"


@pytest.fixture
def handler_module(monkeypatch):
    """Import the Lambda handler with moto-mocked AWS in scope."""
    monkeypatch.setenv("CLAIMS_TABLE", "claims-poc-claims")
    monkeypatch.delenv("AWS_ENDPOINT", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.syspath_prepend(str(LAMBDA_DIR))

    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="claims-poc-claims",
            KeySchema=[{"AttributeName": "claim_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "claim_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Force a fresh import so the module-level boto3 resource binds
        # to moto's mock backend.
        sys.modules.pop("handler", None)
        module = importlib.import_module("handler")
        yield module


def _sqs_event(bucket: str, key: str, size: int = 1024) -> dict:
    s3_event = {
        "Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key, "size": size}}}]
    }
    return {"Records": [{"body": json.dumps(s3_event)}]}


def test_handler_writes_a_claim_record(handler_module):
    event = _sqs_event("claims-poc-documents", "claims/POL-123/abc.pdf", size=2048)

    result = handler_module.lambda_handler(event, None)

    assert result == {"processed": ["abc"]}
    item = handler_module.table.get_item(Key={"claim_id": "abc"})["Item"]
    assert item["policy_number"] == "POL-123"
    assert item["document_size_bytes"] == 2048
    assert item["status"] == "RECEIVED"


def test_handler_skips_malformed_keys(handler_module):
    event = _sqs_event("claims-poc-documents", "garbage/no-policy.pdf")

    result = handler_module.lambda_handler(event, None)

    assert result == {"processed": []}


def test_handler_handles_url_encoded_keys(handler_module):
    event = _sqs_event("claims-poc-documents", "claims/POL-456/claim%20with%20spaces.pdf")

    result = handler_module.lambda_handler(event, None)

    assert result == {"processed": ["claim with spaces"]}
