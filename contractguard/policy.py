"""Policy config: which severities fail CI, warn, or pass.

Default policy: BREAKING fails the check, WARNING and UNKNOWN are reported
but do not fail, SAFE passes silently. Teams override with a YAML/JSON
config file:

    # contractguard.yaml
    profile: server
    fail_on: [BREAKING]
    warn_on: [WARNING, UNKNOWN]

or with ``--fail-on`` / ``--warn-on`` on the command line.
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

    def fails(self, findings) -> bool:
        return any(f.severity in self.fail_on for f in findings)

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
