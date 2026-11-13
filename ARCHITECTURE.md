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
| `yamlmini.py` | Dependency-free YAML-subset parser. Block maps/sequences, flow collections, quoted scalars, block scalars (including inside sequence items), comments, and a source-line map (`key_lines`). Rejects anchors/aliases/tags/multi-doc with a clear error. Duplicate mapping keys are rejected with a line number instead of silently keeping the last value. |
| `parser.py` | JSON/YAML loading, OpenAPI 3.x validation, local `$ref` resolution (with cycle detection), `allOf` merging, path-level parameter inheritance. Recursive `$ref` chains are terminated at the recursive reference (unexpanded `Schema.recursive_ref` marker) instead of recursing forever; the depth guard (>25 levels) remains as a backstop for inline nesting. Threads the line map through so every model node records its source line (YAML specs only). Top-level `servers` URLs are kept on the contract. |
| `model.py` | Normalized contract model. Composite schemas (`anyOf`/`oneOf`/`not`) are recorded, not flattened. Unknown keywords are kept in `raw` so the diff can flag them UNKNOWN instead of dropping them. |
| `diff.py` | Semantic diff. Emits typed `Change` objects (what changed, where) — never a severity. Picks comparable media types (prefers `application/json`) and reports media-type set changes, `securitySchemes` changes, `additionalProperties` changes, `deprecated` flag changes, `operationId` changes, top-level `servers` URL changes, and recursive `$ref` target changes. Enum comparison is set-based: a pure reorder emits no finding. |
| `rules.py` | 34 rules (R01–R34). Each maps a `Change` + profile to a `Finding` with severity, message, explanation, and rule link. Unknown change kinds become UNKNOWN findings, never silent. |
| `policy.py` | CI policy: `fail_on` / `warn_on` severities, profile selection, YAML/JSON config file. Default: fail on BREAKING only; `warn_on` is honoured — a warned severity is marked `[WARN]`, counted in the policy summary, and does not fail the check; a severity in both lists fails (`fail_on` wins). CLI `--fail-on` / `--warn-on` values are validated through the same constructor as policy files: an unknown severity is rejected with a clean exit 2 instead of silently disabling the gate. |
| `report.py` | Terminal, JSON, SARIF 2.1.0, Markdown PR summary renderers. SARIF locations use the real source line for YAML specs and omit `region` entirely when the line is unknown (JSON specs) instead of fabricating `startLine: 1`. |
| `baseline.py` | Baseline from a file or from `git show <ref>:<path>`, optionally scoped to a repository directory with `repo=` (the CLI's `--repo` flag). |
| `cli.py` | `check`, `rules`, `demo` subcommands. |
| `action/action.yml` | Composite GitHub Action: installs the package, runs the check (JSON + Markdown), posts the Markdown report as a PR comment, and fails the job on a failing severity. |

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
  exact (rule, severity, location) set for each fixture pair, and
  `fixtures/rules/rNN-<slug>/` pins a positive and a negative pair for
  every rule. Adding a rule means adding a fixture pair first.
- **Line numbers travel with the change.** The YAML parser records the
  source line of every mapping key and sequence item; the parser threads
  those lines onto the model nodes, the diff copies them onto changes,
  and SARIF reports them. When a line is not known (JSON specs), the
  region is omitted rather than invented.
- **Constraint keywords are parsed, not compared.** `minLength`,
  `maximum` and friends are recognised as known JSON Schema keywords, so
  they are not flagged by R28 — but their values are not yet compared, so
  a tighter `minLength` currently produces no finding. That is a known
  gap, not a silent pass: see the limitations in the README.
- **Recursive schemas are terminated, not expanded.** A `$ref` to a
  schema already being expanded above it becomes an unexpanded marker
  (`Schema.recursive_ref`). The diff compares markers by reference
  identity only (R34 UNKNOWN when the target changes) and never diffs
  a marker field-by-field against an expanded schema, which would
  report phantom additions/removals. Content changes to the referenced
  schema are still caught where it is first expanded. Genuinely
  circular `$ref`-only chains and inline nesting over 25 levels are
  rejected with a clear error.
- **`servers` and `operationId` are compared; nothing else at the top
  level is.** The diff compares top-level `servers` URLs (R33) and each
  operation's `operationId` (R32). Other top-level metadata (`info`
  except title/version, `tags`, `externalDocs`) is not compared and is
  not claimed to be.
- **Stateless and CI-friendly.** No database, no server, no network calls.
  The only external dependency is the `git` CLI, used only for git-ref
  baselines.

## Production path (not built here)

Per the blueprint: Rust diff engine (`contract-model`, `openapi-parser`,
`diff-engine`, `compatibility-rules`, `report`, `cli` crates), full OpenAPI
parser via serde, and a GitHub Action that installs the binary, comments
on PRs, and sets a required status check. The composite action in
`action/` already does the CI half of that in Python (install from the
repo, run the check, comment, fail the job); the Rust port would swap
the install step for a prebuilt binary. Then GraphQL / Protobuf
adapters, a public fixture corpus, and optional contract-test
generation. This Python package is the reference implementation those crates
should match rule-for-rule.
