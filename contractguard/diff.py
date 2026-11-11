"""Semantic diff engine.

Compares a base Contract against a head Contract and emits a flat list of
typed :class:`Change` objects. Classification into BREAKING / WARNING /
SAFE / UNKNOWN happens in :mod:`contractguard.rules` -- the diff itself
only describes *what* changed, never *how bad* it is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Contract, Operation, Schema

# Media types whose schemas are compared. Prefer an exact match, then any
# JSON media type, then the first available media type on each side.
JSON_MEDIA = ("application/json",)


@dataclass
class Change:
    """One semantic difference between base and head."""

    kind: str
    location: str
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.kind} at {self.location}"


def _pick_media(base: dict, head: dict):
    """Pick a comparable (base, head) media-type pair, or (None, None)."""
    if not base or not head:
        return None, None
    for media in JSON_MEDIA:
        if media in base and media in head:
            return base[media], head[media]
    for media in base:
        if media in head:
            return base[media], head[media]
    # Fall back to the first JSON-ish type on each side.
    base_json = next((m for m in base if "json" in m), None)
    head_json = next((m for m in head if "json" in m), None)
    if base_json and head_json:
        return base[base_json], head[head_json]
    return None, None


def _diff_schema(
    base: Schema | None,
    head: Schema | None,
    location: str,
    changes: list[Change],
    direction: str,
) -> None:
    """Diff two schemas recursively.

    direction is "request" or "response": it travels with the change so the
    rule engine can classify it in context.
    """
    if base is None and head is None:
        return
    if base is None and head is not None:
        # Schema appeared where none existed: handled by the caller as a
        # field/parameter addition, not here.
        return
    if base is not None and head is None:
        changes.append(
            Change("schema-removed", location, {"direction": direction})
        )
        return
    assert base is not None and head is not None

    if base.composite is not None or head.composite is not None:
        if (base.composite or {}) != (head.composite or {}):
            changes.append(
                Change(
                    "schema-composite-changed",
                    location,
                    {
                        "direction": direction,
                        "base": base.composite,
                        "head": head.composite,
                    },
                )
            )
        # Composite schemas are not flattened further: we cannot tell which
        # branch a consumer relies on.
        return

    if base.type != head.type:
        changes.append(
            Change(
                "schema-type-changed",
                location,
                {
                    "direction": direction,
                    "base": base.type,
                    "head": head.type,
                },
            )
        )
    if base.format != head.format:
        changes.append(
            Change(
                "schema-format-changed",
                location,
                {
                    "direction": direction,
                    "base": base.format,
                    "head": head.format,
                },
            )
        )
    if base.nullable != head.nullable:
        changes.append(
            Change(
                "schema-nullable-changed",
                location,
                {
                    "direction": direction,
                    "base": base.nullable,
                    "head": head.nullable,
                },
            )
        )
    if base.enum is not None or head.enum is not None:
        base_enum = list(base.enum or [])
        head_enum = list(head.enum or [])
        if base_enum != head_enum:
            removed = [v for v in base_enum if v not in head_enum]
            added = [v for v in head_enum if v not in base_enum]
            changes.append(
                Change(
                    "schema-enum-changed",
                    location,
                    {
                        "direction": direction,
                        "base": base_enum,
                        "head": head_enum,
                        "removed": removed,
                        "added": added,
                    },
                )
            )
    if base.items is not None or head.items is not None:
        _diff_schema(base.items, head.items, f"{location}[]", changes, direction)

    base_props = base.properties
    head_props = head.properties
    for name in sorted(set(base_props) | set(head_props)):
        prop_loc = f"{location}.{name}"
        if name not in base_props:
            changes.append(
                Change(
                    "schema-field-added",
                    prop_loc,
                    {
                        "direction": direction,
                        "required": name in head.required,
                        "type": head_props[name].type,
                    },
                )
            )
        elif name not in head_props:
            changes.append(
                Change(
                    "schema-field-removed",
                    prop_loc,
                    {
                        "direction": direction,
                        "was_required": name in base.required,
                        "type": base_props[name].type,
                    },
                )
            )
        else:
            _diff_schema(base_props[name], head_props[name], prop_loc, changes, direction)
    base_req = set(base.required)
    head_req = set(head.required)
    for name in sorted(base_req - head_req):
        if name in base_props and name in head_props:
            changes.append(
                Change(
                    "schema-field-required-to-optional",
                    f"{location}.{name}",
                    {"direction": direction},
                )
            )
    for name in sorted(head_req - base_req):
        if name in base_props and name in head_props:
            changes.append(
                Change(
                    "schema-field-optional-to-required",
                    f"{location}.{name}",
                    {"direction": direction},
                )
            )


def _diff_parameters(
    base: Operation, head: Operation, location: str, changes: list[Change]
) -> None:
    base_params = {(p.name, p.location): p for p in base.parameters}
    head_params = {(p.name, p.location): p for p in head.parameters}
    for key in sorted(set(base_params) | set(head_params)):
        name, where = key
        param_loc = f"{location} > parameter {name} ({where})"
        if key not in base_params:
            changes.append(
                Change(
                    "parameter-added",
                    param_loc,
                    {"required": head_params[key].required},
                )
            )
        elif key not in head_params:
            changes.append(
                Change(
                    "parameter-removed",
                    param_loc,
                    {"was_required": base_params[key].required},
                )
            )
        else:
            bp, hp = base_params[key], head_params[key]
            if bp.required != hp.required:
                changes.append(
                    Change(
                        "parameter-required-changed",
                        param_loc,
                        {"base": bp.required, "head": hp.required},
                    )
                )
            if bp.location != hp.location:
                changes.append(
                    Change(
                        "parameter-location-changed",
                        param_loc,
                        {"base": bp.location, "head": hp.location},
                    )
                )
            if bp.schema is not None or hp.schema is not None:
                _diff_schema(bp.schema, hp.schema, param_loc, changes, "request")


def _diff_operation(
    base: Operation, head: Operation, changes: list[Change]
) -> None:
    location = f"{base.method} {base.path}"
    _diff_parameters(base, head, location, changes)

    # Request body.
    if base.request_body is None and head.request_body is not None:
        changes.append(
            Change(
                "request-body-added",
                location,
                {"required": head.request_body.required},
            )
        )
    elif base.request_body is not None and head.request_body is None:
        changes.append(Change("request-body-removed", location, {}))
    elif base.request_body is not None and head.request_body is not None:
        if base.request_body.required != head.request_body.required:
            changes.append(
                Change(
                    "request-body-required-changed",
                    location,
                    {
                        "base": base.request_body.required,
                        "head": head.request_body.required,
                    },
                )
            )
        b_media, h_media = _pick_media(
            base.request_body.content, head.request_body.content
        )
        if b_media is not None and h_media is not None:
            _diff_schema(
                b_media.schema,
                h_media.schema,
                f"{location} > request body",
                changes,
                "request",
            )

    # Responses.
    for status in sorted(set(base.responses) | set(head.responses)):
        resp_loc = f"{location} > response {status}"
        if status not in base.responses:
            changes.append(Change("response-added", resp_loc, {}))
        elif status not in head.responses:
            changes.append(Change("response-removed", resp_loc, {}))
        else:
            b_media, h_media = _pick_media(
                base.responses[status].content, head.responses[status].content
            )
            if b_media is not None and h_media is not None:
                _diff_schema(
                    b_media.schema,
                    h_media.schema,
                    resp_loc,
                    changes,
                    "response",
                )

    # Security declarations.
    if (base.security or []) != (head.security or []):
        changes.append(
            Change(
                "security-changed",
                location,
                {"base": base.security, "head": head.security},
            )
        )


def diff_contracts(base: Contract, head: Contract) -> list[Change]:
    """Return the semantic diff between two normalized contracts."""
    changes: list[Change] = []
    for key in sorted(set(base.operations) | set(head.operations)):
        method, path = key
        location = f"{method} {path}"
        if key not in base.operations:
            changes.append(Change("operation-added", location, {}))
        elif key not in head.operations:
            changes.append(Change("operation-removed", location, {}))
        else:
            _diff_operation(base.operations[key], head.operations[key], changes)

    if (base.global_security or []) != (head.global_security or []):
        changes.append(
            Change(
                "global-security-changed",
                "security",
                {"base": base.global_security, "head": head.global_security},
            )
        )
    return changes
