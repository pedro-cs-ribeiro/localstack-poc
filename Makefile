SHELL := /bin/bash
.DEFAULT_GOAL := help

ENDPOINT ?= http://localhost:4566
export AWS_ENDPOINT_URL := $(ENDPOINT)
export AWS_ACCESS_KEY_ID := test
export AWS_SECRET_ACCESS_KEY := test
export AWS_DEFAULT_REGION := eu-west-1

.PHONY: help up down logs status demo test test-unit test-integration install clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start LocalStack and provision infrastructure
	docker compose up -d localstack
	docker compose run --rm provisioner
	@echo ""
	@echo "✅ LocalStack is up at $(ENDPOINT)"
	@echo "   Run 'make demo' to submit a sample claim"

down: ## Stop LocalStack and remove containers
	docker compose down -v

status: ## Show health & provisioned resources
	@curl -s $(ENDPOINT)/_localstack/health | python3 -m json.tool
	@echo ""
	@echo "Buckets:" && aws --endpoint-url=$(ENDPOINT) s3 ls
	@echo "Topics:" && aws --endpoint-url=$(ENDPOINT) sns list-topics --query 'Topics[].TopicArn' --output table
	@echo "Queues:" && aws --endpoint-url=$(ENDPOINT) sqs list-queues --query 'QueueUrls' --output table
	@echo "Tables:" && aws --endpoint-url=$(ENDPOINT) dynamodb list-tables --query 'TableNames' --output table
	@echo "Lambdas:" && aws --endpoint-url=$(ENDPOINT) lambda list-functions --query 'Functions[].FunctionName' --output table

logs: ## Tail LocalStack logs
	docker compose logs -f localstack

demo: ## Submit a sample claim and show the result
	./scripts/demo.sh

install: ## Install Python dependencies for tests
	cd app && pip install -e '.[dev]'

test: test-unit test-integration ## Run all tests

test-unit: ## Fast unit tests (moto, no Docker required)
	cd app && pytest tests/unit -m unit

test-integration: ## End-to-end tests against LocalStack
	cd app && pytest tests/integration -m integration

clean: ## Remove generated artifacts
	rm -rf app/.pytest_cache app/**/__pycache__ infra/.terraform infra/terraform.tfstate*
