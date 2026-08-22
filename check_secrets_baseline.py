"""
CI gate for secret scanning.

Unlike the `detect-secrets` pre-commit hook, this doesn't require a git
repository — CodePipeline's GitHub source delivers a plain zip snapshot to
CodeBuild, with no .git directory. Rescans the given files against
.secrets.baseline (merging in any new findings with is_secret left
unaudited), then fails the build if anything is unaudited.

Usage: python check_secrets_baseline.py <file> [<file> ...]
"""

import json
import subprocess
import sys
from pathlib import Path

BASELINE_PATH = Path(__file__).resolve().parent / ".secrets.baseline"


def main() -> int:
    files = sys.argv[1:]
    if not files:
        print("check_secrets_baseline.py: no files given", file=sys.stderr)
        return 1

    subprocess.run(
        [
            sys.executable,
            "-m",
            "detect_secrets",
            "scan",
            "--baseline",
            str(BASELINE_PATH),
            *files,
        ],
        check=True,
    )

    data = json.loads(BASELINE_PATH.read_text())
    unaudited = [
        (filename, entry)
        for filename, entries in data["results"].items()
        for entry in entries
        if entry.get("is_secret") is None
    ]

    if unaudited:
        print("Unaudited potential secrets found:\n")
        for filename, entry in unaudited:
            print(f"  {filename}:{entry['line_number']}  ({entry['type']})")
        print(
            "\nIf these are real secrets, remove them. If they're false "
            "positives, run `make secrets-scan` and `make secrets-audit` "
            "locally, then commit the updated .secrets.baseline."
        )
        return 1

    print("No unaudited secrets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
