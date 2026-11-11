"""Built-in demo: run ContractGuard against the golden fixtures."""

from __future__ import annotations

import os

from .diff import diff_contracts
from .parser import parse_spec_file
from .policy import Policy
from .report import render_terminal
from .rules import classify

_FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def _fixture_pair(name: str):
    base = os.path.join(_FIXTURES, name, "base.yaml")
    head = os.path.join(_FIXTURES, name, "head.yaml")
    return base, head


def run_demo(profile: str = "server") -> int:
    policy = Policy(profile=profile)
    worst = 0
    for name, title in (
        ("breaking", "A PR that removes an endpoint and changes a field type"),
        ("non-breaking", "The same PR, fixed: optional fields only"),
        ("ambiguous", "A PR with a format change ContractGuard cannot judge"),
    ):
        base_path, head_path = _fixture_pair(name)
        base = parse_spec_file(base_path)
        head = parse_spec_file(head_path)
        findings = classify(diff_contracts(base, head), profile=policy.profile)
        print(f"### {title}")
        print(render_terminal(findings, f"fixtures/{name}/base.yaml", f"fixtures/{name}/head.yaml"))
        print()
        worst = max(worst, policy.exit_code(findings))
    return worst
