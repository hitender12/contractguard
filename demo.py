"""ContractGuard demo: the blueprint's example, end to end.

Runs the breaking fixture through the CLI (terminal + JSON + SARIF +
Markdown outputs) and prints the terminal report, which should match the
blueprint example:

    BREAKING: GET /users/{id} removed
    BREAKING: response field `email` changed from string to integer
    WARNING: new required request field `region`
    SAFE: optional response field `timezone` added

Run: python demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contractguard.cli import main  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def run() -> int:
    breaking_base = os.path.join(HERE, "fixtures", "breaking", "base.yaml")
    breaking_head = os.path.join(HERE, "fixtures", "breaking", "head.yaml")
    print("=== contractguard check (breaking fixture, server profile) ===")
    code = main(
        ["check", "--base", breaking_base, "--head", breaking_head]
    )
    print(f"\nexit code: {code}  (1 = CI fails: breaking changes found)")
    print()
    print("=== same check, client profile ===")
    code = main(
        [
            "check", "--base", breaking_base, "--head", breaking_head,
            "--profile", "client",
        ]
    )
    print(f"\nexit code: {code}")
    print()
    print("=== non-breaking fixture ===")
    code = main(
        [
            "check",
            "--base", os.path.join(HERE, "fixtures", "non-breaking", "base.yaml"),
            "--head", os.path.join(HERE, "fixtures", "non-breaking", "head.yaml"),
        ]
    )
    print(f"\nexit code: {code}  (0 = CI passes)")
    print()
    print("=== ambiguous fixture (format + anyOf change) ===")
    code = main(
        [
            "check",
            "--base", os.path.join(HERE, "fixtures", "ambiguous", "base.yaml"),
            "--head", os.path.join(HERE, "fixtures", "ambiguous", "head.yaml"),
        ]
    )
    print(f"\nexit code: {code}  (0 by default: UNKNOWN warns but does not fail)")
    print()
    print("=== machine-readable outputs (written to examples/) ===")
    examples = os.path.join(HERE, "examples")
    os.makedirs(examples, exist_ok=True)
    main(
        [
            "check", "--base", breaking_base, "--head", breaking_head,
            "--format", "json",
            "--output", os.path.join(examples, "report.json"),
        ]
    )
    main(
        [
            "check", "--base", breaking_base, "--head", breaking_head,
            "--format", "sarif",
            "--output", os.path.join(examples, "report.sarif"),
        ]
    )
    main(
        [
            "check", "--base", breaking_base, "--head", breaking_head,
            "--format", "markdown",
            "--output", os.path.join(examples, "pr-summary.md"),
        ]
    )
    print("wrote examples/report.json, examples/report.sarif, examples/pr-summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
