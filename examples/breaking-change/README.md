# Breaking change

A head spec that breaks existing clients, checked against its baseline.
Adapted from the golden fixture in `fixtures/breaking/` (same five changes).

## What changes

| Change | Rule | Why it breaks clients |
|---|---|---|
| `GET /users/{id}` removed | R01 | Existing callers get 404s |
| Query parameter `limit` made required | R09 | Callers that omit it are rejected |
| Request field `email`: `string` → `integer` | R21 | Breaks deserialization / validation |
| New required request field `region` | R17 | Existing callers do not send it |
| Response field `role` enum narrowed (`admin`, `user` → `admin`) | R24 | Clients relying on `'user'` break |

## Run it

From the repo root:

```bash
bash examples/breaking-change/run.sh
```

Or the underlying command directly:

```bash
python3 -m contractguard check --base examples/breaking-change/base.yaml --head examples/breaking-change/head.yaml
```

(`python` works too where it is installed; this machine only has `python3`.)

## Expected output

```text
ContractGuard: examples/breaking-change/base.yaml -> examples/breaking-change/head.yaml

BREAKING: request parameter limit (query) is now required
    Server profile: existing callers that omit the parameter will be rejected. Client profile: the new client always sends it. [R09]
BREAKING: GET /users/{id} removed
    Existing clients calling this endpoint will get 404 / not-found errors. Removing an operation is the most direct breaking change. [R01]
BREAKING: request field `email` changed from string to integer
    Consumers parse this value as the old type; a different type breaks deserialization, validation, and downstream logic. [R21]
BREAKING: new required request field `region`
    Server profile: existing callers do not send this field and will be rejected. Client profile: older servers may reject an unknown required field under strict validation. [R17]
BREAKING: response field `role` enum narrowed: removed 'user'
    Values that existing clients or servers rely on are no longer valid. [R24]

Summary: 5 breaking (5 findings)
```

Exit code is **1**: by default `BREAKING` fails CI, which is exactly the
point — this change must not ship as-is.
