# Changelog

All notable changes to ContractGuard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it reaches 1.0. During 0.x, minor versions may include breaking changes
to rule severities or output formats; those will be called out explicitly.

## [Unreleased]

## [0.2.0] — 2026-11-11

Audit fix release. An independent QA audit found 14 broken or unverified
claims plus integration gaps; every one is fixed below, each with a
regression test or golden fixture in `tests/test_audit_fixes.py` and
`fixtures/rules/`.

### Fixed

- **B1 — R11 parameter-moved was unreachable.** The diff keyed
  parameters by (name, location), so moving `token` from query to header
  reported SAFE. Parameters are now matched by name first; a location
  move emits `parameter-location-changed` and R11 reports BREAKING under
  both profiles.
- **B2 — R17 contradicted the docs under the client profile.** An added
  optional response field now reports SAFE under both profiles; an added
  required response field is SAFE (server) / WARNING (client).
- **B3 — R23 contradicted the docs.** Nullability is now
  direction-aware: becoming nullable is SAFE for requests and WARNING
  for responses; becoming non-nullable is BREAKING (server) / SAFE
  (client) for requests and SAFE for responses.
- **B4 — R27 tables were wrong.** The rule table and `docs/rules.md`
  said WARNING/WARNING; the code returned WARNING on add and SAFE on
  removal. The tables now say WARNING/SAFE, and R27 also compares
  requirement sets: adding a requirement or swapping schemes is WARNING,
  removal is SAFE, reorder-only is SAFE.
- **B5 — README example output.** The intro example is now the verbatim
  output of the breaking fixture run (pinned by a test).
- **B6 — per-rule golden fixtures.** Every rule R01–R31 now has a
  positive and a negative fixture pair under `fixtures/rules/rNN-<slug>/`,
  asserted by `tests/test_rule_fixtures.py`.
- **B7 — multi-document YAML was silently merged.** The parser now
  rejects a second document (`---`) or content after `...` with a clear
  `UnsupportedYAML` error. A leading `---` and an indented `---` inside
  a block scalar are still accepted.
- **B8 — dead `rule_url` links.** Every rule row in `docs/rules.md`
  now carries a real `<a id="rNN"></a>` anchor, and sections for R28–R31
  were added.
- **B9 — install step and `python` vs `python3`.** The README now shows
  `pip install .` before the first `contractguard` command, and all
  commands in the README, CONTRIBUTING.md and docs use `python3`.
- **B10 — `warn_on` was accepted, validated, then ignored.** The policy
  now classifies every finding as fail/warn/pass (`fail_on` wins on
  overlap); terminal output marks lines `[FAIL]`/`[WARN]`/`[ok]` and
  prints a `Policy:` summary line; JSON and Markdown reports carry a
  `policy` block.
- **B11 — SARIF locations were fabricated (`startLine: 1`).** The YAML
  parser now records the source line of every key; findings carry the
  real line and SARIF reports it. For JSON specs (no line info) the
  `region` is omitted instead of invented.
- **B12 — unknown keywords were silently dropped.** `Schema.raw` is now
  read by the diff: a changed unknown keyword emits
  `schema-unknown-changed` and R28 reports UNKNOWN under both profiles.
- **B13 — wrong rule citations.** The `rules.py` docstring now cites
  R22/R25 for UNKNOWN (was R21/R24).
- **B14 — media-type changes were invisible.** The diff now compares
  request/response media-type sets; a change emits
  `media-type-changed` and R29 reports BREAKING (response: both
  profiles; request: BREAKING server / WARNING client).

### Added

- **R28** — unknown schema keyword changed (UNKNOWN both profiles).
- **R29** — media type changed (see B14).
- **R30** — `additionalProperties` changed (ranked by permissiveness:
  absent ≡ `true` > schema > `false`; direction-aware severities).
- **R31** — `deprecated` flag changed on an operation, parameter, or
  schema (newly deprecated: WARNING both; un-deprecated: SAFE both).
- **GitHub Action** (`action/`): a composite action that installs the
  package, runs the check (JSON + Markdown), posts the Markdown report
  as a PR comment, and fails the job on a failing severity.
