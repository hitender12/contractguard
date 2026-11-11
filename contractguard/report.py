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


def render_terminal(findings: list[Finding], base_label: str, head_label: str,
                    policy=None) -> str:
    lines = [f"ContractGuard: {base_label} -> {head_label}", ""]
    if not findings:
        lines.append("No changes detected. Contracts are identical.")
        return "\n".join(lines)
    for finding in findings:
        if policy is not None:
            outcome = policy.classify_finding(finding)
            marker = {"fail": "FAIL", "warn": "WARN", "pass": "ok"}[outcome]
            lines.append(f"[{marker}] {finding.severity}: {finding.message}")
        else:
            lines.append(f"{finding.severity}: {finding.message}")
        if finding.explanation:
            lines.append(f"    {finding.explanation} [{finding.rule_id}]")
    counts = {sev: 0 for sev in ("BREAKING", "WARNING", "SAFE", "UNKNOWN")}
    for finding in findings:
        counts[finding.severity] += 1
    summary = ", ".join(f"{n} {sev.lower()}" for sev, n in counts.items() if n)
    lines.append("")
    lines.append(f"Summary: {summary} ({len(findings)} findings)")
    if policy is not None:
        outcome_counts = policy.summary_counts(findings)
        lines.append(
            "Policy: "
            f"{outcome_counts['fail']} fail, {outcome_counts['warn']} warn, "
            f"{outcome_counts['pass']} pass "
            f"(fail_on={list(policy.fail_on)}, warn_on={list(policy.warn_on)})"
        )
    return "\n".join(lines)


def findings_to_dict(findings: list[Finding]) -> list[dict]:
    result = []
    for f in findings:
        entry = {
            "rule": f.rule_id,
            "severity": f.severity,
            "location": f.location,
            "message": f.message,
            "explanation": f.explanation,
            "rule_url": f.rule_url,
        }
        if f.line is not None:
            entry["line"] = f.line
        result.append(entry)
    return result


def render_json(findings: list[Finding], base_label: str, head_label: str,
                policy=None) -> str:
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
    if policy is not None:
        payload["policy"] = {
            "profile": policy.profile,
            "fail_on": list(policy.fail_on),
            "warn_on": list(policy.warn_on),
            "outcomes": policy.summary_counts(findings),
            "warnings": [
                f.rule_id for f in policy.warns(findings)
            ],
        }
    return json.dumps(payload, indent=2)


def render_sarif(findings: list[Finding], base_label: str, head_label: str) -> str:
    """SARIF 2.1.0 output for GitHub code scanning / CI automation.

    Locations use the real source line of the changed node when the
    spec was YAML (tracked from the parser); when the line is unknown
    (JSON specs, or changes with no single node) the region is omitted
    rather than fabricated -- SARIF allows a location without a region.
    """
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
    results = []
    for f in findings:
        physical_location = {
            "artifactLocation": {"uri": head_label},
        }
        if f.line is not None:
            physical_location["region"] = {"startLine": f.line}
        results.append(
            {
                "ruleId": f.rule_id,
                "level": level_map[f.severity],
                "message": {"text": f"{f.severity}: {f.message} ({f.explanation})"},
                "locations": [{"physicalLocation": physical_location}],
            }
        )
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


def render_markdown(findings: list[Finding], base_label: str, head_label: str,
                    policy=None) -> str:
    lines = [
        "## ContractGuard report",
        "",
        f"Base: `{base_label}` → Head: `{head_label}`",
        "",
    ]
    if policy is not None:
        outcome_counts = policy.summary_counts(findings)
        lines.append(
            f"Policy: {outcome_counts['fail']} fail, "
            f"{outcome_counts['warn']} warn, {outcome_counts['pass']} pass "
            f"(fail_on={list(policy.fail_on)}, warn_on={list(policy.warn_on)})"
        )
        lines.append("")
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
