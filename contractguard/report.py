"""Report renderers: terminal, JSON, SARIF, and Markdown PR summary."""

from __future__ import annotations

import json

from .rules import Finding

SEVERITY_EMOJI = {
    "BREAKING": "✗",
    "WARNING": "!",
    "SAFE": "✓",
    "UNKNOWN": "?",
}


def render_terminal(findings: list[Finding], base_label: str, head_label: str) -> str:
    lines = [f"ContractGuard: {base_label} -> {head_label}", ""]
    if not findings:
        lines.append("No changes detected. Contracts are identical.")
        return "\n".join(lines)
    for finding in findings:
        lines.append(f"{finding.severity}: {finding.message}")
        if finding.explanation:
            lines.append(f"    {finding.explanation} [{finding.rule_id}]")
    counts = {sev: 0 for sev in ("BREAKING", "WARNING", "SAFE", "UNKNOWN")}
    for finding in findings:
        counts[finding.severity] += 1
    summary = ", ".join(f"{n} {sev.lower()}" for sev, n in counts.items() if n)
    lines.append("")
    lines.append(f"Summary: {summary} ({len(findings)} findings)")
    return "\n".join(lines)


def findings_to_dict(findings: list[Finding]) -> list[dict]:
    return [
        {
            "rule": f.rule_id,
            "severity": f.severity,
            "location": f.location,
            "message": f.message,
            "explanation": f.explanation,
            "rule_url": f.rule_url,
        }
        for f in findings
    ]


def render_json(findings: list[Finding], base_label: str, head_label: str) -> str:
    payload = {
        "tool": "contractguard",
        "base": base_label,
        "head": head_label,
        "summary": {
            sev: sum(1 for f in findings if f.severity == sev)
            for sev in ("BREAKING", "WARNING", "SAFE", "UNKNOWN")
        },
        "findings": findings_to_dict(findings),
    }
    return json.dumps(payload, indent=2)


def render_sarif(findings: list[Finding], base_label: str, head_label: str) -> str:
    """SARIF 2.1.0 output for GitHub code scanning / CI automation."""
    level_map = {
        "BREAKING": "error",
        "WARNING": "warning",
        "SAFE": "note",
        "UNKNOWN": "warning",
    }
    rules = []
    seen: set[str] = set()
    for finding in findings:
        if finding.rule_id in seen:
            continue
        seen.add(finding.rule_id)
        rules.append(
            {
                "id": finding.rule_id,
                "name": finding.rule_id,
                "shortDescription": {"text": finding.message},
                "fullDescription": {"text": finding.explanation},
                "helpUri": finding.rule_url,
                "defaultConfiguration": {"level": level_map[finding.severity]},
            }
        )
    results = [
        {
            "ruleId": f.rule_id,
            "level": level_map[f.severity],
            "message": {"text": f"{f.severity}: {f.message} ({f.explanation})"},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": head_label},
                        "region": {"startLine": 1},
                    }
                }
            ],
        }
        for f in findings
    ]
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ContractGuard",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/hitender12/contractguard",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, indent=2)


def render_markdown(findings: list[Finding], base_label: str, head_label: str) -> str:
    lines = [
        "## ContractGuard report",
        "",
        f"Base: `{base_label}` → Head: `{head_label}`",
        "",
    ]
    if not findings:
        lines.append("No changes detected. Contracts are identical.")
        return "\n".join(lines)
    counts = {sev: 0 for sev in ("BREAKING", "WARNING", "SAFE", "UNKNOWN")}
    for finding in findings:
        counts[finding.severity] += 1
    lines.append("| Severity | Count |")
    lines.append("|---|---|")
    for sev, count in counts.items():
        if count:
            lines.append(f"| {sev} | {count} |")
    lines.append("")
    lines.append("| Severity | Rule | Change |")
    lines.append("|---|---|---|")
    for finding in findings:
        lines.append(
            f"| {finding.severity} | {finding.rule_id} | {finding.message} |"
        )
    lines.append("")
    lines.append("### Details")
    lines.append("")
    for finding in findings:
        lines.append(f"#### {finding.severity}: {finding.message}")
        lines.append("")
        lines.append(f"- **Location:** `{finding.location}`")
        lines.append(f"- **Rule:** {finding.rule_id} ({finding.rule_url})")
        lines.append(f"- **Why it matters:** {finding.explanation}")
        lines.append("")
    return "\n".join(lines)
