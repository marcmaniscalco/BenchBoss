"""
Normalizes path separators in .secrets.baseline to forward slashes.

`detect-secrets scan` bakes in OS-native path separators, so running it on
Windows writes backslash-separated paths that won't match the forward-slash
paths CI (Linux) generates when re-checking the baseline. Run this after
`detect-secrets scan` on Windows:

    pipenv run detect-secrets scan --baseline .secrets.baseline $(git ls-files)
    python local/normalize_secrets_baseline.py
"""

import json
from pathlib import Path

BASELINE_PATH = Path(__file__).resolve().parent.parent / ".secrets.baseline"


def main() -> None:
    data = json.loads(BASELINE_PATH.read_text())

    normalized_results = {}
    for filename, entries in data["results"].items():
        for entry in entries:
            entry["filename"] = entry["filename"].replace("\\", "/")
        normalized_results[filename.replace("\\", "/")] = entries
    data["results"] = normalized_results

    # `detect-secrets scan` also bakes an absolute, OS-native path into this
    # filter's config on Windows (Linux writes the relative ".secrets.baseline").
    for f in data["filters_used"]:
        if f["path"] == "detect_secrets.filters.common.is_baseline_file":
            f["filename"] = ".secrets.baseline"

    BASELINE_PATH.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
