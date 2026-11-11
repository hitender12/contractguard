## ContractGuard report

Base: `examples/pr-summary/base.yaml` → Head: `examples/pr-summary/head.yaml`

| Severity | Count |
|---|---|
| BREAKING | 5 |

| Severity | Rule | Change |
|---|---|---|
| BREAKING | R09 | request parameter limit (query) is now required |
| BREAKING | R01 | GET /users/{id} removed |
| BREAKING | R21 | request field `email` changed from string to integer |
| BREAKING | R17 | new required request field `region` |
| BREAKING | R24 | response field `role` enum narrowed: removed 'user' |

### Details

#### BREAKING: request parameter limit (query) is now required

- **Location:** `GET /users > parameter limit (query)`
- **Rule:** R09 (docs/rules.md#r09)
- **Why it matters:** Server profile: existing callers that omit the parameter will be rejected. Client profile: the new client always sends it.

#### BREAKING: GET /users/{id} removed

- **Location:** `GET /users/{id}`
- **Rule:** R01 (docs/rules.md#r01)
- **Why it matters:** Existing clients calling this endpoint will get 404 / not-found errors. Removing an operation is the most direct breaking change.

#### BREAKING: request field `email` changed from string to integer

- **Location:** `POST /users > request body.email`
- **Rule:** R21 (docs/rules.md#r21)
- **Why it matters:** Consumers parse this value as the old type; a different type breaks deserialization, validation, and downstream logic.

#### BREAKING: new required request field `region`

- **Location:** `POST /users > request body.region`
- **Rule:** R17 (docs/rules.md#r17)
- **Why it matters:** Server profile: existing callers do not send this field and will be rejected. Client profile: older servers may reject an unknown required field under strict validation.

#### BREAKING: response field `role` enum narrowed: removed 'user'

- **Location:** `POST /users > response 201.role`
- **Rule:** R24 (docs/rules.md#r24)
- **Why it matters:** Values that existing clients or servers rely on are no longer valid.

