"""OpenAPI parser and normalizer.

Loads JSON directly and YAML through the bundled subset parser, resolves
local ``$ref`` pointers (``#/components/...`` and ``#/paths/...``), and
produces a :class:`~contractguard.model.Contract`.

Limits, stated plainly:
- Only OpenAPI 3.x documents (``openapi: 3.*``). Swagger 2.0 is rejected
  with a clear error instead of being half-parsed.
- Only local ``$ref`` targets. Remote / file / URL references are rejected.
- Recursive ``$ref`` chains (for example a tree type whose ``child``
  property references itself) are terminated at the recursive reference:
  the reference is kept as an unexpanded marker (``Schema.recursive_ref``)
  instead of recursing forever, so the diff can still report a change of
  reference (R34). Genuinely circular ``$ref``-only chains and schemas
  nested more than 25 levels deep are rejected with a clear error.
- ``allOf`` is merged (properties + required union); ``anyOf`` / ``oneOf``
  are kept as composite schemas and flagged UNKNOWN by the diff engine.
"""

from __future__ import annotations

import json

from .model import (
    Contract,
    MediaType,
    Operation,
    Parameter,
    RequestBody,
    Response,
    Schema,
)
from .yamlmini import YAMLParseError, parse_yaml, parse_yaml_lines

SUPPORTED_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


class SpecError(ValueError):
    """Raised when a spec cannot be parsed or normalized."""


class RefError(SpecError):
    """Raised for unresolvable, remote, or circular ``$ref`` pointers."""


def load_spec_text(text: str, path: str = "<input>"):
    """Parse a spec document (JSON or YAML) into a plain Python dict."""
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SpecError(f"{path}: invalid JSON: {exc}") from exc
    try:
        return parse_yaml(text)
    except YAMLParseError as exc:
        raise SpecError(f"{path}: {exc}") from exc


def load_spec_with_lines(text: str, path: str = "<input>"):
    """Parse a spec document, returning (document, key-path -> line map).

    The line map is populated for YAML input (via ``parse_yaml_lines``)
    and empty for JSON input, which carries no source lines. It is used
    to give SARIF findings real line numbers.
    """
    stripped = text.lstrip()
    if stripped.startswith("{"):
        return load_spec_text(text, path), {}
    try:
        return parse_yaml(text), parse_yaml_lines(text)
    except YAMLParseError as exc:
        raise SpecError(f"{path}: {exc}") from exc


def load_spec_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise SpecError(f"cannot read {path}: {exc}") from exc
    return load_spec_text(text, path)


def _line(lines: dict | None, *keys) -> int | None:
    """Look up the source line for a key path, or None when unknown."""
    if not lines:
        return None
    return lines.get(tuple(keys))


class _Resolver:
    """Resolves local JSON-Pointer $refs within one document."""

    def __init__(self, root: dict):
        self.root = root
        self._resolving: list[str] = []

    def resolve(self, node):
        """Follow $ref chains and return the target node (or the node)."""
        seen: set[str] = set()
        current = node
        while isinstance(current, dict) and "$ref" in current:
            ref = current["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/"):
                raise RefError(
                    f"only local $ref pointers are supported, got {ref!r}"
                )
            if ref in seen:
                raise RefError(f"circular $ref detected: {' -> '.join(seen)} -> {ref}")
            seen.add(ref)
            current = self._lookup(ref)
            if current is None:
                raise RefError(f"unresolvable $ref: {ref}")
        return current

    def _lookup(self, ref: str):
        parts = ref[2:].split("/")
        node = self.root
        for part in parts:
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node


def _as_bool(value, default: bool = False) -> bool:
    return bool(value) if isinstance(value, bool) else default


