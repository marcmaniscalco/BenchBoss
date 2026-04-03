.PHONY: install test cov lint lint-fix format dynamo-up dynamo-down dynamo-init server register build push ecr-create deploy-infra deploy

AWS_REGION ?= us-east-1
IMAGE_TAG   ?= latest

AWS_ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text)
ECR_URI ?= $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/bench-boss

# ── Dependencies ──────────────────────────────────────────────────────────────

install:
	pipenv install --dev

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	pipenv run pytest tests/ -v

cov:
	pipenv run pytest tests/ -v --cov=bench_boss --cov-report=term-missing

# ── Lint & format ─────────────────────────────────────────────────────────────

lint:
	pipenv run ruff check bench_boss/ tests/

lint-fix:
	pipenv run ruff check --fix bench_boss/ tests/

format:
	pipenv run ruff format bench_boss/ tests/

# ── Local DynamoDB ────────────────────────────────────────────────────────────

dynamo-up:
	docker-compose -f local/docker-compose.yml up -d

dynamo-down:
	docker-compose -f local/docker-compose.yml stop

dynamo-init:
	set AWS_ACCESS_KEY_ID=local&&set AWS_SECRET_ACCESS_KEY=local&&pipenv run python local/create_local_table.py

# ── Local dev server ──────────────────────────────────────────────────────────

# Build the Docker image and start the full stack (app + DynamoDB Local + admin UI)
# Point ngrok at port 8080
server: build
	docker-compose -f local/docker-compose.yml up

# ── Discord commands ──────────────────────────────────────────────────────────

register:
	pipenv run python register_commands.py

# ── Docker ────────────────────────────────────────────────────────────────────

build:
	pipenv requirements > requirements.txt
	docker build -t bench-boss:$(IMAGE_TAG) .

push: build
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(ECR_URI)
	docker tag bench-boss:$(IMAGE_TAG) $(ECR_URI):$(IMAGE_TAG)
	docker push $(ECR_URI):$(IMAGE_TAG)

# ── AWS deployment ────────────────────────────────────────────────────────────

# Create the ECR repository before the first full deploy (idempotent)
ecr-create:
	-aws ecr create-repository --repository-name bench-boss --region $(AWS_REGION)
	-aws iam create-service-linked-role --aws-service-name apprunner.amazonaws.com

# Deploy or update the CloudFormation stack.
# Required env vars: DISCORD_PUBLIC_KEY, DISCORD_TOKEN
deploy-infra:
	aws cloudformation deploy \
		--template-file infrastructure/template.yaml \
		--stack-name bench-boss \
		--capabilities CAPABILITY_NAMED_IAM \
		--parameter-overrides \
			DiscordPublicKey=$(DISCORD_PUBLIC_KEY) \
			DiscordToken=$(DISCORD_TOKEN) \
			ImageUri=$(ECR_URI):$(IMAGE_TAG)

# Build image, push to ECR, then update the stack (which forces a new task deployment)
deploy: push deploy-infra