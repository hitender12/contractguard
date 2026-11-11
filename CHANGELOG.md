# Changelog

All notable changes to ContractGuard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it reaches 1.0. During 0.x, minor versions may include breaking changes
to rule severities or output formats; those will be called out explicitly.

## [Unreleased]

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
