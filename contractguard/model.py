"""Normalized internal contract model.

The compatibility rules work only against these structures, never against
raw YAML/JSON. That is what makes the rule engine testable and what lets a
future Rust engine (or a GraphQL/Protobuf adapter) reuse the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Schema:
    """A normalized JSON Schema fragment (OpenAPI Schema Object)."""

    type: str | None = None
    format: str | None = None
    nullable: bool = False
    enum: list | None = None
    properties: dict[str, "Schema"] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    items: "Schema | None" = None
    additional_properties: "Schema | bool | None" = None
    # Composite schemas (anyOf / oneOf / allOf) are recorded, not flattened:
    # their compatibility cannot be decided by simple field comparison.
    composite: dict | None = None
    # Anything the normalizer does not understand is kept verbatim so a
    # diff can report it as UNKNOWN instead of silently dropping it.
    raw: dict = field(default_factory=dict)
    ref: str | None = None

    def is_empty(self) -> bool:
        return (
            self.type is None
            and not self.properties
            and self.enum is None
            and self.composite is None
            and self.items is None
        )


@dataclass
class Parameter:
    name: str
    location: str  # query | header | path | cookie
    required: bool = False
    schema: Schema | None = None
    deprecated: bool = False


@dataclass
class MediaType:
    schema: Schema | None = None


@dataclass
class RequestBody:
    required: bool = False
    content: dict[str, MediaType] = field(default_factory=dict)


@dataclass
class Response:
    description: str = ""
    content: dict[str, MediaType] = field(default_factory=dict)


@dataclass
class Operation:
    method: str
    path: str
    operation_id: str | None = None
    summary: str | None = None
    parameters: list[Parameter] = field(default_factory=list)
    request_body: RequestBody | None = None
    responses: dict[str, Response] = field(default_factory=dict)
    security: list | None = None
    deprecated: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.method.upper(), self.path)


@dataclass
class Contract:
    """A whole normalized API contract."""

    title: str | None = None
    version: str | None = None
    openapi_version: str | None = None
    operations: dict[tuple[str, str], Operation] = field(default_factory=dict)
    security_schemes: dict = field(default_factory=dict)
    global_security: list | None = None
    source_path: str | None = None

    def operation_keys(self) -> list[tuple[str, str]]:
        return sorted(self.operations.keys())
