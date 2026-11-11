"""Policy config: which severities fail CI, warn, or pass.

Default policy: BREAKING fails the check, WARNING and UNKNOWN are reported
but do not fail, SAFE passes silently. Teams override with a YAML/JSON
config file:

    # contractguard.yaml
    profile: server
    fail_on: [BREAKING]
    warn_on: [WARNING, UNKNOWN]

or with ``--fail-on`` / ``--warn-on`` on the command line.

Semantics:
- A finding whose severity is in ``fail_on`` FAILS the check (exit 1).
- A finding whose severity is in ``warn_on`` (and not in ``fail_on``) is
  a WARNING: it is reported prominently in every report format and
  counted in the policy summary, but it does not fail the check.
- Anything else PASSES silently as far as the policy is concerned
  (it is still listed in the findings).
- ``fail_on`` wins on overlap: a severity in both lists fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .parser import load_spec_text
from .rules import SEVERITIES

DEFAULT_FAIL_ON = ("BREAKING",)
DEFAULT_WARN_ON = ("WARNING", "UNKNOWN")


@dataclass
class Policy:
    profile: str = "server"
    fail_on: tuple[str, ...] = DEFAULT_FAIL_ON
    warn_on: tuple[str, ...] = DEFAULT_WARN_ON

    def __post_init__(self):
        for name in ("fail_on", "warn_on"):
            values = tuple(str(v).upper() for v in getattr(self, name))
            unknown = [v for v in values if v not in SEVERITIES]
            if unknown:
                raise ValueError(f"unknown severities in {name}: {unknown}")
            setattr(self, name, values)
        if self.profile not in ("server", "client"):
            raise ValueError(f"unknown profile {self.profile!r}")

    def classify_finding(self, finding) -> str:
        """Return "fail", "warn", or "pass" for one finding.

        ``fail_on`` wins when a severity is listed in both ``fail_on``
        and ``warn_on``.
        """
        if finding.severity in self.fail_on:
            return "fail"
        if finding.severity in self.warn_on:
            return "warn"
        return "pass"

    def fails(self, findings) -> bool:
        return any(f.severity in self.fail_on for f in findings)

    def warns(self, findings) -> list:
        """Findings that warn but do not fail: severity in warn_on only."""
        return [
            f for f in findings
            if f.severity in self.warn_on and f.severity not in self.fail_on
        ]

    def summary_counts(self, findings) -> dict[str, int]:
        """Count findings by policy outcome: {"fail": n, "warn": n, "pass": n}."""
        counts = {"fail": 0, "warn": 0, "pass": 0}
        for finding in findings:
            counts[self.classify_finding(finding)] += 1
        return counts

    def exit_code(self, findings) -> int:
        return 1 if self.fails(findings) else 0


def policy_from_dict(data: dict) -> Policy:
    if not isinstance(data, dict):
        raise ValueError("policy file must contain a mapping")
    return Policy(
        profile=str(data.get("profile", "server")),
        fail_on=tuple(data.get("fail_on", list(DEFAULT_FAIL_ON))),
        warn_on=tuple(data.get("warn_on", list(DEFAULT_WARN_ON))),
    )


def policy_from_file(path: str) -> Policy:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise ValueError(f"cannot read policy file {path}: {exc}") from exc
    return policy_from_dict(load_spec_text(text, path))
