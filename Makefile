.PHONY: install test cov lint lint-fix format dynamo-up dynamo-down dynamo-init serve register deploy

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

server:
	set DYNAMODB_TABLE=bench-boss-local&&set DYNAMODB_ENDPOINT=http://localhost:8000&&set AWS_ACCESS_KEY_ID=local&&set AWS_SECRET_ACCESS_KEY=local&&pipenv run python local/local_server.py

# ── Discord commands ──────────────────────────────────────────────────────────

register:
	pipenv run python register_commands.py

# ── AWS deployment ────────────────────────────────────────────────────────────

deploy:
	sam build && sam deploy --guided