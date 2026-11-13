# ContractGuard compatibility rules

Two profiles. Read them as questions:

- **server** — will existing clients keep working against the new server?
  This is the default, and what a backend pull-request check usually means.
- **client** — will the new client keep working against existing servers?
  Use this when the contract describes what a client will send and expect.

"depends" means the severity is decided by direction (request vs response)
and by whether the field was required. The rule code in
`contractguard/rules.py` is the authoritative implementation; this document
explains the reasoning.

| Rule | Change | Direction | Server | Client |
|------|--------|-----------|--------|--------|
| <a id="r01"></a>R01 | operation removed | both | BREAKING | BREAKING |
| <a id="r02"></a>R02 | operation added | both | SAFE | SAFE |
| <a id="r03"></a>R03 | response status removed | response | BREAKING | BREAKING |
| <a id="r04"></a>R04 | response status added | response | SAFE | SAFE |
| <a id="r05"></a>R05 | new required request parameter | request | BREAKING | WARNING |
| <a id="r06"></a>R06 | new optional request parameter | request | SAFE | SAFE |
| <a id="r07"></a>R07 | required request parameter removed | request | SAFE | BREAKING |
| <a id="r08"></a>R08 | optional request parameter removed | request | SAFE | SAFE |
| <a id="r09"></a>R09 | parameter optional → required | request | BREAKING | SAFE |
| <a id="r10"></a>R10 | parameter required → optional | request | SAFE | BREAKING |
| <a id="r11"></a>R11 | parameter moved (query/header/path) | request | BREAKING | BREAKING |
| <a id="r12"></a>R12 | new required request body | request | BREAKING | WARNING |
| <a id="r13"></a>R13 | new optional request body | request | SAFE | SAFE |
| <a id="r14"></a>R14 | request body removed | request | SAFE | BREAKING |
| <a id="r15"></a>R15 | request body optional → required | request | BREAKING | SAFE |
| <a id="r16"></a>R16 | request body required → optional | request | SAFE | BREAKING |
| <a id="r17"></a>R17 | schema field added | both | depends | depends |
| <a id="r18"></a>R18 | schema field removed | both | depends | depends |
| <a id="r19"></a>R19 | schema field required → optional | both | depends | depends |
| <a id="r20"></a>R20 | schema field optional → required | both | depends | depends |
| <a id="r21"></a>R21 | schema type changed (e.g. string → integer) | both | BREAKING | BREAKING |
| <a id="r22"></a>R22 | schema format changed | both | UNKNOWN | UNKNOWN |
| <a id="r23"></a>R23 | schema nullability changed | both | depends | depends |
| <a id="r24"></a>R24 | enum narrowed / widened | both | depends | depends |
| <a id="r25"></a>R25 | anyOf / oneOf / not schema changed | both | UNKNOWN | UNKNOWN |
| <a id="r26"></a>R26 | schema removed | both | BREAKING | BREAKING |
| <a id="r27"></a>R27 | security requirement / scheme changed | both | WARNING | SAFE* |
| <a id="r28"></a>R28 | unknown schema keyword changed | both | UNKNOWN | UNKNOWN |
| <a id="r29"></a>R29 | media type changed | both | depends | depends |
| <a id="r30"></a>R30 | additionalProperties changed | both | depends | depends |
| <a id="r31"></a>R31 | operation / parameter / schema deprecated | both | depends | depends |
| <a id="r32"></a>R32 | operationId changed | both | depends | depends |
| <a id="r33"></a>R33 | server URL changed | both | depends | depends |
| <a id="r34"></a>R34 | recursive schema $ref target changed | both | UNKNOWN | UNKNOWN |

\* R27 is WARNING when a security requirement is added or a security
scheme definition changes, and SAFE when a security requirement is
removed.

## The rules that need the most care

### <a id="r17"></a><a id="r18"></a>R17 / R18 — adding and removing fields

- **Response field added, optional:** SAFE under both profiles. Old clients
  ignore unknown fields.
- **Response field added, required:** SAFE for the server profile (the
  server now guarantees the field), WARNING for the client profile (a new
  client reading it will fail against older servers that do not send it).
- **Response field removed:** BREAKING under both profiles. Consumers
  reading the field get missing data.
- **Request field added, required:** BREAKING for the server profile
  (existing callers do not send it), WARNING for the client profile (older
  servers may reject an unknown field under strict validation).
- **Request field removed, was required:** SAFE for the server profile (the
  server no longer needs the value), BREAKING for the client profile (a new
  client will not send a value existing servers require). The server-side
  SAFE comes with a caveat: behaviour driven by that field is gone, so the
  finding still explains the risk.
- **Request field removed, was optional:** SAFE under both profiles.

### <a id="r19"></a><a id="r20"></a>R19 / R20 — required ↔ optional

