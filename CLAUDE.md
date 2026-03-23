# Claude Instructions

## Unit Tests

Whenever you add or modify code in the `discord_bot/` package, you must also add or update the corresponding unit tests in `tests/` without being asked.

- New function or method → add tests covering the happy path and edge cases
- Modified function → update existing tests to reflect the change
- New module `discord_bot/foo.py` → create `tests/test_foo.py`

Tests use `pytest`. Run with:
```
pipenv run pytest tests/ -v --cov=discord_bot --cov-report=term-missing
```

## Linting and Formatting

This project uses `ruff` for both linting and formatting.

Check for lint errors:
```
pipenv run ruff check discord_bot/ tests/
```

Auto-fix lint errors:
```
pipenv run ruff check --fix discord_bot/ tests/
```

Format code:
```
pipenv run ruff format discord_bot/ tests/
```

Check formatting without writing (CI):
```
pipenv run ruff format --check discord_bot/ tests/
```