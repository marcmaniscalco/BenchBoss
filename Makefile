.PHONY: install test cov lint lint-fix format pre-commit-install pre-commit-run dynamo-up dynamo-down dynamo-init local register register-qa build deploy pipeline-deploy

-include .env
export

AWS_REGION ?= us-east-1
STACK_NAME ?= bench-boss
PIPELINE_STACK_NAME ?= bench-boss-pipeline

# ── Dependencies ──────────────────────────────────────────────────────────────

install:
	pipenv install --dev
	pipenv run pre-commit install

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

# ── Pre-commit hooks ──────────────────────────────────────────────────────────

pre-commit-install:
	pipenv run pre-commit install

pre-commit-run:
	pipenv run pre-commit run --all-files

# ── Local DynamoDB ────────────────────────────────────────────────────────────

dynamo-up:
	docker-compose -f local/docker-compose.yml up -d

dynamo-down:
	docker-compose -f local/docker-compose.yml stop

dynamo-init:
	set AWS_ACCESS_KEY_ID=local&&set AWS_SECRET_ACCESS_KEY=local&&pipenv run python local/create_local_table.py

# ── Local dev server ──────────────────────────────────────────────────────────

# Run the Flask local server (point ngrok at port 3000)
local:
	pipenv run python local/local_server.py

# ── Discord commands ──────────────────────────────────────────────────────────

register:
	pipenv run python register_commands.py

register-qa:
	pipenv run python register_commands.py --env qa

# ── AWS deployment (SAM) ──────────────────────────────────────────────────────

build:
	pipenv requirements > requirements.txt
	sam build --template infrastructure/template.yaml

# Deploy or update the stack. First time: `sam deploy --guided` to record params.
# Required env vars: DISCORD_PUBLIC_KEY, DISCORD_TOKEN
deploy: build
	sam deploy \
		--stack-name $(STACK_NAME) \
		--region $(AWS_REGION) \
		--capabilities CAPABILITY_IAM \
		--no-confirm-changeset \
		--resolve-s3 \
		--parameter-overrides \
			DiscordPublicKey=$(DISCORD_PUBLIC_KEY) \
			DiscordToken=$(DISCORD_TOKEN)

# ── CI/CD pipeline (one-time bootstrap) ───────────────────────────────────────

# Deploy the CodePipeline stack itself. Run once; afterwards every push to
# `main` triggers the pipeline automatically. Requires the QA and Prod
# Secrets Manager secrets to exist (see README Part 7).
pipeline-deploy:
	aws cloudformation deploy \
		--template-file infrastructure/pipeline.yaml \
		--stack-name $(PIPELINE_STACK_NAME) \
		--region $(AWS_REGION) \
		--capabilities CAPABILITY_IAM
