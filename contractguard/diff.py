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
    # Source line (1-based) of the changed node in the head spec (or the
    # base spec for removals), when known from a YAML input. None for
    # JSON specs. Carried through to findings and SARIF output.
    line: int | None = None

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


# JSON Schema / OpenAPI keywords the normalizer understands. Any other key
# found in a schema's raw mapping is an unknown keyword: the diff flags a
# change to it as UNKNOWN (R28) instead of silently dropping it.
KNOWN_SCHEMA_KEYS = {
    "type", "format", "nullable", "enum", "properties", "required",
    "items", "additionalProperties", "anyOf", "oneOf", "not", "allOf",
    "$ref", "description", "example", "examples", "default", "deprecated",
    "readOnly", "writeOnly", "xml", "externalDocs", "title",
    "discriminator", "minLength", "maxLength", "pattern", "minimum",
    "maximum", "minItems", "maxItems", "uniqueItems", "minProperties",
    "maxProperties", "multipleOf", "exclusiveMinimum", "exclusiveMaximum",
    "contentEncoding", "contentMediaType", "contentSchema",
}

# Permissiveness rank for additionalProperties values: False allows no
# extra properties, a schema restricts them, True (or an absent value,
# which JSON Schema treats as unrestricted) allows anything.
def _additional_properties_rank(value) -> int:
    if value is None or value is True:
        return 2
    if isinstance(value, Schema):
        return 1
    return 0  # False


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
            Change("schema-removed", location, {"direction": direction},
                   line=base.line)
        )
        return
    assert base is not None and head is not None

    # Recursive references are unexpanded markers (parser): their
    # content is the referenced schema, already expanded at its first
    # occurrence, so a content change to the target is caught there.
    # Comparing a marker field-by-field against an expanded schema
    # would report phantom additions/removals, so a marker is only
    # ever compared by reference identity. A change of reference (or
    # a reference replaced by an inline schema, or vice versa) is
    # R34 UNKNOWN: whether the new target is compatible cannot be
    # decided from the reference alone.
    if base.recursive_ref or head.recursive_ref:
        if base.ref != head.ref:
            changes.append(
                Change(
                    "schema-ref-changed",
                    location,
                    {
                        "direction": direction,
                        "base": base.ref,
                        "head": head.ref,
                    },
                    line=head.line or base.line,
                )
            )
        return

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
                    line=head.line or base.line,
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
                line=head.line or base.line,
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
                line=head.line or base.line,
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
                line=head.line or base.line,
            )
        )
    if base.deprecated != head.deprecated:
        changes.append(
            Change(
                "schema-deprecated-changed",
                location,
                {
                    "direction": direction,
                    "base": base.deprecated,
                    "head": head.deprecated,
                },
                line=head.line or base.line,
            )
        )
    if base.enum is not None or head.enum is not None:
        base_enum = list(base.enum or [])
        head_enum = list(head.enum or [])
        removed = [v for v in base_enum if v not in head_enum]
        added = [v for v in head_enum if v not in base_enum]
        # A pure reorder (same value set, different order) is not a
        # change: enums are unordered sets of allowed values.
        if removed or added:
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
                    line=head.line or base.line,
                )
            )
    # additionalProperties: two schemas are diffed recursively; a bool
    # against a schema (or bool against bool) is a permissiveness change.
    # An absent value is unrestricted, i.e. equivalent to True.
    base_ap = base.additional_properties
    head_ap = head.additional_properties
    if isinstance(base_ap, Schema) and isinstance(head_ap, Schema):
        _diff_schema(base_ap, head_ap, f"{location}.additionalProperties",
                     changes, direction)
    else:
        base_rank = _additional_properties_rank(base_ap)
        head_rank = _additional_properties_rank(head_ap)
        if base_rank != head_rank:
            def _ap_label(value) -> str:
                if value is None:
                    return "absent"
                if isinstance(value, Schema):
                    return "schema"
                return str(value)

            changes.append(
                Change(
                    "schema-additional-properties-changed",
                    location,
                    {
                        "direction": direction,
                        "base": _ap_label(base_ap),
                        "head": _ap_label(head_ap),
                        "change": (
                            "more-permissive" if head_rank > base_rank
                            else "more-restrictive"
                        ),
                    },
                    line=head.line or base.line,
                )
            )
    # Unknown keywords: anything in raw that is not a known JSON Schema /
    # OpenAPI keyword. A change to one is reported UNKNOWN (R28) rather
    # than silently dropped. (Constraint keywords such as minLength are
    # known but not yet compared; see ARCHITECTURE.md.)
    base_unknown = {k: v for k, v in (base.raw or {}).items() if k not in KNOWN_SCHEMA_KEYS}
    head_unknown = {k: v for k, v in (head.raw or {}).items() if k not in KNOWN_SCHEMA_KEYS}
    if base_unknown != head_unknown:
        changes.append(
            Change(
                "schema-unknown-changed",
                location,
                {
                    "direction": direction,
                    "added": sorted(set(head_unknown) - set(base_unknown)),
                    "removed": sorted(set(base_unknown) - set(head_unknown)),
                    "changed": sorted(
                        k for k in set(base_unknown) & set(head_unknown)
                        if base_unknown[k] != head_unknown[k]
                    ),
                },
                line=head.line or base.line,
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
                    line=head_props[name].line or head.line or base.line,
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
                    line=base_props[name].line or base.line,
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
                    line=head_props[name].line or base_props[name].line,
                )
            )
    for name in sorted(head_req - base_req):
        if name in base_props and name in head_props:
            changes.append(
                Change(
                    "schema-field-optional-to-required",
                    f"{location}.{name}",
                    {"direction": direction},
                    line=head_props[name].line or base_props[name].line,
                )
            )


