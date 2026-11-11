# ContractGuard — Architecture

## Pipeline

```text
OpenAPI YAML / JSON
        |
Parser + validator (parser.py, yamlmini.py)
        |
Normalized contract model (model.py)
        |
Semantic diff engine (diff.py)  <---- Base contract
        |
Compatibility rules + team profile (rules.py, policy.py)
        |
        +----------+-----------+-----------+
        |          |           |           |
     Terminal    JSON       SARIF      Markdown
                             (report.py)
```

## Why the model layer matters

The rules never see raw YAML or JSON. They see `Contract` objects built
from `Operation`, `Parameter`, `RequestBody`, `Response`, and `Schema`
dataclasses. That separation is deliberate:

1. **Rules are testable in isolation.** A test builds two tiny specs as
   text and asserts a classification — no fixture files needed.
2. **A Rust port reuses the classifications.** The production engine
   (blueprint: Rust + serde + OpenAPI parser crates) can implement the same
   normalized model and the same rule table; the Python implementation is
   the executable specification.
3. **New formats are adapters, not rewrites.** A GraphQL or Protobuf
   adapter only has to produce a `Contract`; the diff and rules are
   unchanged.

## Components

| Module | Responsibility |
|--------|---------------|
| `yamlmini.py` | Dependency-free YAML-subset parser. Block maps/sequences, flow collections, quoted scalars, block scalars, comments. Rejects anchors/aliases/tags/multi-doc with a clear error. |
| `parser.py` | JSON/YAML loading, OpenAPI 3.x validation, local `$ref` resolution (with cycle detection), `allOf` merging, path-level parameter inheritance. |
| `model.py` | Normalized contract model. Composite schemas (`anyOf`/`oneOf`/`not`) are recorded, not flattened. Unknown keywords are kept in `raw` so the diff can flag them UNKNOWN instead of dropping them. |
| `diff.py` | Semantic diff. Emits typed `Change` objects (what changed, where) — never a severity. Picks comparable media types (prefers `application/json`). |
| `rules.py` | 27 rules (R01–R27). Each maps a `Change` + profile to a `Finding` with severity, message, explanation, and rule link. Unknown change kinds become UNKNOWN findings, never silent. |
| `policy.py` | CI policy: `fail_on` / `warn_on` severities, profile selection, YAML/JSON config file. Default: fail on BREAKING only. |
| `report.py` | Terminal, JSON, SARIF 2.1.0, Markdown PR summary renderers. |
| `baseline.py` | Baseline from a file or from `git show <ref>:<path>`. |
| `cli.py` | `check`, `rules`, `demo` subcommands. |

## Key design decisions

- **Direction travels with the change.** Every schema change carries
  `direction: request | response`, because the same field change means
  different things on each side (e.g. a new required *request* field is
  BREAKING for the server profile; a new required *response* field is SAFE).
- **UNKNOWN is a first-class outcome.** Format changes and composite-schema
  changes cannot be decided from the schema alone. Reporting UNKNOWN (and
  letting policy decide whether it fails CI) is more honest than guessing.
- **Profiles, not one vague "breaking".** Server vs client compatibility
  differ on at least six rules (R05, R07, R09, R10, R14, R15, R17, R18,
  R19, R20, R23, R24-request). The rule table in `docs/rules.md` lists
  both severities for every rule.
- **Golden fixtures as the contract.** `fixtures/*/expected.json` pins the
  exact (rule, severity, location) set for each fixture pair. Adding a rule
  means adding a fixture pair first.
- **Stateless and CI-friendly.** No database, no server, no network calls.
  The only external dependency is the `git` CLI, used only for git-ref
  baselines.

## Production path (not built here)

Per the blueprint: Rust diff engine (`contract-model`, `openapi-parser`,
`diff-engine`, `compatibility-rules`, `report`, `cli` crates), full OpenAPI
parser via serde, GitHub Action (composite or TypeScript) that installs the
binary, comments on PRs, and sets a required status check. Then GraphQL /
Protobuf adapters, a public fixture corpus, and optional contract-test
generation. This Python package is the reference implementation those crates
should match rule-for-rule.
