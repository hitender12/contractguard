# ContractGuard

> **Catch breaking API changes before they reach production.**

ContractGuard compares an OpenAPI contract against a known baseline and tells
maintainers whether a change can break existing clients — with the exact
schema path, an explanation of which client behaviour may break, and a
configurable definition of backward compatibility.

Install it first (one command, no dependencies — see
[Quickstart](#quickstart)):

```bash
pip install .
```

Then:

```bash
contractguard check \
  --base fixtures/breaking/base.yaml \
  --head fixtures/breaking/head.yaml
```

```text
ContractGuard: fixtures/breaking/base.yaml -> fixtures/breaking/head.yaml

[FAIL] BREAKING: request parameter limit (query) is now required
    Server profile: existing callers that omit the parameter will be rejected. Client profile: the new client always sends it. [R09]
[FAIL] BREAKING: GET /users/{id} removed
    Existing clients calling this endpoint will get 404 / not-found errors. Removing an operation is the most direct breaking change. [R01]
[FAIL] BREAKING: request field `email` changed from string to integer
    Consumers parse this value as the old type; a different type breaks deserialization, validation, and downstream logic. [R21]
[FAIL] BREAKING: new required request field `region`
    Server profile: existing callers do not send this field and will be rejected. Client profile: older servers may reject an unknown required field under strict validation. [R17]
[FAIL] BREAKING: response field `role` enum narrowed: removed 'user'
    Values that existing clients or servers rely on are no longer valid. [R24]

Summary: 5 breaking (5 findings)
Policy: 5 fail, 0 warn, 0 pass (fail_on=['BREAKING'], warn_on=['WARNING', 'UNKNOWN'])
```

The output above is the verbatim output of that command (exit code 1:
breaking changes fail CI). The `[FAIL]` / `[WARN]` / `[ok]` markers and
the `Policy:` line come from the active policy; see
[Policy](#policy) below.

## Why not just diff the YAML?

A text diff cannot tell you that removing an *optional* response field is
breaking while adding a *required* request field is breaking for a different
reason — or that a format change (`date-time` → `date`) cannot be judged
from the schema at all. ContractGuard normalizes both specs into a contract
model, diffs them semantically, and classifies every change under a
compatibility profile:

- **server** (default) — will existing clients keep working against the new
  server?
- **client** — will the new client keep working against existing servers?

When it cannot confidently determine compatibility, it reports **UNKNOWN**
instead of pretending certainty.

## Quickstart

No dependencies. Python 3.10+ only.

Install the `contractguard` command (from the repository root):

```bash
pip install .
```

Or run it without installing:

```bash
python3 demo.py                                   # built-in demo on the fixtures
python3 -m contractguard check --base fixtures/breaking/base.yaml \
                               --head fixtures/breaking/head.yaml
python3 -m contractguard rules                   # list all 31 rules
python3 -m unittest discover -s tests            # full test suite
```

Compare against a git baseline instead of a file:

```bash
python3 -m contractguard check --base-ref main --base-path api/openapi.yaml \
                               --head api/openapi.yaml
# --repo scopes the git lookup to another directory:
python3 -m contractguard check --base-ref main --base-path api/openapi.yaml \
                               --head api/openapi.yaml --repo /path/to/repo
```

## Reports

| Format | Flag | Use |
|--------|------|-----|
| Terminal | (default) | local runs, CI logs |
| JSON | `--format json` | automation |
| SARIF | `--format sarif` | GitHub code scanning |
| Markdown | `--format markdown` | PR summary comment |

## Policy

By default `BREAKING` fails CI (exit code 1). `WARNING` and `UNKNOWN`
are reported as warnings -- marked `[WARN]` in terminal output, counted
in the JSON `policy.outcomes` block and the `Policy:` summary line --
but they do not fail the check; `SAFE` passes. A severity listed in
both `fail_on` and `warn_on` fails (`fail_on` wins). Override with a
config file or flags:

```yaml
# contractguard.yaml
profile: server
fail_on: [BREAKING]
warn_on: [WARNING, UNKNOWN]
```

```bash
python3 -m contractguard check --base b.yaml --head h.yaml --policy contractguard.yaml
python3 -m contractguard check --base b.yaml --head h.yaml --fail-on BREAKING UNKNOWN
```

See `examples/contractguard.yaml` and `docs/rules.md` for the full rule list.

## GitHub Action

A composite action lives in `action/` (see `action/README.md` for the
full input list). It installs ContractGuard, runs the check, posts the
Markdown report as a PR comment, and fails the job when a failing
severity is found:

```yaml
jobs:
  contract:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: hitender12/contractguard/action@v0.2.0
        with:
          base-ref: ${{ github.event.pull_request.base.sha }}
          base-path: api/openapi.yaml
          head-path: api/openapi.yaml
```

## Rules

31 rules (R01–R31), each with a direction (request / response / both) and a
severity under each profile. Highlights:

| Change | Server | Client |
|--------|--------|--------|
| Operation removed | BREAKING | BREAKING |
| Response field `string` → `integer` | BREAKING | BREAKING |
| New required request field | BREAKING | WARNING |
| Optional response field added | SAFE | SAFE |
| Enum narrowed | BREAKING | depends* |
| Format changed (`date-time` → `date`) | UNKNOWN | UNKNOWN |
| `anyOf` / `oneOf` changed | UNKNOWN | UNKNOWN |

\* A narrowed *request* enum is SAFE under the client profile: the new
client only sends values the old server still accepts.

## Golden fixtures

Every rule has positive and negative test cases in `fixtures/rules/`
(one directory per rule, `rNN-<slug>`, with `base.yaml`, `head.yaml`,
`head_neg.yaml`, and `expected.json` pinning the exact (rule,
severity, location) sets under both profiles; run by
`tests/test_rule_fixtures.py`). The older top-level fixtures are kept
for the demo:

- `fixtures/breaking/` — removed endpoint, type change, new required field,
  enum narrowing, parameter made required.
- `fixtures/non-breaking/` — optional response field, optional parameter,
  enum widening, new operation.
- `fixtures/ambiguous/` — format change and `anyOf` change, both UNKNOWN.

Each fixture ships an `expected.json`; the test suite asserts the exact
(rule, severity, location) set produced.

## Honest status (v0.2.0)

What works: OpenAPI 3.x parsing (JSON + a dependency-free YAML-subset
parser), local `$ref` resolution, `allOf` merging, semantic diff, 31
compatibility rules with server/client profiles, policy config
(`fail_on` / `warn_on` both honoured), terminal / JSON / SARIF /
Markdown reports, SARIF findings carry real source lines for YAML
specs (omitted, never fabricated, when the line is unknown), git-ref
baselines (with `--repo`), golden fixtures for every rule, and a
composite GitHub Action under `action/` that comments on PRs and fails
the job on BREAKING.

What is **not** built yet (see `ARCHITECTURE.md` for the production path):
- **No Rust engine.** The blueprint specifies a Rust diff engine with a
  full OpenAPI parser (serde + OpenAPI crates). This is a Python reference
  implementation; the rule model is designed so the Rust port reuses the
  same classifications.
- **No GraphQL / Protobuf / AsyncAPI** adapters (M6) — OpenAPI only.
- **YAML subset parser limits:** anchors/aliases/tags, multi-document
  streams, and complex keys are rejected with a clear error. Real-world
  specs using them need a full YAML library.
- `anyOf` / `oneOf` / `not` changes are reported UNKNOWN by design.
- Constraint keywords such as `minLength` / `maximum` are parsed but not
  yet compared; unknown keywords are reported UNKNOWN (R28).
- Contract tests / mock generation from schema changes are not implemented.

## Repository structure

```text
contractguard/        # the package
  yamlmini.py         # dependency-free YAML-subset parser
  parser.py           # OpenAPI -> normalized contract model
  model.py            # normalized contract model
  diff.py             # semantic diff engine
  rules.py            # 31 compatibility rules + profiles
  policy.py           # CI policy config
  report.py           # terminal / JSON / SARIF / Markdown
  baseline.py         # file or git-ref baselines
  cli.py              # argparse CLI
  demo.py             # built-in demo
action/               # composite GitHub Action (action.yml)
fixtures/             # breaking / non-breaking / ambiguous golden pairs
fixtures/rules/       # per-rule positive + negative golden fixtures
docs/rules.md         # full rule documentation
examples/             # generated reports + sample policy
tests/                # test suite
```
