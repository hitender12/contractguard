# Safe change

A head spec that existing clients can keep using, checked against its
baseline. Adapted from the golden fixture in `fixtures/non-breaking/`
(same four changes).

## What changes

| Change | Rule | Why it is safe |
|---|---|---|
| New optional query parameter `region` | R06 | Callers may simply omit it |
| New operation `GET /users/{id}/posts` added | R02 | Does not affect existing clients |
| Response field `role` enum widened (`admin`, `user` → `admin`, `user`, `guest`) | R24 | Existing values remain valid |
| Optional response field `timezone` added | R17 | Added response data is ignored by old clients |

## Run it

From the repo root:

```bash
bash examples/safe-change/run.sh
```

Or the underlying command directly:

```bash
python3 -m contractguard check --base examples/safe-change/base.yaml --head examples/safe-change/head.yaml
```

(`python` works too where it is installed; this machine only has `python3`.)

## Expected output

```text
ContractGuard: examples/safe-change/base.yaml -> examples/safe-change/head.yaml

SAFE: new optional request parameter region (query)
    Existing callers are unaffected; the parameter may simply be omitted. [R06]
SAFE: GET /users/{id}/posts added
    A new operation does not affect existing clients. [R02]
SAFE: response field `role` enum widened: added 'guest'
    Existing values remain valid; new values are simply available. [R24]
SAFE: optional response field `timezone` added
    Added response data does not affect existing clients. [R17]

Summary: 4 safe (4 findings)
```

Exit code is **0**: nothing breaking, so the check passes and CI stays green.