def _normalize_schema(node, resolver: _Resolver, depth: int = 0,
                      path: tuple = (), lines: dict | None = None,
                      _active_refs: tuple[str, ...] = ()) -> Schema:
    """Normalize one schema node.

    ``_active_refs`` is the stack of ``$ref`` targets currently being
    expanded above this node. A reference to a target already on the
    stack is a recursive reference: return an unexpanded marker
    (``recursive_ref=True``) instead of expanding it again, which
    would recurse forever. A marker is safe to return because the
    target's content is already expanded at its first occurrence, so a
    change to the target is still caught there; the marker only has to
    carry the reference identity. The depth guard remains as a backstop
    for deeply nested inline schemas (no $ref involved).
    """
    if depth > 25:
        raise RefError("schema nesting too deep (over 25 levels)")
    if node is None:
        return Schema()
    if not isinstance(node, dict):
        raise SpecError(f"schema must be an object, got {node!r}")
    ref = node.get("$ref")
    if isinstance(ref, str) and ref in _active_refs:
        return Schema(
            ref=ref, raw=dict(node), recursive_ref=True,
            line=_line(lines, *path),
        )
    node = resolver.resolve(node)
    if not isinstance(node, dict):
        raise SpecError(f"$ref target must be an object, got {node!r}")
    # This node's $ref (if any) is on the stack while its target's
    # subtree is expanded, so a self-reference inside the target stops.
    child_refs = _active_refs + ((ref,) if isinstance(ref, str) else ())

    schema = Schema(
        ref=ref if isinstance(ref, str) else None,
        raw=dict(node),
        deprecated=_as_bool(node.get("deprecated"), False),
        line=_line(lines, *path),
    )
    schema.type = node.get("type")
    schema.format = node.get("format")
    schema.nullable = _as_bool(node.get("nullable"), False)
    enum = node.get("enum")
    schema.enum = list(enum) if isinstance(enum, list) else None

    # allOf: merge properties and required lists (the common OpenAPI idiom
    # for extending a base schema). Anything else in allOf is kept raw.
    if isinstance(node.get("allOf"), list):
        for i, part in enumerate(node["allOf"]):
            sub = _normalize_schema(part, resolver, depth + 1, path + ("allOf", i), lines, child_refs)
            schema.properties.update(sub.properties)
            for req in sub.required:
                if req not in schema.required:
                    schema.required.append(req)
            if schema.type is None:
                schema.type = sub.type
            if schema.enum is None:
                schema.enum = sub.enum
    for key in ("anyOf", "oneOf"):
        if key in node:
            schema.composite = {key: node[key]}
    if isinstance(node.get("not"), dict):
        schema.composite = dict(schema.composite or {})
        schema.composite["not"] = node["not"]

    props = node.get("properties")
    if isinstance(props, dict):
        for name, sub in props.items():
            schema.properties[name] = _normalize_schema(
                sub, resolver, depth + 1, path + ("properties", name), lines, child_refs
            )
    required = node.get("required")
    if isinstance(required, list):
        schema.required = [str(r) for r in required]
    if isinstance(node.get("items"), dict):
        schema.items = _normalize_schema(node["items"], resolver, depth + 1, path + ("items",), lines, child_refs)
    if "additionalProperties" in node:
        ap = node["additionalProperties"]
        if isinstance(ap, bool):
            schema.additional_properties = ap
        elif isinstance(ap, dict):
            schema.additional_properties = _normalize_schema(
                ap, resolver, depth + 1, path + ("additionalProperties",), lines, child_refs
            )
    return schema


def _normalize_parameter(node, resolver: _Resolver, path: tuple = (),
                         lines: dict | None = None) -> Parameter:
    node = resolver.resolve(node)
    if not isinstance(node, dict):
        raise SpecError(f"parameter must be an object, got {node!r}")
    schema = None
    if isinstance(node.get("schema"), dict):
        schema = _normalize_schema(node["schema"], resolver, 0, path + ("schema",), lines)
    return Parameter(
        name=str(node.get("name", "")),
        location=str(node.get("in", "")),
        required=_as_bool(node.get("required"), False),
        schema=schema,
        deprecated=_as_bool(node.get("deprecated"), False),
        line=_line(lines, *path),
    )


def _normalize_media(content, resolver: _Resolver, path: tuple = (),
                     lines: dict | None = None) -> dict[str, MediaType]:
    result: dict[str, MediaType] = {}
    if not isinstance(content, dict):
        return result
    for media_type, body in content.items():
        if not isinstance(body, dict):
            continue
        schema = None
        if isinstance(body.get("schema"), dict):
            schema = _normalize_schema(
                body["schema"], resolver, 0, path + (media_type, "schema"), lines
            )
        result[str(media_type)] = MediaType(
            schema=schema, line=_line(lines, *(path + (media_type,)))
        )
    return result


