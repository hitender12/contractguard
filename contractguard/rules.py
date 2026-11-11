"""Compatibility rules with clear severity and direction.

Two profiles:
- ``server`` -- "Will existing clients keep working against the new
  server?" (the default; this is what a backend PR check usually means.)
- ``client`` -- "Will the new client keep working against existing
  servers?" (use when the contract describes what a client will do.)

Every rule documents its direction (request vs response) and its severity
under each profile. When the tool cannot confidently determine
compatibility it reports UNKNOWN instead of guessing -- see R21/R24.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .diff import Change

SEVERITIES = ("BREAKING", "WARNING", "SAFE", "UNKNOWN")
PROFILES = ("server", "client")


@dataclass
class Finding:
    rule_id: str
    severity: str
    location: str
    message: str
    explanation: str
    change_kind: str = ""
    rule_url: str = ""

    def __post_init__(self):
        if not self.rule_url:
            self.rule_url = f"docs/rules.md#{self.rule_id.lower()}"


@dataclass
class Rule:
    rule_id: str
    name: str
    description: str
    direction: str  # request | response | both | meta
    server: str | None  # severity, or None when the rule decides per-change
    client: str | None

    def severity_for(self, profile: str, change: Change) -> str:
        raise NotImplementedError


def _direction(change: Change) -> str:
    return str(change.detail.get("direction", "both"))


def _fmt_type(value) -> str:
    return "absent" if value is None else str(value)


# ---------------------------------------------------------------------------
# Rule implementations. Each takes a Change and a profile and returns a
# Finding (or None when the change is not a compatibility event at all).
# ---------------------------------------------------------------------------


def _r01(change: Change, profile: str) -> Finding:
    return Finding(
        "R01", "BREAKING", change.location,
        f"{change.location} removed",
        "Existing clients calling this endpoint will get 404 / not-found "
        "errors. Removing an operation is the most direct breaking change.",
        change.kind,
    )


def _r02(change: Change, profile: str) -> Finding:
    return Finding(
        "R02", "SAFE", change.location,
        f"{change.location} added",
        "A new operation does not affect existing clients.",
        change.kind,
    )


def _r03(change: Change, profile: str) -> Finding:
    return Finding(
        "R03", "BREAKING", change.location,
        f"response {change.location.split('> response ')[-1]} removed",
        "Clients expecting this status code will no longer receive it.",
        change.kind,
    )


def _r04(change: Change, profile: str) -> Finding:
    return Finding(
        "R04", "SAFE", change.location,
        f"response {change.location.split('> response ')[-1]} added",
        "A new response status does not affect existing clients.",
        change.kind,
    )


def _r05(change: Change, profile: str) -> Finding:
    required = bool(change.detail.get("required"))
    if required:
        return Finding(
            "R05",
            "BREAKING" if profile == "server" else "WARNING",
            change.location,
            f"new required request parameter {change.location.split('parameter ')[-1]}",
            "Server profile: existing callers do not send this parameter and "
            "will be rejected. Client profile: new callers send a parameter "
            "older servers may reject under strict validation.",
            change.kind,
        )
    return Finding(
        "R06", "SAFE", change.location,
        f"new optional request parameter {change.location.split('parameter ')[-1]}",
        "Existing callers are unaffected; the parameter may simply be omitted.",
        change.kind,
    )


def _r07(change: Change, profile: str) -> Finding:
    was_required = bool(change.detail.get("was_required"))
    if was_required:
        return Finding(
            "R07",
            "SAFE" if profile == "server" else "BREAKING",
            change.location,
            f"required request parameter {change.location.split('parameter ')[-1]} removed",
            "Server profile: the server no longer requires the value, so old "
            "callers keep working (the value is ignored). Client profile: a "
            "new client will not send a value that existing servers require.",
            change.kind,
        )
    return Finding(
        "R08", "SAFE", change.location,
        f"optional request parameter {change.location.split('parameter ')[-1]} removed",
        "No caller was required to send it, so nothing breaks.",
        change.kind,
    )


def _r09(change: Change, profile: str) -> Finding:
    base, head = change.detail.get("base"), change.detail.get("head")
    if base is False and head is True:
        return Finding(
            "R09",
            "BREAKING" if profile == "server" else "SAFE",
            change.location,
            f"request parameter {change.location.split('parameter ')[-1]} is now required",
            "Server profile: existing callers that omit the parameter will be "
            "rejected. Client profile: the new client always sends it.",
            change.kind,
        )
    return Finding(
        "R10",
        "SAFE" if profile == "server" else "BREAKING",
        change.location,
        f"request parameter {change.location.split('parameter ')[-1]} is now optional",
        "Server profile: the server accepts more requests than before. "
        "Client profile: a new client may omit a value that existing "
        "servers still require.",
        change.kind,
    )


def _r11(change: Change, profile: str) -> Finding:
    return Finding(
        "R11", "BREAKING", change.location,
        f"request parameter {change.location.split('parameter ')[-1]} moved "
        f"from {change.detail.get('base')} to {change.detail.get('head')}",
        "Callers send the value in the old location; the server reads the new one.",
        change.kind,
    )


def _r12(change: Change, profile: str) -> Finding:
    required = bool(change.detail.get("required"))
    if required:
        return Finding(
            "R12",
            "BREAKING" if profile == "server" else "WARNING",
            change.location,
            "new required request body",
            "Server profile: existing callers send no body and will be "
            "rejected. Client profile: older servers may reject an "
            "unexpected body under strict validation.",
            change.kind,
        )
    return Finding(
        "R13", "SAFE", change.location,
        "new optional request body",
        "Existing callers are unaffected.",
        change.kind,
    )


def _r14(change: Change, profile: str) -> Finding:
    return Finding(
        "R14",
        "SAFE" if profile == "server" else "BREAKING",
        change.location,
        "request body removed",
        "Server profile: the server no longer reads a body, so old callers "
        "keep working. Client profile: a new client sends no body to "
        "servers that still require one.",
        change.kind,
    )


def _r15(change: Change, profile: str) -> Finding:
    base, head = change.detail.get("base"), change.detail.get("head")
    if base is False and head is True:
        return Finding(
            "R15",
            "BREAKING" if profile == "server" else "SAFE",
            change.location,
            "request body is now required",
            "Server profile: existing callers that send no body will be "
            "rejected. Client profile: the new client always sends a body.",
            change.kind,
        )
    return Finding(
        "R16",
        "SAFE" if profile == "server" else "BREAKING",
        change.location,
        "request body is now optional",
        "Server profile: the server accepts requests without a body. "
        "Client profile: a new client may omit a body that existing "
        "servers still require.",
        change.kind,
    )


def _field_name(location: str) -> str:
    return location.rsplit(".", 1)[-1].strip("[]")


def _r17(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    required = bool(change.detail.get("required"))
    name = _field_name(change.location)
    if direction == "response":
        return Finding(
            "R17",
            "SAFE" if profile == "server" else "WARNING",
            change.location,
            f"{'required' if required else 'optional'} response field "
            f"`{name}` added",
            "Server profile: the server now sends more data; old clients "
            "ignore unknown fields. Client profile: a new client reading a "
            "required field will fail against older servers that do not "
            "send it."
            if required
            else "Added response data does not affect existing clients.",
            change.kind,
        )
    if required:
        return Finding(
            "R17",
            "BREAKING" if profile == "server" else "WARNING",
            change.location,
            f"new required request field `{name}`",
            "Server profile: existing callers do not send this field and "
            "will be rejected. Client profile: older servers may reject an "
            "unknown required field under strict validation.",
            change.kind,
        )
    return Finding(
        "R17", "SAFE", change.location,
        f"new optional request field `{name}`",
        "Existing callers are unaffected.",
        change.kind,
    )


def _r18(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    was_required = bool(change.detail.get("was_required"))
    name = _field_name(change.location)
    if direction == "response":
        return Finding(
            "R18", "BREAKING", change.location,
            f"response field `{name}` removed",
            "Consumers reading this field will get missing data or null "
            "where they previously got a value.",
            change.kind,
        )
    if was_required:
        return Finding(
            "R18",
            "WARNING" if profile == "server" else "BREAKING",
            change.location,
            f"required request field `{name}` removed",
            "Server profile: the server no longer uses the value, so old "
            "callers keep working -- but any behavior driven by that field "
            "is gone. Client profile: a new client will not send a value "
            "that existing servers require.",
            change.kind,
        )
    return Finding(
        "R18", "SAFE", change.location,
        f"optional request field `{name}` removed",
        "No caller was required to send it.",
        change.kind,
    )


def _r19(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    name = _field_name(change.location)
    if direction == "response":
        return Finding(
            "R19", "WARNING", change.location,
            f"response field `{name}` is now optional",
            "The server may now omit this field. Clients that read it "
            "unconditionally can break.",
            change.kind,
        )
    return Finding(
        "R19",
        "SAFE" if profile == "server" else "BREAKING",
        change.location,
        f"request field `{name}` is now optional",
        "Server profile: the server accepts requests without the field. "
        "Client profile: a new client may omit a field that existing "
        "servers still require.",
        change.kind,
    )


def _r20(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    name = _field_name(change.location)
    if direction == "response":
        return Finding(
            "R20",
            "SAFE" if profile == "server" else "WARNING",
            change.location,
            f"response field `{name}` is now required",
            "Server profile: the server guarantees the field more strongly. "
            "Client profile: a new client assuming the field is present "
            "will fail against older servers that may omit it.",
            change.kind,
        )
    return Finding(
        "R20",
        "BREAKING" if profile == "server" else "SAFE",
        change.location,
        f"request field `{name}` is now required",
        "Server profile: existing callers that omit the field will be "
        "rejected. Client profile: the new client always sends it.",
        change.kind,
    )


def _r21(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    name = _field_name(change.location)
    return Finding(
        "R21", "BREAKING", change.location,
        f"{direction} field `{name}` changed from "
        f"{_fmt_type(change.detail.get('base'))} to "
        f"{_fmt_type(change.detail.get('head'))}",
        "Consumers parse this value as the old type; a different type "
        "breaks deserialization, validation, and downstream logic.",
        change.kind,
    )


def _r22(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    name = _field_name(change.location)
    return Finding(
        "R22", "UNKNOWN", change.location,
        f"{direction} field `{name}` format changed from "
        f"{_fmt_type(change.detail.get('base'))} to "
        f"{_fmt_type(change.detail.get('head'))}",
        "A format change (e.g. date-time to date, int32 to int64) may or "
        "may not break clients depending on how strictly they validate. "
        "ContractGuard cannot decide this from the schema alone.",
        change.kind,
    )


def _r23(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    name = _field_name(change.location)
    base_nullable = bool(change.detail.get("base"))
    if base_nullable is False:  # became nullable
        return Finding(
            "R23", "WARNING", change.location,
            f"{direction} field `{name}` is now nullable",
            "Strict clients that do not expect null can break. Lenient "
            "clients are unaffected.",
            change.kind,
        )
    if direction == "request":
        return Finding(
            "R23",
            "BREAKING" if profile == "server" else "SAFE",
            change.location,
            f"request field `{name}` is no longer nullable",
            "Server profile: existing callers that send null will be "
            "rejected. Client profile: the new client never sends null.",
            change.kind,
        )
    return Finding(
        "R23", "SAFE", change.location,
        f"response field `{name}` is no longer nullable",
        "The server guarantees a non-null value more strongly.",
        change.kind,
    )


def _r24(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    name = _field_name(change.location)
    removed = change.detail.get("removed") or []
    added = change.detail.get("added") or []
    if removed:
        return Finding(
            "R24",
            "BREAKING" if (profile == "server" or direction == "response") else "SAFE",
            change.location,
            f"{direction} field `{name}` enum narrowed: removed "
            f"{', '.join(repr(v) for v in removed)}",
            "Server profile / response: existing clients or servers relying "
            "on the removed values will break. Client profile, request: a "
            "new client only sends values the old server still accepts."
            if not (profile == "server" or direction == "response")
            else "Values that existing clients or servers rely on are no "
            "longer valid.",
            change.kind,
        )
    return Finding(
        "R24", "SAFE", change.location,
        f"{direction} field `{name}` enum widened: added "
        f"{', '.join(repr(v) for v in added)}",
        "Existing values remain valid; new values are simply available.",
        change.kind,
    )


def _r25(change: Change, profile: str) -> Finding:
    return Finding(
        "R25", "UNKNOWN", change.location,
        f"schema at `{change.location}` uses anyOf/oneOf/not and changed",
        "Composite schemas (anyOf / oneOf / not) cannot be compared field "
        "by field. A human must review whether the allowed value set "
        "narrowed.",
        change.kind,
    )


def _r26(change: Change, profile: str) -> Finding:
    return Finding(
        "R26", "BREAKING", change.location,
        f"schema at `{change.location}` removed",
        "The value that used to be here is gone entirely.",
        change.kind,
    )


def _r27(change: Change, profile: str) -> Finding:
    base = change.detail.get("base")
    head = change.detail.get("head")
    added = bool(head) and not bool(base)
    if added:
        return Finding(
            "R27", "WARNING", change.location,
            "new security requirement added",
            "Clients without the new credentials will be rejected. "
            "Existing authenticated clients are unaffected if they already "
            "meet the requirement.",
            change.kind,
        )
    return Finding(
        "R27", "SAFE", change.location,
        "security requirement removed",
        "Fewer credentials are required than before.",
        change.kind,
    )


_HANDLERS = {
    "operation-removed": _r01,
    "operation-added": _r02,
    "response-removed": _r03,
    "response-added": _r04,
    "parameter-added": _r05,
    "parameter-removed": _r07,
    "parameter-required-changed": _r09,
    "parameter-location-changed": _r11,
    "request-body-added": _r12,
    "request-body-removed": _r14,
    "request-body-required-changed": _r15,
    "schema-field-added": _r17,
    "schema-field-removed": _r18,
    "schema-field-required-to-optional": _r19,
    "schema-field-optional-to-required": _r20,
    "schema-type-changed": _r21,
    "schema-format-changed": _r22,
    "schema-nullable-changed": _r23,
    "schema-enum-changed": _r24,
    "schema-composite-changed": _r25,
    "schema-removed": _r26,
    "security-changed": _r27,
    "global-security-changed": _r27,
}

# Human-readable rule catalog used by `contractguard rules` and docs.
RULES = [
    ("R01", "operation-removed", "both", "BREAKING", "BREAKING",
     "An operation (method + path) was removed."),
    ("R02", "operation-added", "both", "SAFE", "SAFE",
     "A new operation was added."),
    ("R03", "response-removed", "response", "BREAKING", "BREAKING",
     "A response status code was removed."),
    ("R04", "response-added", "response", "SAFE", "SAFE",
     "A new response status code was added."),
    ("R05", "parameter-added (required)", "request", "BREAKING", "WARNING",
     "A new required request parameter was added."),
    ("R06", "parameter-added (optional)", "request", "SAFE", "SAFE",
     "A new optional request parameter was added."),
    ("R07", "parameter-removed (was required)", "request", "SAFE", "BREAKING",
     "A required request parameter was removed."),
    ("R08", "parameter-removed (optional)", "request", "SAFE", "SAFE",
     "An optional request parameter was removed."),
    ("R09", "parameter optional -> required", "request", "BREAKING", "SAFE",
     "A request parameter became required."),
    ("R10", "parameter required -> optional", "request", "SAFE", "BREAKING",
     "A request parameter became optional."),
    ("R11", "parameter-location-changed", "request", "BREAKING", "BREAKING",
     "A parameter moved to a different location (query/header/path)."),
    ("R12", "request-body-added (required)", "request", "BREAKING", "WARNING",
     "A new required request body was added."),
    ("R13", "request-body-added (optional)", "request", "SAFE", "SAFE",
     "A new optional request body was added."),
    ("R14", "request-body-removed", "request", "SAFE", "BREAKING",
     "The request body was removed."),
    ("R15", "request-body optional -> required", "request", "BREAKING", "SAFE",
     "The request body became required."),
    ("R16", "request-body required -> optional", "request", "SAFE", "BREAKING",
     "The request body became optional."),
    ("R17", "schema-field-added", "both", "depends", "depends",
     "A schema field was added (severity depends on direction/required)."),
    ("R18", "schema-field-removed", "both", "depends", "depends",
     "A schema field was removed (severity depends on direction/required)."),
    ("R19", "schema-field required -> optional", "both", "depends", "depends",
     "A schema field became optional."),
    ("R20", "schema-field optional -> required", "both", "depends", "depends",
     "A schema field became required."),
    ("R21", "schema-type-changed", "both", "BREAKING", "BREAKING",
     "A field's type changed (e.g. string -> integer)."),
    ("R22", "schema-format-changed", "both", "UNKNOWN", "UNKNOWN",
     "A field's format changed; impact cannot be decided from the schema."),
    ("R23", "schema-nullable-changed", "both", "depends", "depends",
     "A field's nullability changed."),
    ("R24", "schema-enum-changed", "both", "depends", "depends",
     "An enum narrowed (breaking) or widened (safe)."),
    ("R25", "schema-composite-changed", "both", "UNKNOWN", "UNKNOWN",
     "An anyOf/oneOf/not schema changed; impact needs human review."),
    ("R26", "schema-removed", "both", "BREAKING", "BREAKING",
     "A schema disappeared from a parameter, body, or response."),
    ("R27", "security-changed", "both", "WARNING", "WARNING",
     "Authentication/authorization requirements changed."),
]


def classify(changes: list[Change], profile: str = "server") -> list[Finding]:
    """Map raw diff changes to compatibility findings under a profile."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; expected one of {PROFILES}")
    findings: list[Finding] = []
    for change in changes:
        handler = _HANDLERS.get(change.kind)
        if handler is None:
            findings.append(
                Finding(
                    "R00", "UNKNOWN", change.location,
                    f"unclassified change: {change.kind}",
                    "ContractGuard does not have a rule for this change kind. "
                    "Reported as unknown rather than guessed.",
                    change.kind,
                )
            )
            continue
        findings.append(handler(change, profile))
    # Deterministic order: severity rank, then location, then rule.
    rank = {"BREAKING": 0, "UNKNOWN": 1, "WARNING": 2, "SAFE": 3}
    findings.sort(key=lambda f: (rank.get(f.severity, 9), f.location, f.rule_id))
    return findings
