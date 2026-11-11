"""ContractGuard demo: the blueprint's example, end to end.

Runs the breaking fixture through the CLI (terminal + JSON + SARIF +
Markdown outputs) and prints the terminal report. The machine-readable
outputs are written to a temporary directory by default so a demo run
never overwrites the committed files under examples/; pass
``--write-examples`` to refresh those files deliberately.

Expected terminal output for the breaking fixture (server profile):

    [FAIL] BREAKING: request parameter limit (query) is now required
    [FAIL] BREAKING: GET /users/{id} removed
    [FAIL] BREAKING: request field `email` changed from string to integer
    [FAIL] BREAKING: new required request field `region`
    [FAIL] BREAKING: response field `role` enum narrowed: removed 'user'

Run: python3 demo.py [--write-examples]
"""

import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contractguard.cli import main  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def run(write_examples: bool = False) -> int:
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
    if write_examples:
        out_dir = os.path.join(HERE, "examples")
        os.makedirs(out_dir, exist_ok=True)
    else:
        out_dir = tempfile.mkdtemp(prefix="contractguard-demo-")
    print(f"=== machine-readable outputs (written to {out_dir}) ===")
    main(
        [
            "check", "--base", breaking_base, "--head", breaking_head,
            "--format", "json",
            "--output", os.path.join(out_dir, "report.json"),
        ]
    )
    main(
        [
            "check", "--base", breaking_base, "--head", breaking_head,
            "--format", "sarif",
            "--output", os.path.join(out_dir, "report.sarif"),
        ]
    )
    main(
        [
            "check", "--base", breaking_base, "--head", breaking_head,
            "--format", "markdown",
            "--output", os.path.join(out_dir, "pr-summary.md"),
        ]
    )
    print("wrote report.json, report.sarif, pr-summary.md")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ContractGuard demo")
    parser.add_argument(
        "--write-examples", action="store_true",
        help="Write the machine-readable outputs into examples/ "
             "(default: a temporary directory)",
    )
    args = parser.parse_args()
    raise SystemExit(run(write_examples=args.write_examples))
