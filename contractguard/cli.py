"""Command-line interface for ContractGuard."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .baseline import load_base, load_head
from .diff import diff_contracts
from .parser import SpecError
from .policy import DEFAULT_FAIL_ON, DEFAULT_WARN_ON, Policy, policy_from_file
from .report import render_json, render_markdown, render_sarif, render_terminal
from .rules import RULES, classify


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contractguard",
        description=(
            "Catch breaking API changes before they reach production. "
            "Compares an OpenAPI contract against a baseline."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser(
        "check", help="Compare a head contract against a baseline"
    )
    check.add_argument("--base", dest="base_file", default=None,
                       help="Baseline spec file (YAML or JSON)")
    check.add_argument("--head", dest="head_file", default=None,
                       help="Head spec file (YAML or JSON)")
    check.add_argument("--base-ref", default=None,
                       help="Git ref for the baseline (needs --base-path)")
    check.add_argument("--base-path", default=None,
                       help="Path of the baseline spec inside the git ref")
    check.add_argument("--head-ref", default=None,
                       help="Git ref for the head (needs --head-path)")
    check.add_argument("--head-path", default=None,
                       help="Path of the head spec inside the git ref")
    check.add_argument("--profile", choices=("server", "client"), default="server",
                       help="Compatibility profile (default: server)")
    check.add_argument("--policy", default=None,
                       help="Policy config file (YAML/JSON)")
    check.add_argument("--fail-on", nargs="*", default=None,
                       help="Severities that fail CI (default: BREAKING)")
    check.add_argument("--warn-on", nargs="*", default=None,
                       help="Severities reported as warnings (default: WARNING UNKNOWN)")
    check.add_argument("--format", choices=("terminal", "json", "sarif", "markdown"),
                       default="terminal", help="Report format (default: terminal)")
    check.add_argument("--output", default=None,
                       help="Write the report to a file instead of stdout")

    sub.add_parser("rules", help="List the compatibility rules")

    demo = sub.add_parser("demo", help="Run the built-in demo fixtures")
    demo.add_argument("--profile", choices=("server", "client"), default="server")
    return parser


def _load_policy(args) -> Policy:
    if args.policy:
        policy = policy_from_file(args.policy)
    else:
        policy = Policy(profile=args.profile)
    if args.profile and not args.policy:
        policy.profile = args.profile
    if args.fail_on is not None:
        policy.fail_on = tuple(v.upper() for v in args.fail_on)
    if args.warn_on is not None:
        policy.warn_on = tuple(v.upper() for v in args.warn_on)
    return policy


def _run_check(args) -> int:
    try:
        policy = _load_policy(args)
    except ValueError as exc:
        print(f"contractguard: policy error: {exc}", file=sys.stderr)
        return 2
    try:
        base, base_label = load_base(
            base_file=args.base_file, base_ref=args.base_ref, base_path=args.base_path
        )
        head, head_label = load_head(
            head_file=args.head_file, head_ref=args.head_ref, head_path=args.head_path
        )
    except SpecError as exc:
        print(f"contractguard: {exc}", file=sys.stderr)
        return 2
    findings = classify(diff_contracts(base, head), profile=policy.profile)
    if args.format == "json":
        text = render_json(findings, base_label, head_label)
    elif args.format == "sarif":
        text = render_sarif(findings, base_label, head_label)
    elif args.format == "markdown":
        text = render_markdown(findings, base_label, head_label)
    else:
        text = render_terminal(findings, base_label, head_label)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)
    return policy.exit_code(findings)


def _run_rules() -> int:
    print("ContractGuard compatibility rules")
    print("---------------------------------")
    print("server = existing clients vs new server | client = new client vs old servers")
    print()
    print(f"{'Rule':<5}{'Change':<38}{'Direction':<10}{'Server':<10}{'Client':<10}")
    for rule_id, change, direction, server, client, _desc in RULES:
        print(f"{rule_id:<5}{change:<38}{direction:<10}{server:<10}{client:<10}")
    print()
    print("Full rule documentation: docs/rules.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return _run_check(args)
    if args.command == "rules":
        return _run_rules()
    if args.command == "demo":
        from .demo import run_demo

        return run_demo(profile=args.profile)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
