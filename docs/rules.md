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
| R01 | operation removed | both | BREAKING | BREAKING |
| R02 | operation added | both | SAFE | SAFE |
| R03 | response status removed | response | BREAKING | BREAKING |
| R04 | response status added | response | SAFE | SAFE |
| R05 | new required request parameter | request | BREAKING | WARNING |
| R06 | new optional request parameter | request | SAFE | SAFE |
| R07 | required request parameter removed | request | SAFE | BREAKING |
| R08 | optional request parameter removed | request | SAFE | SAFE |
| R09 | parameter optional → required | request | BREAKING | SAFE |
| R10 | parameter required → optional | request | SAFE | BREAKING |
| R11 | parameter moved (query/header/path) | request | BREAKING | BREAKING |
| R12 | new required request body | request | BREAKING | WARNING |
| R13 | new optional request body | request | SAFE | SAFE |
| R14 | request body removed | request | SAFE | BREAKING |
| R15 | request body optional → required | request | BREAKING | SAFE |
| R16 | request body required → optional | request | SAFE | BREAKING |
| R17 | schema field added | both | depends | depends |
| R18 | schema field removed | both | depends | depends |
| R19 | schema field required → optional | both | depends | depends |
| R20 | schema field optional → required | both | depends | depends |
| R21 | schema type changed (e.g. string → integer) | both | BREAKING | BREAKING |
| R22 | schema format changed | both | UNKNOWN | UNKNOWN |
| R23 | schema nullability changed | both | depends | depends |
| R24 | enum narrowed / widened | both | depends | depends |
| R25 | anyOf / oneOf / not schema changed | both | UNKNOWN | UNKNOWN |
| R26 | schema removed | both | BREAKING | BREAKING |
| R27 | security requirement changed | both | WARNING | WARNING |

## The rules that need the most care

### R17 / R18 — adding and removing fields

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

### R19 / R20 — required ↔ optional

- **Request field optional → required:** BREAKING (server) / SAFE (client).
- **Request field required → optional:** SAFE (server) / BREAKING (client).
- **Response field required → optional:** WARNING under both profiles — the
  server may now omit a field clients read unconditionally.
- **Response field optional → required:** SAFE (server) / WARNING (client).

### R21 / R22 / R23 — type, format, nullability

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

### R24 — enums

- **Narrowed** (values removed): BREAKING for the server profile and for
  responses under either profile. The one exception is a narrowed *request*
  enum under the client profile (SAFE): the new client only sends values
  the old server still accepts.
- **Widened** (values added): SAFE. Existing values remain valid.

### R25 — composite schemas

`anyOf` / `oneOf` / `not` changes are UNKNOWN. The allowed value set may
have narrowed, but field-by-field comparison cannot tell which branch a
consumer relies on. A human must review.

### R27 — security

Adding a security requirement is WARNING: clients without the new
credentials will be rejected. Removing one is SAFE.