- **`--repo` flag** for git baselines (`baseline.py` already accepted
  `repo=`; the CLI now wires it through).
- **Line-number tracking** through the parser → model → diff → report
  pipeline (see B11).
- **YAML block scalars in sequence items** — `yamlmini.py` now parses
  `run: |` under a `- id:` item instead of treating `|` as a literal
  string (found while validating `action/action.yml`).

### Changed

- `demo.py` writes its machine-readable outputs to a temp directory by
  default and only writes into `examples/` with `--write-examples`.
  (The `contractguard demo` subcommand is unaffected — it only prints.)
- `securitySchemes` are now compared: a changed scheme (flow, scope,
  or definition) emits a finding under R27 (WARNING).
- The `examples/` outputs were regenerated to match the new report
  formats (JSON now carries a `policy` block; SARIF carries real lines).

### Known limitations

- Constraint keywords (`minLength`, `maximum`, …) are parsed and
  recognised as known, so they are not flagged by R28 — but their values
  are not yet compared, so a tighter `minLength` currently produces no
  finding.
- Unknown keywords inside `allOf` parts are not compared (the merged
  schema's `raw` is the top node only).
- R24 enum reorder-only is flagged R24 SAFE (pinned quirk, harmless but
  noisy).

## [0.1.0] — 2026-11-11

The initial release: a dependency-free Python reference implementation of
the ContractGuard compatibility checker.

### Added

- OpenAPI 3.x parsing for YAML and JSON, using a dependency-free
  YAML-subset parser (`contractguard/yamlmini.py`). Local `$ref`
  resolution with cycle detection, `allOf` merging, and path-level
  parameter inheritance.
- Semantic diff engine (`contractguard/diff.py`) that compares operations,
  parameters, request bodies, responses, schemas, enums, formats, and
  nullability, and emits typed `Change` objects.
- 27 compatibility rules (R01–R27) in `contractguard/rules.py`,
  classifying every change as `BREAKING`, `WARNING`, `SAFE`, or
  `UNKNOWN` under two profiles:
  - `server` (default) — will existing clients keep working against the
    new server?
  - `client` — will the new client keep working against existing servers?
  - When compatibility cannot be decided from the schema alone (format
    changes, `anyOf` / `oneOf` / `not`), the tool reports `UNKNOWN`
    instead of guessing.
- CLI (`python -m contractguard`) with three subcommands: `check`
  (compare a head spec against a baseline), `rules` (list all 27 rules),
  and `demo` (built-in demo on the fixtures).
- Four report formats: terminal (default), JSON (`--format json`),
  SARIF 2.1.0 (`--format sarif`) for GitHub code scanning, and Markdown
  (`--format markdown`) for PR summary comments.
- CI policy config (`contractguard.yaml`): `profile`, `fail_on`, and
  `warn_on` severities. Default: `BREAKING` fails CI (exit code 1);
  `WARNING` and `UNKNOWN` are reported but pass. Overridable with
  `--fail-on` / `--warn-on` flags.
- Baselines from a file (`--base`) or from a git ref
  (`--base-ref main --base-path api/openapi.yaml`, via `git show`).
- Golden fixtures in `fixtures/` — `breaking/`, `non-breaking/`, and
  `ambiguous/` pairs, each with an `expected.json` pinning the exact
  `(rule, severity, location)` set produced.
- Full rule documentation in `docs/rules.md`.
- Example policy config and generated reports in `examples/`.
- 24-test stdlib `unittest` suite (`python -m unittest discover -s tests`).

### Known limitations (not yet built)

- No Rust engine yet — this is a Python reference implementation; the
  production Rust port is on the roadmap in `ARCHITECTURE.md`.
- No GitHub Action yet — SARIF and Markdown output are the integration
  points for it.
- OpenAPI only — no GraphQL, Protobuf, or AsyncAPI adapters.
- The YAML-subset parser rejects anchors/aliases/tags, multi-document
  streams, and complex keys with a clear error; specs using them need a
  full YAML library.
- `anyOf` / `oneOf` / `not` changes are reported `UNKNOWN` by design.
- No contract-test or mock generation from schema changes.
