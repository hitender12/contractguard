# ContractGuard

> **Catch breaking API changes before they reach production.**

ContractGuard compares an OpenAPI contract against a known baseline and tells
maintainers whether a change can break existing clients — with the exact
schema path, an explanation of which client behaviour may break, and a
configurable definition of backward compatibility.

```bash
contractguard check \
  --base api/openapi-main.yaml \
  --head api/openapi-branch.yaml
```

```text
BREAKING: GET /users/{id} removed
BREAKING: response field `email` changed from string to integer
WARNING: new required request field `region`
SAFE: optional response field `timezone` added
```

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

```bash
python demo.py                                   # built-in demo on the fixtures
python -m contractguard check --base fixtures/breaking/base.yaml \
                              --head fixtures/breaking/head.yaml
python -m contractguard rules                   # list all 27 rules
python -m unittest discover -s tests            # 24 tests
```

Compare against a git baseline instead of a file:

```bash
python -m contractguard check --base-ref main --base-path api/openapi.yaml \
                              --head api/openapi.yaml
```

## Reports

| Format | Flag | Use |
|--------|------|-----|
| Terminal | (default) | local runs, CI logs |
| JSON | `--format json` | automation |
| SARIF | `--format sarif` | GitHub code scanning |
| Markdown | `--format markdown` | PR summary comment |

## Policy

By default `BREAKING` fails CI (exit code 1); `WARNING` and `UNKNOWN` are
reported but pass; `SAFE` passes. Override with a config file or flags:

```yaml
# contractguard.yaml
profile: server
fail_on: [BREAKING]
warn_on: [WARNING, UNKNOWN]
```

```bash
python -m contractguard check --base b.yaml --head h.yaml --policy contractguard.yaml
python -m contractguard check --base b.yaml --head h.yaml --fail-on BREAKING UNKNOWN
```

See `examples/contractguard.yaml` and `docs/rules.md` for the full rule list.

## Rules

27 rules (R01–R27), each with a direction (request / response / both) and a
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

Every rule has positive and negative test cases in `fixtures/`:

- `fixtures/breaking/` — removed endpoint, type change, new required field,
  enum narrowing, parameter made required.
- `fixtures/non-breaking/` — optional response field, optional parameter,
  enum widening, new operation.
- `fixtures/ambiguous/` — format change and `anyOf` change, both UNKNOWN.

Each fixture ships an `expected.json`; the test suite asserts the exact
(rule, severity, location) set produced.

## Honest status (v0.1.0)

What works: OpenAPI 3.x parsing (JSON + a dependency-free YAML-subset
parser), local `$ref` resolution, `allOf` merging, semantic diff, 27
compatibility rules with server/client profiles, policy config, terminal /
JSON / SARIF / Markdown reports, git-ref baselines, golden fixtures.

What is **not** built yet (see `ARCHITECTURE.md` for the production path):
- **No Rust engine.** The blueprint specifies a Rust diff engine with a
  full OpenAPI parser (serde + OpenAPI crates). This is a Python reference
  implementation; the rule model is designed so the Rust port reuses the
  same classifications.
- **No GitHub Action** (M4 in the roadmap) — the SARIF + Markdown outputs
  are the integration points for it.
- **No GraphQL / Protobuf / AsyncAPI** adapters (M6) — OpenAPI only.
- **YAML subset parser limits:** anchors/aliases/tags, multi-document
  streams, and complex keys are rejected with a clear error. Real-world
  specs using them need a full YAML library.
- `anyOf` / `oneOf` / `not` changes are reported UNKNOWN by design.
- Contract tests / mock generation from schema changes are not implemented.

## Repository structure

```text
contractguard/        # the package
  yamlmini.py         # dependency-free YAML-subset parser
  parser.py           # OpenAPI -> normalized contract model
  model.py            # normalized contract model
  diff.py             # semantic diff engine
  rules.py            # 27 compatibility rules + profiles
  policy.py           # CI policy config
  report.py           # terminal / JSON / SARIF / Markdown
  baseline.py         # file or git-ref baselines
  cli.py              # argparse CLI
  demo.py             # built-in demo
fixtures/             # breaking / non-breaking / ambiguous golden pairs
docs/rules.md         # full rule documentation
examples/             # generated reports + sample policy
tests/                # 24 tests
```
