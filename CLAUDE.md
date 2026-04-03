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