def _diff_parameters(
    base: Operation, head: Operation, location: str, changes: list[Change]
) -> None:
    """Diff parameters, keyed by name so a location move is detected.

    Parameters are matched by name first: when a parameter exists on both
    sides under a different location (query -> header), that is a move
    (R11, BREAKING), not an add plus a remove. The same name in several
    locations on one side is ambiguous by name alone, so those fall back
    to the old (name, location) keying.
    """
    base_by_name: dict[str, list] = {}
    head_by_name: dict[str, list] = {}
    for p in base.parameters:
        base_by_name.setdefault(p.name, []).append(p)
    for p in head.parameters:
        head_by_name.setdefault(p.name, []).append(p)

    for name in sorted(set(base_by_name) | set(head_by_name)):
        b_list = base_by_name.get(name, [])
        h_list = head_by_name.get(name, [])
        if len(b_list) == 1 and len(h_list) == 1:
            _diff_one_parameter(b_list[0], h_list[0], location, changes)
            continue
        # Ambiguous name (same name in several locations): fall back to
        # (name, location) keying for this name only.
        base_params = {(p.name, p.location): p for p in b_list}
        head_params = {(p.name, p.location): p for p in h_list}
        for key in sorted(set(base_params) | set(head_params)):
            param_name, where = key
            param_loc = f"{location} > parameter {param_name} ({where})"
            if key not in base_params:
                changes.append(
                    Change(
                        "parameter-added",
                        param_loc,
                        {"required": head_params[key].required},
                        line=head_params[key].line,
                    )
                )
            elif key not in head_params:
                changes.append(
                    Change(
                        "parameter-removed",
                        param_loc,
                        {"was_required": base_params[key].required},
                        line=base_params[key].line,
                    )
                )
            else:
                _diff_one_parameter(
                    base_params[key], head_params[key], location, changes
                )


def _diff_one_parameter(bp, hp, location: str, changes: list[Change]) -> None:
    """Diff a single parameter present on both sides (matched by name)."""
    param_loc = f"{location} > parameter {bp.name} ({bp.location})"
    if bp.location != hp.location:
        changes.append(
            Change(
                "parameter-location-changed",
                param_loc,
                {"base": bp.location, "head": hp.location},
                line=hp.line or bp.line,
            )
        )
    if bp.required != hp.required:
        changes.append(
            Change(
                "parameter-required-changed",
                param_loc,
                {"base": bp.required, "head": hp.required},
                line=hp.line or bp.line,
            )
        )
    if bp.deprecated != hp.deprecated:
        changes.append(
            Change(
                "parameter-deprecated-changed",
                param_loc,
                {"base": bp.deprecated, "head": hp.deprecated},
                line=hp.line or bp.line,
            )
        )
    if bp.schema is not None or hp.schema is not None:
        _diff_schema(bp.schema, hp.schema, param_loc, changes, "request")


