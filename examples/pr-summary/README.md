# PR summary

Generate the Markdown report ContractGuard would post as a pull-request
comment, from a breaking spec pair. Uses the same pair as
`examples/breaking-change/` (adapted from `fixtures/breaking/`), so the
summary lists the same five `BREAKING` findings.

## Run it

From the repo root:

```bash
bash examples/pr-summary/run.sh
```

Or the underlying command directly:

```bash
python3 -m contractguard check --base examples/pr-summary/base.yaml --head examples/pr-summary/head.yaml --format markdown --output examples/pr-summary/pr-summary.md
```

(`python` works too where it is installed; this machine only has `python3`.)

This writes (regenerates) `pr-summary.md` in this directory. A copy of the
generated file is committed here so the output can be read without running
anything.

## What the summary contains

- A severity count table (`BREAKING | 5`).
- A table of every finding: severity, rule, and change.
- A per-finding section with the exact location, the rule link
  (`docs/rules.md#r01`, …), and why the change matters to clients.

Example excerpt:

```markdown
## ContractGuard report

Base: `examples/pr-summary/base.yaml` → Head: `examples/pr-summary/head.yaml`

| Severity | Count |
|---|---|
| BREAKING | 5 |

| Severity | Rule | Change |
|---|---|---|
| BREAKING | R01 | GET /users/{id} removed |
| BREAKING | R21 | request field `email` changed from string to integer |
| BREAKING | R17 | new required request field `region` |
| BREAKING | R24 | response field `role` enum narrowed: removed 'user' |
```

## Exit code

The command exits **1**, not 0: the report is still written to
`pr-summary.md`, but `BREAKING` findings fail CI by default. That is the
behaviour a GitHub Action relies on — post the summary, then fail the
required status check. `run.sh` treats exit code 1 as the expected result
and only fails if the file is missing or the exit code is anything else.
