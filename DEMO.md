# LocalStack POC — Demo Description

A self-contained, runnable proof-of-concept that shows how LocalStack lets
us build, test, and demonstrate AWS-based systems on a developer laptop —
with no AWS account, no cloud cost, and the same Terraform/SDK code we'd
ship to production.

---

## The scenario

A simplified slice of a **claims-processing pipeline**:

> A customer (or upstream system) submits a claim document. It lands in
> object storage, fans out through a notification topic to a queue, and
> a worker writes a normalised record into a database — exactly the
> async, event-driven shape most enterprise AWS workloads converge on.

```
┌──────────┐  upload  ┌─────┐ notify ┌─────┐ fan-out ┌─────┐ trigger ┌────────┐ write  ┌──────────┐
│ Producer │ ───────► │ S3  │ ─────► │ SNS │ ──────► │ SQS │ ──────► │ Lambda │ ─────► │ DynamoDB │
└──────────┘          └─────┘        └─────┘    │    └─────┘         └────────┘        └──────────┘
                                                │       │
                                                │       └─► (3× retry) ─► DLQ
                                                ▼
                                        (other subscribers — fraud
                                         scoring, audit, notifications…)
```

The pipeline is intentionally small. The point is not the business logic —
it's that every hop runs on real AWS APIs, served locally, with the same
infrastructure-as-code we'd run in production.

---

## What gets demoed

A single command — `make demo` — runs the full path end-to-end:

1. **Upload**: drops a sample document into the S3 bucket
2. **Pipeline fires**: S3 publishes to SNS, SNS fans out to SQS, SQS triggers the Lambda
3. **Persist**: the Lambda parses the S3 event, derives the claim metadata
   from the object key, and writes a record to DynamoDB
4. **Verify**: the script polls DynamoDB and prints the record

Observed end-to-end latency on a laptop: **~4 seconds**, cold.

A second command — `make status` — lists every provisioned resource (S3
bucket, SNS topic, SQS queues + DLQ, DynamoDB table, Lambda function), so
the audience can see this is real AWS API output, not a script faking it.

---

## What's actually built

```
localstack-poc/
├── docker-compose.yml          LocalStack container + a Terraform sidecar
├── infra/main.tf               One Terraform file, 12 AWS resources
├── lambdas/claim_processor/
│   └── handler.py              Lambda source — same code as in real AWS
├── app/
│   ├── src/claims_processor/
│   │   ├── aws.py              boto3 client wrapper (the only file that
│   │   │                       knows about LocalStack)
│   │   └── producer.py         Submission API + read-side queries
│   └── tests/
│       ├── unit/               moto-backed; runs in milliseconds, no Docker
│       └── integration/        Real LocalStack; runs end-to-end in CI
├── scripts/demo.sh             The script you run during the demo
└── Makefile                    up, demo, status, test, down
```

### Resources Terraform provisions

| Resource | Purpose |
| --- | --- |
| `aws_s3_bucket.claim_documents` | Where claim documents land |
| `aws_s3_bucket_notification` | Publishes ObjectCreated events to SNS |
| `aws_sns_topic.claim_events` | Fan-out point for downstream consumers |
| `aws_sns_topic_policy` | Allows S3 to publish to the topic |
| `aws_sqs_queue.claim_processing` | Subscriber, consumed by the Lambda |
| `aws_sqs_queue.claim_processing_dlq` | Dead-letter queue (3 retries → DLQ) |
| `aws_sqs_queue_policy` | Allows SNS to deliver to the queue |
| `aws_sns_topic_subscription` | Wires SNS to SQS |
| `aws_dynamodb_table.claims` | Claim records, with a GSI on `policy_number` |
| `aws_iam_role.lambda_role` | Execution role for the Lambda |
| `aws_lambda_function.claim_processor` | The worker |
| `aws_lambda_event_source_mapping` | Wires the queue to the Lambda |

---

## The key insight: LocalStack-specific code is one file

The whole pitch is that **adopting LocalStack doesn't require restructuring
your code**. The POC proves it concretely:

- **Terraform** — one `endpoints {}` block in the AWS provider points at
  LocalStack. Remove it and the same Terraform deploys to real AWS.
- **Application code** — `app/src/claims_processor/aws.py` is ~15 lines.
  It reads `AWS_ENDPOINT_URL` if set, otherwise uses real AWS. That's the
  whole abstraction.
- **Lambda code** — identical to what would run in real AWS. The
  endpoint is injected via environment variable at deploy time.

Everything else — the producer API, the handler logic, the tests — is
written against vanilla `boto3` and is portable as-is.

---

## Two-layer testing strategy

The POC ships with both kinds of tests, because in practice teams need both:

| Layer | Backend | Speed | What it catches |
| --- | --- | --- | --- |
| **Unit** (`tests/unit`) | `moto` (in-process Python fake) | ~10 ms / test | Logic bugs in handlers, parsing, validation |
| **Integration** (`tests/integration`) | LocalStack via Docker | ~1–3 s / test | Wiring bugs, IAM, event filters, Terraform mistakes |

Both layers test against the same `boto3` API — the difference is which
fake sits behind it. Unit tests run on every keystroke; integration tests
run on every PR. Neither needs an AWS account.

---

## How this maps to real AWS

When promoting to production, three things change. **None of them are
application code**:

1. `infra/main.tf` — drop the `endpoints {}` block and the test credentials
2. Runtime config — unset `AWS_ENDPOINT_URL` in the deploy environment
3. CI — keep LocalStack for pre-merge integration tests; add a smoke-test
   stage post-merge against a real AWS sandbox account to catch any
   LocalStack/AWS divergence

---

## Why this is worth doing

| Friction in real AWS | What LocalStack changes |
| --- | --- |
| Each developer needs a sandbox AWS account | One `docker compose up`, no cloud account |
| Integration tests in CI cost money and contend on shared resources | Tests run inside the CI container, ephemeral and free |
| Reproducing customer incidents requires production-like data, which is risky in real AWS | Spin up a LocalStack snapshot, replay traffic, throw the env away |
| Onboarding a new dev = hours of console / IAM setup | Clone the repo, `make up`, productive in minutes |
| Demos depend on someone's dev account being reachable | The demo is the repo |

---

## Honest limits

- **LocalStack Community** (used here) covers ~30 services. Cognito, RDS,
  EKS, real IAM enforcement, persistence/snapshots, and a few other
  services live in the Pro tier (~$35/dev/month list price).
- **It is not 1:1 with AWS.** Edge-case behaviours diverge. The mitigation
  is the post-merge smoke stage against real AWS.
- **It replaces dev and pre-merge testing**, not production.

---

## What's deliberately out of scope for the POC

Realistic next steps a team would add — left out to keep the demo small:

- API Gateway in front of the producer for a real HTTP entry point
- Step Functions orchestration for multi-stage workflows (Pro)
- KMS envelope encryption on the documents bucket
- EventBridge rules in place of SNS for richer routing
- Cognito + IAM authorizers (Pro)
- A real CI pipeline (GitHub Actions / Jenkins) running the integration
  suite on every PR

Each is a one- or two-resource extension to `infra/main.tf` — not a
rewrite.

---

## Try it yourself

```bash
make up         # start LocalStack and apply Terraform     (~90 s first run)
make demo       # submit a sample claim, watch it process  (~4 s)
make status     # list every resource that was provisioned
make test       # run unit + integration tests
make down       # tear it all down
```

`make help` lists every target.
