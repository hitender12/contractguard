# Security Policy

## Supported Versions

Only the latest released version of ContractGuard receives security
updates. There is no long-term-support branch yet.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

If you are running an older version, upgrade to the latest release
before reporting — the issue may already be fixed. Security fixes are
released as patch versions and noted in `CHANGELOG.md`.

## Reporting a Vulnerability

**Do not open a public issue for a suspected vulnerability.** Public
issues are visible to everyone, including anyone who could exploit the
problem before a fix ships.

Instead, report it privately through one of these channels:

1. **GitHub private security advisory (preferred).** On the repository,
   go to **Security → Advisories → New draft security advisory** and
   describe the issue. This keeps the report private to the maintainers
   until a fix is ready.
2. **Contact the maintainers privately through GitHub** (e.g. a direct
   message to a maintainer, or a private fork discussion) if the advisory
   flow is unavailable to you.

There is currently no dedicated security email address for this project.
Do not send vulnerability reports to any email address found in commit
history or elsewhere — use the private advisory flow above.

### What to include

- A description of the vulnerability and its impact.
- Steps to reproduce, ideally a minimal OpenAPI spec pair
  (`base.yaml` / `head.yaml`) or a single spec that triggers it.
- The version you tested against (`python -m contractguard --version`).
- Any suggested fix, if you have one. (A fix PR is welcome, but please
  coordinate privately first so the disclosure stays private until the
  fix is released.)

### What happens next

- We will acknowledge receipt as promptly as we can.
- We will investigate, and keep you updated on whether the report is
  confirmed and when a fix is planned.
- Once a fix is released, we will publish a security advisory describing
  the issue and credit you as the reporter, unless you ask not to be
  named.
- Please allow a reasonable time for a fix before disclosing publicly.

## Scope

ContractGuard is a local, stateless CLI. It makes no network calls, runs
no server, and stores no data — the only external program it invokes is
the `git` CLI, and only when you ask for a git-ref baseline
(`--base-ref` / `--head-ref`). That limits the attack surface, but the
following are in scope for security reports:

- **Parser vulnerabilities.** ContractGuard parses untrusted OpenAPI
  YAML/JSON, including specs from pull requests. A spec that crashes the
  tool, hangs it (e.g. pathological nesting or a `$ref` cycle the cycle
  detection misses), or exhausts memory is a real issue — the tool should
  fail with a clear error, not hang or crash.
- **Output injection.** Report output (terminal, JSON, SARIF, Markdown)
  is often pasted into PR comments and CI logs. Content from a spec that
  breaks out of its output format — e.g. Markdown that injects links or
  HTML into a PR summary, or terminal escape sequences that spoof
  findings — is in scope.
- **Git baseline handling.** `--base-ref` / `--base-path` pass values to
  the `git` CLI. Argument injection or path traversal through those
  flags is in scope.
- **Dependency issues.** The project is intentionally stdlib-only, so
  there are no third-party dependencies to audit. If that changes, new
  dependencies fall under this policy.

### Out of scope

- Whether a particular API change *should* be classified BREAKING or
  SAFE — that is a compatibility-rule design question, not a security
  vulnerability. Open a normal issue for it (see `docs/rules.md`).
- Specs that are rejected by the YAML-subset parser (anchors, aliases,
  tags, multi-document streams) — that rejection is intentional and
  documented in the README.
- Social-engineering or phishing claims about the project itself.
- Reports that the tool does not support GraphQL, Protobuf, AsyncAPI,
  or a GitHub Action yet — those are roadmap items, listed in the README
  under "Honest status".

## Known limitations

Be aware of these when assessing risk; they are design decisions, not
vulnerabilities:

- The YAML parser is a hand-written subset parser (`yamlmini.py`). It
  rejects constructs it doesn't understand rather than silently
  mis-parsing them, but it has not been fuzz-tested against adversarial
  YAML the way a mature library has. Treat hostile specs accordingly.
- `anyOf` / `oneOf` / `not` changes are reported `UNKNOWN` by design —
  the tool does not attempt to prove equivalence of composite schemas.
- SARIF and Markdown output are generated from spec content; consumers
  should treat them as untrusted text from the spec author, as with any
  CI artifact derived from PR contents.
