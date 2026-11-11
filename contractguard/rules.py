"""Compatibility rules with clear severity and direction.

Two profiles:
- ``server`` -- "Will existing clients keep working against the new
  server?" (the default; this is what a backend PR check usually means.)
- ``client`` -- "Will the new client keep working against existing
  servers?" (use when the contract describes what a client will do.)

Every rule documents its direction (request vs response) and its severity
under each profile. When the tool cannot confidently determine
compatibility it reports UNKNOWN instead of guessing -- see R22/R25.
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
    # Source line (1-based) of the changed node in the head spec (or the
    # base spec for removals), when known from a YAML input. None for
    # JSON specs. SARIF uses it for a real region; it is omitted there
    # when unknown rather than fabricated.
    line: int | None = None

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
        if required:
            return Finding(
                "R17",
                "SAFE" if profile == "server" else "WARNING",
                change.location,
                f"required response field `{name}` added",
                "Server profile: the server now guarantees the field. "
                "Client profile: a new client reading a required field "
                "will fail against older servers that do not send it.",
                change.kind,
            )
        return Finding(
            "R17", "SAFE", change.location,
            f"optional response field `{name}` added",
            "Added response data does not affect existing clients; old "
            "clients ignore unknown fields.",
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
        if direction == "request":
            return Finding(
                "R23", "SAFE", change.location,
                f"request field `{name}` is now nullable",
                "The server accepts null for this field, so existing "
                "callers that send null keep working and callers that "
                "never send null are unaffected.",
                change.kind,
            )
        return Finding(
            "R23", "WARNING", change.location,
            f"response field `{name}` is now nullable",
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
    base = change.detail.get("base") or []
    head = change.detail.get("head") or []

    def _req_set(reqs) -> set:
        # Normalize each security requirement to (scheme, scopes) pairs
        # so added / removed / swapped requirements are distinguished.
        out: set = set()
        for req in reqs:
            if isinstance(req, dict):
                for scheme, scopes in req.items():
                    out.add((str(scheme), tuple(scopes or [])))
        return out

    base_set = _req_set(base)
    head_set = _req_set(head)
    added = sorted(head_set - base_set)
    removed = sorted(base_set - head_set)
    if added and removed:
        return Finding(
            "R27", "WARNING", change.location,
            "security requirements changed (added: "
            + ", ".join(f"{s} [{', '.join(sc)}]" if sc else s for s, sc in added)
            + "; removed: "
            + ", ".join(f"{s} [{', '.join(sc)}]" if sc else s for s, sc in removed)
            + ")",
            "Clients authenticated with the old requirements may be "
            "rejected, and new requirements may need credentials they "
            "do not have.",
            change.kind,
        )
    if added:
        return Finding(
            "R27", "WARNING", change.location,
            "new security requirement added ("
            + ", ".join(f"{s} [{', '.join(sc)}]" if sc else s for s, sc in added)
            + ")",
            "Clients without the new credentials will be rejected. "
            "Existing authenticated clients are unaffected if they already "
            "meet the requirement.",
            change.kind,
        )
    if removed:
        return Finding(
            "R27", "SAFE", change.location,
            "security requirement removed ("
            + ", ".join(f"{s} [{', '.join(sc)}]" if sc else s for s, sc in removed)
            + ")",
            "Fewer credentials are required than before.",
            change.kind,
        )
    # The lists differ but the requirement sets are identical (e.g. a
    # reorder): no effective change.
    return Finding(
        "R27", "SAFE", change.location,
        "security requirements reordered (no effective change)",
        "The same schemes and scopes are required; only their order "
        "changed.",
        change.kind,
    )


def _r27_scheme(change: Change, profile: str) -> Finding:
    added = change.detail.get("added") or []
    removed = change.detail.get("removed") or []
    changed = change.detail.get("changed") or []
    parts = []
    if added:
        parts.append(f"added schemes: {', '.join(added)}")
    if removed:
        parts.append(f"removed schemes: {', '.join(removed)}")
    if changed:
        parts.append(f"changed schemes: {', '.join(changed)}")
    return Finding(
        "R27", "WARNING", change.location,
        "security scheme changed (" + "; ".join(parts) + ")",
        "A security scheme definition changed (for example an OAuth flow "
        "or scope). Clients authenticating with the old definition may "
        "be rejected or may lose access to scopes they relied on.",
        change.kind,
    )


def _r28(change: Change, profile: str) -> Finding:
    added = change.detail.get("added") or []
    removed = change.detail.get("removed") or []
    changed = change.detail.get("changed") or []
    parts = []
    if added:
        parts.append(f"added unknown keywords: {', '.join(added)}")
    if removed:
        parts.append(f"removed unknown keywords: {', '.join(removed)}")
    if changed:
        parts.append(f"changed unknown keywords: {', '.join(changed)}")
    return Finding(
        "R28", "UNKNOWN", change.location,
        f"schema at `{change.location}` has unknown keywords that changed "
        f"({'; '.join(parts)})",
        "The schema uses keywords ContractGuard does not understand, and "
        "their values changed. Whether that breaks clients cannot be "
        "decided from the schema alone; a human must review.",
        change.kind,
    )


def _r29(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    removed = change.detail.get("removed") or []
    added = change.detail.get("added") or []
    if direction == "response":
        return Finding(
            "R29", "BREAKING", change.location,
            f"response media type changed "
            f"({', '.join(removed) or 'none'} -> {', '.join(added) or 'none'})",
            "Clients parse the response body as the old media type; a "
            "different media type breaks deserialization.",
            change.kind,
        )
    return Finding(
        "R29",
        "BREAKING" if profile == "server" else "WARNING",
        change.location,
        f"request media type changed "
        f"({', '.join(removed) or 'none'} -> {', '.join(added) or 'none'})",
        "Server profile: existing callers send the old media type and "
        "will be rejected. Client profile: older servers may reject a "
        "body in the new media type.",
        change.kind,
    )


def _r30(change: Change, profile: str) -> Finding:
    direction = _direction(change)
    name = _field_name(change.location)
    change_kind = change.detail.get("change")
    base = change.detail.get("base")
    head = change.detail.get("head")
    if change_kind == "more-permissive":
        if direction == "response":
            return Finding(
                "R30", "SAFE", change.location,
                f"response field `{name}` additionalProperties became "
                f"more permissive ({base} -> {head})",
                "The server may send additional properties; old clients "
                "ignore unknown fields.",
                change.kind,
            )
        return Finding(
            "R30",
            "SAFE" if profile == "server" else "WARNING",
            change.location,
            f"request field `{name}` additionalProperties became "
            f"more permissive ({base} -> {head})",
            "Server profile: the server accepts more properties than "
            "before. Client profile: a new client may send additional "
            "properties that older servers reject.",
            change.kind,
        )
    # more-restrictive
    if direction == "response":
        return Finding(
            "R30", "WARNING", change.location,
            f"response field `{name}` additionalProperties became "
            f"more restrictive ({base} -> {head})",
            "The server may stop sending additional properties that "
            "clients read.",
            change.kind,
        )
    return Finding(
        "R30",
        "BREAKING" if profile == "server" else "SAFE",
        change.location,
        f"request field `{name}` additionalProperties became "
        f"more restrictive ({base} -> {head})",
        "Server profile: existing callers that send additional "
        "properties will be rejected. Client profile: the new client "
        "never sends additional properties.",
        change.kind,
    )


def _r31(change: Change, profile: str) -> Finding:
    was_deprecated = bool(change.detail.get("base"))
    what = {
        "operation-deprecated-changed": f"operation `{change.location}`",
        "parameter-deprecated-changed": (
            f"parameter {change.location.split('parameter ')[-1]}"
        ),
        "schema-deprecated-changed": f"schema at `{change.location}`",
    }.get(change.kind, f"`{change.location}`")
    if not was_deprecated:  # newly deprecated
        return Finding(
            "R31", "WARNING", change.location,
            f"{what} is now deprecated",
            "Deprecation does not break clients yet, but the operation, "
            "parameter, or field is scheduled for removal; clients "
            "should migrate.",
            change.kind,
        )
    return Finding(
        "R31", "SAFE", change.location,
        f"{what} is no longer deprecated",
        "The deprecation notice was removed; nothing breaks.",
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
    "security-scheme-changed": _r27_scheme,
    "schema-unknown-changed": _r28,
    "media-type-changed": _r29,
    "schema-additional-properties-changed": _r30,
    "operation-deprecated-changed": _r31,
    "parameter-deprecated-changed": _r31,
    "schema-deprecated-changed": _r31,
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
    ("R27", "security-changed", "both", "WARNING", "SAFE",
     "Authentication/authorization requirements changed (added is WARNING, "
     "removed is SAFE); security scheme definitions changed (WARNING)."),
    ("R28", "schema-unknown-changed", "both", "UNKNOWN", "UNKNOWN",
     "A schema keyword ContractGuard does not understand changed value."),
    ("R29", "media-type-changed", "both", "depends", "depends",
     "A request/response media type changed (severity depends on "
     "direction and profile)."),
    ("R30", "schema-additional-properties-changed", "both", "depends",
     "depends",
     "additionalProperties became more permissive or more restrictive."),
    ("R31", "deprecated-changed", "both", "depends", "depends",
     "An operation, parameter, or schema was marked deprecated (WARNING) "
     "or un-deprecated (SAFE)."),
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
                    line=change.line,
                )
            )
            continue
        finding = handler(change, profile)
        # Carry the change's source line through to the finding so
        # reports (SARIF, JSON) can point at the real location.
        finding.line = change.line
        findings.append(finding)
    # Deterministic order: severity rank, then location, then rule.
    rank = {"BREAKING": 0, "UNKNOWN": 1, "WARNING": 2, "SAFE": 3}
    findings.sort(key=lambda f: (rank.get(f.severity, 9), f.location, f.rule_id))
    return findings
