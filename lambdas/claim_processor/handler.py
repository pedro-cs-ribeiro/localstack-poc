"""Claim processor Lambda.

Triggered by SQS messages that originate from S3 ObjectCreated events
(via SNS). For each uploaded claim document, write a record to DynamoDB.

In a real enterprise pipeline this is where you'd plug in OCR, fraud
scoring, KYC checks, etc. — for the POC we keep the logic minimal so
the focus stays on the AWS wiring.
"""
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

ENDPOINT = os.environ.get("AWS_ENDPOINT")
TABLE_NAME = os.environ["CLAIMS_TABLE"]

# When running inside the LocalStack Lambda runtime, AWS_ENDPOINT points
# at the LocalStack edge. In real AWS it's unset and boto3 uses the
# default endpoint.
_kwargs = {"endpoint_url": ENDPOINT} if ENDPOINT else {}
dynamodb = boto3.resource("dynamodb", **_kwargs)
table = dynamodb.Table(TABLE_NAME)

# Object keys follow `claims/<policy_number>/<claim_id>.<ext>`
KEY_PATTERN = re.compile(r"^claims/(?P<policy>[^/]+)/(?P<claim>[^.]+)\.(?P<ext>\w+)$")


def lambda_handler(event, _context):
    processed = []
    for record in event.get("Records", []):
        body = json.loads(record["body"]) if isinstance(record.get("body"), str) else record["body"]

        # S3 → SNS → SQS delivers the original S3 event in `Records`
        for s3_event in body.get("Records", []):
            bucket = s3_event["s3"]["bucket"]["name"]
            key = unquote_plus(s3_event["s3"]["object"]["key"])
            size = s3_event["s3"]["object"].get("size", 0)

            match = KEY_PATTERN.match(key)
            if not match:
                print(f"⚠️  skipping malformed key: {key}")
                continue

            item = {
                "claim_id": match["claim"],
                "policy_number": match["policy"],
                "document_bucket": bucket,
                "document_key": key,
                "document_size_bytes": size,
                "status": "RECEIVED",
                "received_at": datetime.now(timezone.utc).isoformat(),
            }
            table.put_item(Item=item)
            processed.append(item["claim_id"])
            print(f"✅ stored claim {item['claim_id']} for policy {item['policy_number']}")

    return {"processed": processed}