- **Request field optional → required:** BREAKING (server) / SAFE (client).
- **Request field required → optional:** SAFE (server) / BREAKING (client).
- **Response field required → optional:** WARNING under both profiles — the
  server may now omit a field clients read unconditionally.
- **Response field optional → required:** SAFE (server) / WARNING (client).

### <a id="r21"></a><a id="r22"></a><a id="r23"></a>R21 / R22 / R23 — type, format, nullability

- **Type changed** (string → integer): BREAKING. Consumers parse the value
  as the old type.
- **Format changed** (date-time → date, int32 → int64): UNKNOWN. Whether it
  breaks depends on how strictly clients validate, and the schema alone
  cannot tell. ContractGuard reports UNKNOWN rather than guessing.
- **Response field became nullable:** WARNING — strict clients that do not
  expect null can break; lenient clients are fine.
- **Response field became non-nullable:** SAFE.
- **Request field became nullable:** SAFE.
- **Request field became non-nullable:** BREAKING (server) / SAFE (client).

### <a id="r24"></a>R24 — enums

- **Narrowed** (values removed): BREAKING for the server profile and for
  responses under either profile. The one exception is a narrowed *request*
  enum under the client profile (SAFE): the new client only sends values
  the old server still accepts.
- **Widened** (values added): SAFE. Existing values remain valid.
- **Reordered** (same value set, different order): no finding. Enums are
  unordered sets of allowed values.

### <a id="r25"></a>R25 — composite schemas

`anyOf` / `oneOf` / `not` changes are UNKNOWN. The allowed value set may
have narrowed, but field-by-field comparison cannot tell which branch a
consumer relies on. A human must review.

### <a id="r27"></a>R27 — security

Adding a security requirement is WARNING: clients without the new
credentials will be rejected. Removing one is SAFE. A change to a
security *scheme* definition (for example an OAuth flow or scope) is
WARNING: clients authenticating with the old definition may be rejected
or may lose access to scopes they relied on.

### <a id="r28"></a>R28 — unknown schema keywords

A schema keyword ContractGuard does not understand (anything outside the
standard JSON Schema / OpenAPI keyword set, such as a vendor extension
`x-*`) changed value. The impact cannot be decided from the schema
alone, so the finding is UNKNOWN and a human must review. Known
keywords that ContractGuard does not compare yet (for example
`minLength`) are a documented limitation, not unknown keywords.

### <a id="r29"></a>R29 — media types

A request or response body changed media type (for example
`application/json` → `text/plain`) while the schema stayed the same.
Schema comparison alone cannot see this, but clients parse the body as
the old media type, so it breaks them.

- **Response media type changed:** BREAKING under both profiles.
- **Request media type changed:** BREAKING (server) / WARNING (client).

### <a id="r30"></a>R30 — additionalProperties

`additionalProperties` became more permissive (for example `false` →
`true`, or `false` → a schema) or more restrictive (`true` → `false`).
When both sides are schemas they are diffed recursively instead.

- **More permissive, request:** SAFE (server) / WARNING (client).
- **More permissive, response:** SAFE under both profiles.
- **More restrictive, request:** BREAKING (server) / SAFE (client).
- **More restrictive, response:** WARNING under both profiles.

### <a id="r31"></a>R31 — deprecated

An operation, parameter, or schema was marked `deprecated: true`, or
un-deprecated.

- **Newly deprecated:** WARNING under both profiles. Deprecation does
  not break clients yet, but the item is scheduled for removal; clients
  should migrate.
- **Un-deprecated:** SAFE under both profiles.

### <a id="r32"></a>R32 — operationId

An operation's `operationId` changed. The wire contract (method + path)
is unchanged, so this is invisible to raw HTTP clients — but generated
clients call the operation by its `operationId`, so a rename or removal
breaks them.

- **Renamed or removed:** WARNING under both profiles.
- **Added where there was none:** SAFE under both profiles.

### <a id="r33"></a>R33 — servers

A top-level `servers` URL changed. Only the URL strings are compared,
in order; descriptions and server variables are not compared.

- **URL removed:** WARNING under both profiles. Clients configured with
  the removed URL can no longer reach the API.
- **Default server changed** (the first entry reordered): WARNING under
  both profiles. Clients that use the default URL will now talk to a
  different server.
- **URL added:** SAFE under both profiles. Existing URLs are unchanged.

### <a id="r34"></a>R34 — recursive schema reference

A recursive schema's `$ref` target changed (or a recursive reference
was replaced by an inline schema, or vice versa). Recursive schemas —
for example a tree type whose `child` property references itself — are
parsed without expanding the recursion (see the parser limits in the
README), so the referenced schema is not compared at that position and
the impact cannot be decided from the reference alone: UNKNOWN under
both profiles, and a human must compare the two referenced schemas.
A change to the referenced schema's *content* is still caught where
the schema is first expanded.
