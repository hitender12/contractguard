# Architecture overview

ContractGuard is a small, stateless, dependency-free Python CLI. It takes
two OpenAPI specs — a **baseline** and a **head** — and reports whether
the changes between them can break existing clients. The whole pipeline
is five stages:

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

For the full component reference, see `ARCHITECTURE.md` at the repo root.
This page is the short version: what each stage does, and why the stages
are separate.

## 1. Parse — `parser.py`, `yamlmini.py`

Both specs are loaded from YAML or JSON. YAML goes through `yamlmini.py`,
a hand-written parser for a subset of YAML (block maps/sequences, flow
collections, quoted scalars, block scalars, comments). It deliberately
**rejects** anchors/aliases/tags, multi-document streams, and complex
keys with a clear error instead of silently mis-parsing them.

`parser.py` then validates the document as OpenAPI 3.x and builds the
normalised model: it resolves local `$ref`s (with cycle detection),
merges `allOf`, and applies path-level parameters to each operation.
Anything it cannot understand is kept in the model's `raw` field rather
than dropped, so a later stage can flag it `UNKNOWN` instead of ignoring
it.

## 2. Normalize — `model.py`

The output of parsing is a `Contract` made of `Operation`, `Parameter`,
`RequestBody`, `Response`, and `Schema` dataclasses. This is the key
separation in the design: **nothing downstream ever sees raw YAML or
JSON.** The model is the single vocabulary the diff and the rules share,
which is what makes the rules testable in isolation and what a future
port (the production path is a Rust engine — see `ARCHITECTURE.md`) can
reuse rule-for-rule. A GraphQL or Protobuf adapter would only have to
produce a `Contract`; the diff and rules would be unchanged.

Composite schemas (`anyOf` / `oneOf` / `not`) are recorded, not
flattened — the tool does not attempt to prove two composite schemas
equivalent.

## 3. Diff — `diff.py`

The diff engine compares the base contract against the head contract and
emits typed `Change` objects: *what* changed and *where* (e.g.
`GET /users/{id}` removed, `POST /users > response 201.email` type
changed `string` → `integer`). Every schema change carries a
`direction` — `request` or `response` — because the same field change
means different things on each side.

Crucially, the diff **never assigns a severity**. It only describes the
change. Severity is a policy decision, made in the next stage.

## 4. Rules — `rules.py`, `policy.py`

`rules.py` holds the 34 compatibility rules (R01–R34), documented in
`docs/rules.md`. Each rule maps a `Change` plus a compatibility profile
to a `Finding` with a severity, a message, an explanation of which
client behaviour may break, and a link to its rule documentation.

The two profiles ask different questions:

- **server** (default) — will existing clients keep working against the
  new server? This is what a backend PR check usually means.
- **client** — will the new client keep working against existing servers?

The same change can be BREAKING under one profile and SAFE under the
other (for example, a narrowed *request* enum is BREAKING for the server
profile but SAFE for the client profile, because the new client only
sends values the old server still accepts).

When compatibility cannot be decided from the schema alone — format
changes (R22), `anyOf` / `oneOf` / `not` changes (R25) — the rule
returns **UNKNOWN**, a first-class outcome, rather than guessing.

`policy.py` then applies the team's CI policy: which severities fail the
build (`fail_on`, default `BREAKING` only, exit code 1) and which are
reported as warnings (`warn_on`, default `WARNING` and `UNKNOWN`). Policy
comes from a `contractguard.yaml` config file or from `--fail-on` /
`--warn-on` flags.

## 5. Report — `report.py`

Findings are rendered in one of four formats:

| Format | Flag | Use |
|--------|------|-----|
| Terminal | (default) | local runs, CI logs |
| JSON | `--format json` | automation |
| SARIF 2.1.0 | `--format sarif` | GitHub code scanning |
| Markdown | `--format markdown` | PR summary comment |

## Baselines — `baseline.py`

The baseline comes from a file (`--base`) or from a git ref
(`--base-ref main --base-path api/openapi.yaml`, resolved with
`git show`). The `git` CLI is the tool's only external dependency, and
only for git-ref baselines. There is no database, no server, and no
network call anywhere in the pipeline.

## CLI — `cli.py`

Three subcommands: `check` (compare head against baseline),
`rules` (list all 34 rules), and `demo` (built-in demo on the fixtures).
Run `python3 -m contractguard --help` for the full flag list.
