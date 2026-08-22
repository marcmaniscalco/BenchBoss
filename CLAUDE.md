# Claude Instructions

## Unit Tests

Whenever you add or modify code in the `bench_boss/` package, you must also add or update the corresponding unit tests in `tests/` without being asked.

- New function or method → add tests covering the happy path and edge cases
- Modified function → update existing tests to reflect the change
- New module `bench_boss/foo.py` → create `tests/test_foo.py`

Tests use `pytest`. Run with:
```
make cov
```

## README Sync

Whenever the project is updated, you must also update `README.md` to reflect the new or changed instructions without being asked.

## Linting and Formatting

This project uses `ruff` for both linting and formatting.

Check for lint errors:
```
make lint
```

Auto-fix lint errors:
```
make lint-fix
```

Format code:
```
make format
```

## Cross-Platform Compatibility

Local development happens on Windows, but CI (CodeBuild) runs on Linux. Never bake OS-native path separators or other Windows-only assumptions into anything that gets committed or that CI reads.

- Always normalize file paths to forward slashes in any generated/committed artifact (e.g. `.secrets.baseline`) — don't assume `os.sep` is `/`.
- When a tool (like `detect-secrets scan`) writes paths using the host OS's separator, post-process its output to forward slashes before committing, and keep that normalization step in the tooling (see `local/normalize_secrets_baseline.py`) so it isn't a one-off manual fix.
- When writing scripts intended to run in CI, verify they work without relying on Windows-specific behavior, and prefer stdlib path handling (`pathlib`, which is separator-aware) over hardcoded `\` or `/`.
- If a check passes locally on Windows, that is not sufficient evidence it will pass in Linux CI — reason about what the CI environment actually looks like (e.g. CodeBuild's GitHub source is a zip snapshot with no `.git` directory) rather than assuming parity with local dev.

## AWS Guidance

- Prefer the AWS MCP Server for AWS interactions — it provides sandboxed
  execution, observability, and audit logging. If unavailable, use the
  AWS CLI directly.
- Before starting a task, check whether a relevant AWS skill is available.
  Load the skill with `retrieve_skill` and prefer its guidance over
  general knowledge.
- When uncertain about specific AWS details (API parameters, permissions,
  limits, error codes), verify against documentation rather than guessing.
  State uncertainty explicitly if you cannot confirm.
- When creating infrastructure, prefer infrastructure-as-code (AWS CDK or
  CloudFormation) over direct CLI commands.
- When working with infrastructure, follow AWS Well-Architected Framework
  principles.
- Do not use em dashes in AWS resource names or descriptions. Use
  hyphens instead.

### Secret Safety

- MUST load the `aws-secrets-manager` skill first for any secret,
  credential, API key, token, or password task. MUST NOT call
  `secretsmanager get-secret-value` or `batch-get-secret-value`, and MUST
  NOT hit the Secrets Manager Agent daemon directly. MUST use
  `{{resolve:secretsmanager:secret-id:SecretString:json-key}}` with
  `asm-exec` so the secret resolves at runtime without entering context.
