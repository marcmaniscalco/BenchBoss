# Claude Instructions

## Unit Tests

Whenever you add or modify code in the `bench_boss/` package, you must also add or update the corresponding unit tests in `tests/` without being asked.

- New function or method → add tests covering the happy path and edge cases
- Modified function → update existing tests to reflect the change
- New module `bench_boss/foo.py` → create `tests/test_foo.py`

Tests use `pytest`. Run with:
```
pipenv run pytest tests/ -v --cov=bench_boss --cov-report=term-missing
```

## Linting and Formatting

This project uses `ruff` for both linting and formatting.

Check for lint errors:
```
pipenv run ruff check bench_boss/ tests/
```

Auto-fix lint errors:
```
pipenv run ruff check --fix bench_boss/ tests/
```

Format code:
```
pipenv run ruff format bench_boss/ tests/
```

Check formatting without writing (CI):
```
pipenv run ruff format --check bench_boss/ tests/
```