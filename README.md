# LocalStack Enterprise POC — Claims Processing Pipeline

A self-contained proof-of-concept showing how **LocalStack** lets enterprise
teams build, test, and demo AWS-based systems entirely on a developer laptop
or CI runner — with **no AWS account, no cloud cost, no IT ticket**.

The example pipeline is a (deliberately small) slice of a claims-processing
flow:

```
┌──────────┐    upload   ┌─────┐  notify  ┌─────┐  fan-out  ┌─────┐  trigger  ┌────────┐  write  ┌──────────┐
│ Producer │ ──────────► │ S3  │ ───────► │ SNS │ ────────► │ SQS │ ────────► │ Lambda │ ──────► │ DynamoDB │
└──────────┘             └─────┘          └─────┘  ┌──────► └─────┘           └────────┘         └──────────┘
                                                   │            │
                                                   │            └─► (3× retry) ──► DLQ
                                                   ▼
                                                (other subscribers — fraud, audit, notifications…)
```

This is the pattern most enterprise event-driven systems converge on. If
LocalStack can host *this*, it can host the variants your teams actually run.

---

## Quick start

Prerequisites: Docker, AWS CLI (any recent version), Python 3.11+.

```bash
make up           # start LocalStack and apply Terraform
make demo         # submit a sample claim and watch it process end-to-end
make test         # run unit + integration tests
make down         # tear everything down
```

`make help` lists every target.

---

## Project layout

```
localstack-poc/
├── docker-compose.yml          # LocalStack + a Terraform provisioner sidecar
├── infra/main.tf               # The same TF you'd run in real AWS
├── lambdas/claim_processor/    # Lambda source — copied verbatim into AWS
├── app/                        # Producer-side app + tests
│   ├── src/claims_processor/   #   boto3 client wrapper + submission API
│   └── tests/
│       ├── unit/               #   moto-backed, runs in milliseconds
│       └── integration/        #   real LocalStack, end-to-end
├── scripts/demo.sh             # The script you'd show in a demo
└── Makefile
```

---

## The two-layer testing strategy

The POC deliberately demonstrates **both** layers, because in practice
enterprise teams need both:

| Layer | Backend | Speed | Catches |
| --- | --- | --- | --- |
| **Unit** (`tests/unit`) | [moto](https://github.com/getmoto/moto) — in-process Python fake | ~10 ms / test | Logic bugs in handlers, parsing, validation |
| **Integration** (`tests/integration`) | LocalStack via Docker | ~1–3 s / test | Wiring bugs, IAM, event filters, Terraform mistakes |

Unit tests run on every keystroke. Integration tests run on every PR.
**Neither needs a real AWS account.**

---

## How this maps to real AWS

When promoting to a real environment, three things change:

1. **`infra/main.tf`** — drop the `endpoints {}` block and the test
   credentials. Same Terraform, real cloud.
2. **Application config** — unset `AWS_ENDPOINT_URL`. The boto3 wrapper in
   `app/src/claims_processor/aws.py` already handles both cases.
3. **CI** — point integration tests at a per-branch ephemeral env (still
   LocalStack on the runner) and add a smoke test stage against a real
   AWS sandbox account post-merge.

No code change.