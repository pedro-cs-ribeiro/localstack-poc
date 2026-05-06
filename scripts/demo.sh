#!/usr/bin/env bash
# Submits a sample claim and watches it flow through the pipeline.
# This is the script you'd demo to stakeholders.

set -euo pipefail

ENDPOINT="${AWS_ENDPOINT_URL:-http://localhost:4566}"
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=eu-west-1

POLICY="POL-DEMO-$(date +%s)"
CLAIM_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
KEY="claims/${POLICY}/${CLAIM_ID}.pdf"

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }

bold "─── 1. Uploading claim document to S3 ───"
echo "%PDF-1.4 sample claim" | aws --endpoint-url="$ENDPOINT" s3 cp - "s3://claims-poc-documents/${KEY}"
green "✅ uploaded s3://claims-poc-documents/${KEY}"
echo

bold "─── 2. Waiting for Lambda to process via SNS → SQS ───"
for i in {1..30}; do
  RESULT=$(aws --endpoint-url="$ENDPOINT" dynamodb get-item \
    --table-name claims-poc-claims \
    --key "{\"claim_id\":{\"S\":\"${CLAIM_ID}\"}}" \
    --output json 2>/dev/null || echo '{}')
  if echo "$RESULT" | grep -q '"Item"'; then
    green "✅ claim processed (${i}s)"
    echo
    bold "─── 3. DynamoDB record ───"
    echo "$RESULT" | python3 -m json.tool
    exit 0
  fi
  sleep 1
done

echo "❌ timed out waiting for the pipeline. Check 'make logs' for errors."
exit 1