def _diff_media_types(base_content: dict, head_content: dict, location: str,
                      direction: str, changes: list[Change]) -> None:
    """Emit a media-type change when the content media types differ.

    A media-type change (application/json -> text/plain) is invisible to
    schema comparison -- the schemas may be identical -- but it breaks
    every client that parses the body as the old type.
    """
    base_types = sorted(base_content)
    head_types = sorted(head_content)
    if base_types != head_types:
        changes.append(
            Change(
                "media-type-changed",
                location,
                {
                    "direction": direction,
                    "removed": [m for m in base_types if m not in head_types],
                    "added": [m for m in head_types if m not in base_types],
                },
            )
        )


def _diff_operation(
    base: Operation, head: Operation, changes: list[Change]
) -> None:
    location = f"{base.method} {base.path}"
    _diff_parameters(base, head, location, changes)

    # operationId: the wire contract is unchanged by a rename, but
    # generated clients call the operation by this name, so a rename or
    # removal breaks them (R32). Adding one where there was none is safe.
    if base.operation_id != head.operation_id:
        changes.append(
            Change(
                "operation-id-changed",
                location,
                {"base": base.operation_id, "head": head.operation_id},
                line=head.line or base.line,
            )
        )

    if base.deprecated != head.deprecated:
        changes.append(
            Change(
                "operation-deprecated-changed",
                location,
                {"base": base.deprecated, "head": head.deprecated},
                line=head.line or base.line,
            )
        )

    # Request body.
    if base.request_body is None and head.request_body is not None:
        changes.append(
            Change(
                "request-body-added",
                location,
                {"required": head.request_body.required},
                line=head.request_body.line or head.line,
            )
        )
    elif base.request_body is not None and head.request_body is None:
        changes.append(
            Change(
                "request-body-removed", location, {},
                line=base.request_body.line or base.line,
            )
        )
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
                    line=head.request_body.line or base.request_body.line,
                )
            )
        _diff_media_types(
            base.request_body.content, head.request_body.content,
            f"{location} > request body", "request", changes,
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
            changes.append(
                Change("response-added", resp_loc, {},
                       line=head.responses[status].line or head.line)
            )
        elif status not in head.responses:
            changes.append(
                Change("response-removed", resp_loc, {},
                       line=base.responses[status].line or base.line)
            )
        else:
            _diff_media_types(
                base.responses[status].content,
                head.responses[status].content,
                resp_loc, "response", changes,
            )
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
                line=head.line or base.line,
            )
        )


def diff_contracts(base: Contract, head: Contract) -> list[Change]:
    """Return the semantic diff between two normalized contracts."""
    changes: list[Change] = []
    for key in sorted(set(base.operations) | set(head.operations)):
        method, path = key
        location = f"{method} {path}"
        if key not in base.operations:
            changes.append(
                Change("operation-added", location, {},
                       line=head.operations[key].line)
            )
        elif key not in head.operations:
            changes.append(
                Change("operation-removed", location, {},
                       line=base.operations[key].line)
            )
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

    # Top-level servers: a removed URL (or a changed default, the first
    # entry) breaks clients configured with it; adding a URL is safe.
    # Only URLs are compared, in order; descriptions and variables are
    # not stored in the model.
    if (base.servers or []) != (head.servers or []):
        base_servers = list(base.servers or [])
        head_servers = list(head.servers or [])
        changes.append(
            Change(
                "servers-changed",
                "servers",
                {
                    "base": base_servers,
                    "head": head_servers,
                    "added": [u for u in head_servers if u not in base_servers],
                    "removed": [u for u in base_servers if u not in head_servers],
                },
            )
        )

    # Security schemes: a changed OAuth flow or scope is a compatibility
    # event even when no operation's security requirement changed.
    base_schemes = base.security_schemes or {}
    head_schemes = head.security_schemes or {}
    if base_schemes != head_schemes:
        changes.append(
            Change(
                "security-scheme-changed",
                "components.securitySchemes",
                {
                    "added": sorted(set(head_schemes) - set(base_schemes)),
                    "removed": sorted(set(base_schemes) - set(head_schemes)),
                    "changed": sorted(
                        k for k in set(base_schemes) & set(head_schemes)
                        if base_schemes[k] != head_schemes[k]
                    ),
                },
            )
        )
    return changes
