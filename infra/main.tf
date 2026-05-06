terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

# Single provider block — point at LocalStack via custom endpoints.
# In real AWS, only the access keys & endpoints change; the resource
# definitions below are identical.
provider "aws" {
  region                      = "eu-west-1"
  access_key                  = "test"
  secret_key                  = "test"
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    s3       = "http://localstack:4566"
    sns      = "http://localstack:4566"
    sqs      = "http://localstack:4566"
    lambda   = "http://localstack:4566"
    dynamodb = "http://localstack:4566"
    iam      = "http://localstack:4566"
    logs     = "http://localstack:4566"
  }
}

locals {
  project = "claims-poc"
}

# ─── S3: bucket where customers upload claim documents ─────────────
resource "aws_s3_bucket" "claim_documents" {
  bucket        = "${local.project}-documents"
  force_destroy = true
}

resource "aws_s3_bucket_notification" "claim_uploaded" {
  bucket = aws_s3_bucket.claim_documents.id

  topic {
    topic_arn = aws_sns_topic.claim_events.arn
    events    = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_sns_topic_policy.allow_s3]
}

# ─── SNS: fan-out topic for claim lifecycle events ─────────────────
resource "aws_sns_topic" "claim_events" {
  name = "${local.project}-claim-events"
}

resource "aws_sns_topic_policy" "allow_s3" {
  arn = aws_sns_topic.claim_events.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "SNS:Publish"
      Resource  = aws_sns_topic.claim_events.arn
    }]
  })
}

# ─── SQS: queue subscribed to the topic, consumed by Lambda ────────
resource "aws_sqs_queue" "claim_processing_dlq" {
  name = "${local.project}-claim-processing-dlq"
}

resource "aws_sqs_queue" "claim_processing" {
  name                       = "${local.project}-claim-processing"
  visibility_timeout_seconds = 60
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.claim_processing_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sns_topic_subscription" "claim_to_queue" {
  topic_arn            = aws_sns_topic.claim_events.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.claim_processing.arn
  raw_message_delivery = true
}

resource "aws_sqs_queue_policy" "allow_sns" {
  queue_url = aws_sqs_queue.claim_processing.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.claim_processing.arn
      Condition = {
        ArnEquals = { "aws:SourceArn" = aws_sns_topic.claim_events.arn }
      }
    }]
  })
}

# ─── DynamoDB: claim records ───────────────────────────────────────
resource "aws_dynamodb_table" "claims" {
  name         = "${local.project}-claims"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "claim_id"

  attribute {
    name = "claim_id"
    type = "S"
  }

  attribute {
    name = "policy_number"
    type = "S"
  }

  global_secondary_index {
    name            = "policy_number-index"
    hash_key        = "policy_number"
    projection_type = "ALL"
  }
}

# ─── Lambda: processes the queue, writes to DynamoDB ───────────────
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "/lambdas/claim_processor"
  output_path = "/tmp/claim_processor.zip"
}

resource "aws_iam_role" "lambda_role" {
  name = "${local.project}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_lambda_function" "claim_processor" {
  function_name    = "${local.project}-claim-processor"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      CLAIMS_TABLE = aws_dynamodb_table.claims.name
      AWS_ENDPOINT = "http://localstack:4566"
    }
  }
}

resource "aws_lambda_event_source_mapping" "queue_trigger" {
  event_source_arn = aws_sqs_queue.claim_processing.arn
  function_name    = aws_lambda_function.claim_processor.arn
  batch_size       = 5
}

# ─── Outputs ───────────────────────────────────────────────────────
output "documents_bucket" {
  value = aws_s3_bucket.claim_documents.id
}

output "claim_events_topic" {
  value = aws_sns_topic.claim_events.arn
}

output "claims_table" {
  value = aws_dynamodb_table.claims.name
}
