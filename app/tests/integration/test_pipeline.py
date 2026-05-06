"""End-to-end pipeline test against LocalStack.

This is the kind of test that's hard to write without LocalStack —
it covers S3 → SNS → SQS → Lambda → DynamoDB in one go. With moto you'd
need to mock each hop; here we exercise the real wiring (the same
wiring Terraform applies to production).

Run with: pytest -m integration
"""
import time
import uuid

import pytest

from claims_processor.producer import (
    get_claim,
    list_claims_for_policy,
    submit_claim,
)


pytestmark = [pytest.mark.integration, pytest.mark.timeout(45)]


def _wait_for_claim(claim_id: str, timeout: float = 30.0) -> dict:
    """Poll DynamoDB until the Lambda has processed the upload.

    Async pipelines can't be asserted synchronously — every enterprise
    integration test needs a pattern like this. Keep the timeout
    generous: cold-start of a LocalStack Lambda is slow on the first run.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        item = get_claim(claim_id)
        if item is not None:
            return item
        time.sleep(0.5)
    pytest.fail(f"claim {claim_id} not processed within {timeout}s")


def test_submitting_a_claim_creates_a_dynamodb_record():
    policy = f"POL-{uuid.uuid4().hex[:8].upper()}"

    submission = submit_claim(policy, b"%PDF-1.4 fake claim doc")
    item = _wait_for_claim(submission.claim_id)

    assert item["policy_number"] == policy
    assert item["status"] == "RECEIVED"
    assert item["document_key"] == submission.document_key
    assert item["document_size_bytes"] > 0


def test_multiple_claims_for_same_policy_are_queryable_by_gsi():
    policy = f"POL-{uuid.uuid4().hex[:8].upper()}"

    submissions = [submit_claim(policy, f"claim {i}".encode()) for i in range(3)]
    for s in submissions:
        _wait_for_claim(s.claim_id)

    claims = list_claims_for_policy(policy)
    assert len(claims) == 3
    assert {c["claim_id"] for c in claims} == {s.claim_id for s in submissions}