def _normalize_operation(method: str, path: str, node, resolver: _Resolver,
                         op_path: tuple = (), lines: dict | None = None) -> Operation:
    node = resolver.resolve(node)
    if not isinstance(node, dict):
        raise SpecError(f"operation {method} {path} must be an object")
    params: list[Parameter] = []
    for i, raw in enumerate(node.get("parameters", []) or []):
        if isinstance(raw, dict):
            params.append(
                _normalize_parameter(raw, resolver, op_path + ("parameters", i), lines)
            )
    request_body = None
    if isinstance(node.get("requestBody"), dict):
        body = resolver.resolve(node["requestBody"])
        if isinstance(body, dict):
            request_body = RequestBody(
                required=_as_bool(body.get("required"), False),
                content=_normalize_media(
                    body.get("content"), resolver,
                    op_path + ("requestBody", "content"), lines,
                ),
                line=_line(lines, *(op_path + ("requestBody",))),
            )
    responses: dict[str, Response] = {}
    raw_responses = node.get("responses", {}) or {}
    if isinstance(raw_responses, dict):
        for status, raw_resp in raw_responses.items():
            if not isinstance(raw_resp, dict):
                continue
            resp = resolver.resolve(raw_resp)
            if not isinstance(resp, dict):
                continue
            responses[str(status)] = Response(
                description=str(resp.get("description", "")),
                content=_normalize_media(
                    resp.get("content"), resolver,
                    op_path + ("responses", status, "content"), lines,
                ),
                line=_line(lines, *(op_path + ("responses", status))),
            )
    return Operation(
        method=method.upper(),
        path=path,
        operation_id=node.get("operationId"),
        summary=node.get("summary"),
        parameters=params,
        request_body=request_body,
        responses=responses,
        security=node.get("security"),
        deprecated=_as_bool(node.get("deprecated"), False),
        line=_line(lines, *op_path),
    )


def normalize_spec(doc, source_path: str | None = None,
                   lines: dict | None = None) -> Contract:
    """Normalize a parsed OpenAPI document into a Contract.

    ``lines`` is an optional key-path -> source-line map (from
    ``load_spec_with_lines``); it is used only to attach real line
    numbers to operations, parameters, and schemas for SARIF output.
    """
    if not isinstance(doc, dict):
        raise SpecError("spec must be a mapping")
    version = doc.get("openapi")
    if not isinstance(version, str) or not version.startswith("3."):
        raise SpecError(
            f"only OpenAPI 3.x is supported, got openapi={version!r} "
            "(Swagger 2.0 is not supported)"
        )
    resolver = _Resolver(doc)
    info = doc.get("info") or {}
    contract = Contract(
        title=info.get("title") if isinstance(info, dict) else None,
        version=str(info.get("version")) if isinstance(info, dict) and info.get("version") is not None else None,
        openapi_version=version,
        source_path=source_path,
    )
    components = doc.get("components") or {}
    if isinstance(components, dict):
        schemes = components.get("securitySchemes")
        if isinstance(schemes, dict):
            contract.security_schemes = schemes
    contract.global_security = doc.get("security")
    # Top-level servers: only the URL strings are kept (descriptions and
    # variables are not compared). A missing or malformed list means no
    # servers, same as an empty list.
    raw_servers = doc.get("servers")
    if isinstance(raw_servers, list):
        contract.servers = [
            str(entry["url"])
            for entry in raw_servers
            if isinstance(entry, dict) and isinstance(entry.get("url"), str)
        ]

    paths = doc.get("paths") or {}
    if not isinstance(paths, dict):
        raise SpecError("spec.paths must be a mapping")
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        # Path-level parameters apply to every operation on the path.
        path_params = []
        for i, raw in enumerate(path_item.get("parameters", []) or []):
            if isinstance(raw, dict):
                path_params.append(
                    _normalize_parameter(
                        raw, resolver, ("paths", path, "parameters", i), lines
                    )
                )
        for method in SUPPORTED_METHODS:
            if method not in path_item:
                continue
            op_path = ("paths", path, method)
            op = _normalize_operation(
                method, path, path_item[method], resolver, op_path, lines
            )
            # Merge path-level parameters not shadowed by the operation.
            seen = {(p.name, p.location) for p in op.parameters}
            for param in path_params:
                if (param.name, param.location) not in seen:
                    op.parameters.append(param)
            contract.operations[op.key] = op
    return contract


def parse_spec_text(text: str, source_path: str | None = None) -> Contract:
    doc, lines = load_spec_with_lines(text, source_path or "<input>")
    return normalize_spec(doc, source_path, lines)


def parse_spec_file(path: str) -> Contract:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise SpecError(f"cannot read {path}: {exc}") from exc
    doc, lines = load_spec_with_lines(text, path)
    return normalize_spec(doc, path, lines)
