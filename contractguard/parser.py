"""OpenAPI parser and normalizer.

Loads JSON directly and YAML through the bundled subset parser, resolves
local ``$ref`` pointers (``#/components/...`` and ``#/paths/...``), and
produces a :class:`~contractguard.model.Contract`.

Limits, stated plainly:
- Only OpenAPI 3.x documents (``openapi: 3.*``). Swagger 2.0 is rejected
  with a clear error instead of being half-parsed.
- Only local ``$ref`` targets. Remote / file / URL references are rejected.
- Circular ``$ref`` chains are rejected instead of recursing forever.
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
from .yamlmini import YAMLParseError, parse_yaml

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


def load_spec_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise SpecError(f"cannot read {path}: {exc}") from exc
    return load_spec_text(text, path)


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


def _normalize_schema(node, resolver: _Resolver, depth: int = 0) -> Schema:
    if depth > 25:
        raise RefError("schema nesting too deep (possible circular $ref)")
    if node is None:
        return Schema()
    if not isinstance(node, dict):
        raise SpecError(f"schema must be an object, got {node!r}")
    ref = node.get("$ref")
    node = resolver.resolve(node)
    if not isinstance(node, dict):
        raise SpecError(f"$ref target must be an object, got {node!r}")

    schema = Schema(ref=ref if isinstance(ref, str) else None, raw=dict(node))
    schema.type = node.get("type")
    schema.format = node.get("format")
    schema.nullable = _as_bool(node.get("nullable"), False)
    enum = node.get("enum")
    schema.enum = list(enum) if isinstance(enum, list) else None

    # allOf: merge properties and required lists (the common OpenAPI idiom
    # for extending a base schema). Anything else in allOf is kept raw.
    if isinstance(node.get("allOf"), list):
        for part in node["allOf"]:
            sub = _normalize_schema(part, resolver, depth + 1)
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
            schema.properties[name] = _normalize_schema(sub, resolver, depth + 1)
    required = node.get("required")
    if isinstance(required, list):
        schema.required = [str(r) for r in required]
    if isinstance(node.get("items"), dict):
        schema.items = _normalize_schema(node["items"], resolver, depth + 1)
    if "additionalProperties" in node:
        ap = node["additionalProperties"]
        if isinstance(ap, bool):
            schema.additional_properties = ap
        elif isinstance(ap, dict):
            schema.additional_properties = _normalize_schema(ap, resolver, depth + 1)
    return schema


def _normalize_parameter(node, resolver: _Resolver) -> Parameter:
    node = resolver.resolve(node)
    if not isinstance(node, dict):
        raise SpecError(f"parameter must be an object, got {node!r}")
    schema = None
    if isinstance(node.get("schema"), dict):
        schema = _normalize_schema(node["schema"], resolver)
    return Parameter(
        name=str(node.get("name", "")),
        location=str(node.get("in", "")),
        required=_as_bool(node.get("required"), False),
        schema=schema,
        deprecated=_as_bool(node.get("deprecated"), False),
    )


def _normalize_media(content, resolver: _Resolver) -> dict[str, MediaType]:
    result: dict[str, MediaType] = {}
    if not isinstance(content, dict):
        return result
    for media_type, body in content.items():
        if not isinstance(body, dict):
            continue
        schema = None
        if isinstance(body.get("schema"), dict):
            schema = _normalize_schema(body["schema"], resolver)
        result[str(media_type)] = MediaType(schema=schema)
    return result


def _normalize_operation(method: str, path: str, node, resolver: _Resolver) -> Operation:
    node = resolver.resolve(node)
    if not isinstance(node, dict):
        raise SpecError(f"operation {method} {path} must be an object")
    params: list[Parameter] = []
    for raw in node.get("parameters", []) or []:
        if isinstance(raw, dict):
            params.append(_normalize_parameter(raw, resolver))
    request_body = None
    if isinstance(node.get("requestBody"), dict):
        body = resolver.resolve(node["requestBody"])
        if isinstance(body, dict):
            request_body = RequestBody(
                required=_as_bool(body.get("required"), False),
                content=_normalize_media(body.get("content"), resolver),
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
                content=_normalize_media(resp.get("content"), resolver),
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
    )


def normalize_spec(doc, source_path: str | None = None) -> Contract:
    """Normalize a parsed OpenAPI document into a Contract."""
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

    paths = doc.get("paths") or {}
    if not isinstance(paths, dict):
        raise SpecError("spec.paths must be a mapping")
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        # Path-level parameters apply to every operation on the path.
        path_params = []
        for raw in path_item.get("parameters", []) or []:
            if isinstance(raw, dict):
                path_params.append(_normalize_parameter(raw, resolver))
        for method in SUPPORTED_METHODS:
            if method not in path_item:
                continue
            op = _normalize_operation(method, path, path_item[method], resolver)
            # Merge path-level parameters not shadowed by the operation.
            seen = {(p.name, p.location) for p in op.parameters}
            for param in path_params:
                if (param.name, param.location) not in seen:
                    op.parameters.append(param)
            contract.operations[op.key] = op
    return contract


def parse_spec_text(text: str, source_path: str | None = None) -> Contract:
    return normalize_spec(load_spec_text(text, source_path or "<input>"), source_path)


def parse_spec_file(path: str) -> Contract:
    return normalize_spec(load_spec_file(path), path)
