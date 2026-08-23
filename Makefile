.PHONY: install test cov lint lint-fix format pre-commit-install pre-commit-run secrets-scan secrets-audit dynamo-up dynamo-down dynamo-init local register register-qa build deploy pipeline-deploy pr-pipeline-deploy

-include .env
export

AWS_REGION ?= us-east-1
STACK_NAME ?= bench-boss
PIPELINE_STACK_NAME ?= bench-boss-pipeline
PR_PIPELINE_STACK_NAME ?= bench-boss-pr-pipeline

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

# ── Secret scanning ───────────────────────────────────────────────────────────

# Regenerate .secrets.baseline after adding new tracked files. New findings
# still need auditing (see secrets-audit) before they're accepted. Paths are
# normalized to forward slashes afterwards so the baseline matches on Linux CI.
secrets-scan:
	pipenv run detect-secrets scan --baseline .secrets.baseline $$(git ls-files)
	pipenv run python local/normalize_secrets_baseline.py

# Interactively mark new findings in .secrets.baseline as real secrets or
# false positives.
secrets-audit:
	pipenv run detect-secrets audit .secrets.baseline

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

# Deploy the PR pipeline stack. Run once; afterwards every PR opened/updated
# against main runs lint/format/secrets/tests and deploys to QA only — no
# approval stage, no Prod stage. Requires the QA Secrets Manager secret to
# already exist (see README Part 7.2).
pr-pipeline-deploy:
	aws cloudformation deploy \
		--template-file infrastructure/pr-pipeline.yaml \
		--stack-name $(PR_PIPELINE_STACK_NAME) \
		--region $(AWS_REGION) \
		--capabilities CAPABILITY_IAM
