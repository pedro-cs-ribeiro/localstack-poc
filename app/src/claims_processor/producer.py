"""Claim submission API.

Represents whatever upstream system creates claims — a customer-facing
web form, a broker integration, an underwriter's batch upload, etc.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from .aws import client, resource

DOCUMENTS_BUCKET = "claims-poc-documents"
CLAIMS_TABLE = "claims-poc-claims"


@dataclass
class ClaimSubmission:
    claim_id: str
    policy_number: str
    document_key: str


def submit_claim(policy_number: str, document_bytes: bytes, ext: str = "pdf") -> ClaimSubmission:
    """Upload a claim document. Triggers the downstream pipeline asynchronously."""
    claim_id = str(uuid.uuid4())
    key = f"claims/{policy_number}/{claim_id}.{ext}"

    client("s3").put_object(
        Bucket=DOCUMENTS_BUCKET,
        Key=key,
        Body=document_bytes,
        ContentType=f"application/{ext}",
    )
    return ClaimSubmission(claim_id=claim_id, policy_number=policy_number, document_key=key)


def get_claim(claim_id: str) -> dict | None:
    """Read-side query — returns None until the Lambda has processed the upload."""
    response = resource("dynamodb").Table(CLAIMS_TABLE).get_item(Key={"claim_id": claim_id})
    return response.get("Item")


def list_claims_for_policy(policy_number: str) -> list[dict]:
    response = resource("dynamodb").Table(CLAIMS_TABLE).query(
        IndexName="policy_number-index",
        KeyConditionExpression="policy_number = :p",
        ExpressionAttributeValues={":p": policy_number},
    )
    return response.get("Items", [])
