# ContractGuard GitHub Action

Composite action: installs ContractGuard, runs the check against a
baseline, posts the Markdown report as a PR comment, and fails the job
when a failing severity is found (BREAKING by default).

## Usage

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

Or compare two files on disk:

```yaml
      - uses: hitender12/contractguard/action@v0.2.0
        with:
          base: api/openapi-main.yaml
          head: api/openapi-branch.yaml
```

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `base` | `""` | Baseline spec file (used when `base-ref` is empty). |
| `head` | `api/openapi.yaml` | Head spec file. |
| `base-ref` | `""` | Git ref for the baseline (needs `base-path`). |
| `base-path` | `""` | Path of the baseline spec inside the git ref. |
| `head-ref` | `""` | Git ref for the head (needs `head-path`). |
| `head-path` | `""` | Path of the head spec inside the git ref. |
| `profile` | `server` | Compatibility profile (`server` or `client`). |
| `fail-on` | `BREAKING` | Space-separated severities that fail the check. |
| `warn-on` | `WARNING UNKNOWN` | Space-separated severities reported as warnings. |
| `comment` | `true` | Post the Markdown report as a PR comment. |

## Outputs

| Output | Description |
|--------|-------------|
| `exit-code` | Exit code of the check (1 = a failing severity was found). |
| `breaking` | Number of BREAKING findings. |

## Notes

- Composite actions can only run `run:` steps, so the action uses the
  Python 3 and `gh` CLI already present on GitHub-hosted runners; it
  does not need `actions/setup-python`.
- The PR comment step edits the action's previous comment on the same
  PR when one exists, so repeated pushes do not spam the thread.
- The check step always succeeds internally (its exit code is captured
  as an output); the separate `gate` step fails the job afterwards so
  the comment is still posted even when the check fails.
