# Examples

Runnable examples for ContractGuard. Each lives in its own directory with
its own `base.yaml` / `head.yaml` spec pair, a `run.sh`, and a `README.md`
explaining what it shows. All commands run from the repo root, with no
dependencies beyond Python 3.10+ (`python3` on this machine; `python`
works where it is installed).

| Example | What it shows | Command |
|---|---|---|
| [breaking-change](breaking-change/) | A head spec that breaks existing clients: 5 `BREAKING` findings, exit code 1 | `bash examples/breaking-change/run.sh` |
| [safe-change](safe-change/) | A head spec existing clients can keep using: 4 `SAFE` findings, exit code 0 | `bash examples/safe-change/run.sh` |
| [pr-summary](pr-summary/) | The Markdown report for a PR comment, generated from a breaking pair: `pr-summary.md` with 5 `BREAKING` findings, exit code 1 | `bash examples/pr-summary/run.sh` |

The spec pairs are adapted from the golden fixtures in `fixtures/`:
`breaking-change/` and `pr-summary/` use `fixtures/breaking/`,
`safe-change/` uses `fixtures/non-breaking/`.

The pre-existing generated outputs at the top of this directory
(`report.json`, `report.sarif`, `pr-summary.md`, `contractguard.yaml`)
come from the core build's demo and are left untouched.
