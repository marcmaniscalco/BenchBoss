.PHONY: install test cov lint lint-fix format dynamo-up dynamo-down dynamo-init local register build deploy

-include .env
export

AWS_REGION ?= us-east-1
STACK_NAME ?= bench-boss

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

# Run the Flask local server (point ngrok at port 3000)
local:
	pipenv run python local/local_server.py

# ── Discord commands ──────────────────────────────────────────────────────────

register:
	pipenv run python register_commands.py

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