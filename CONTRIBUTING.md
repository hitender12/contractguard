# Contributing to ContractGuard

Thanks for helping make API compatibility checks better. ContractGuard is a
small, dependency-free Python tool, so the barrier to a first contribution
is deliberately low: if you can run Python, you can contribute.

## Local setup

Requirements: **Python 3.10+**. There are no third-party dependencies —
no virtualenv tooling, no `pip install` step, no build system.

```bash
git clone https://github.com/hitender12/contractguard.git
cd contractguard
python3 --version        # must be 3.10 or newer
python3 demo.py           # built-in demo on the fixtures; should exit 0
```

That's the whole setup. The package lives in `contractguard/` and is run
as a module:

```bash
python3 -m contractguard check --base fixtures/breaking/base.yaml \
                              --head fixtures/breaking/head.yaml
python3 -m contractguard rules        # list all 34 rules (R01–R34)
python3 -m contractguard demo         # demo fixtures, server profile
```

## Running the tests

```bash
python3 -m unittest discover -s tests        # full suite (131 tests)
python3 -m unittest tests.test_contractguard -v   # verbose, single module
```

The suite is pure stdlib `unittest` — no pytest, no plugins. Keep it that
way: a new dependency needs a strong justification and maintainer approval.

Before opening a PR, run the full suite and the demo, and confirm both
pass. If you changed rule behaviour, the golden-fixture tests (below) are
the ones most likely to catch a regression — run them, don't just eyeball
the output.

## How the code is organised

See `ARCHITECTURE.md` for the pipeline. The short version:

| File | Responsibility |
|------|---------------|
| `contractguard/yamlmini.py` | Dependency-free YAML-subset parser |
| `contractguard/parser.py` | OpenAPI 3.x loading, local `$ref` resolution, `allOf` merging |
| `contractguard/model.py` | Normalised contract model (`Contract`, `Operation`, `Schema`, …) |
| `contractguard/diff.py` | Semantic diff — emits typed `Change` objects, never a severity |
| `contractguard/rules.py` | The 34 compatibility rules (R01–R34) + server/client profiles |
| `contractguard/policy.py` | CI policy: `fail_on` / `warn_on`, config file |
| `contractguard/report.py` | Terminal / JSON / SARIF / Markdown renderers |
| `contractguard/baseline.py` | Baseline from a file or a `git show <ref>:<path>` |
| `contractguard/cli.py` | `check`, `rules`, `demo` subcommands |

The key invariant: **rules never see raw YAML/JSON** — they see
`Change` objects produced by `diff.py` against the normalised model in
`model.py`. Keep that separation when you add features.

## How to add a new compatibility rule

This is the most common contribution, and it has a fixed shape. See
`docs/adding-a-rule.md` for the full step-by-step; the checklist is:

1. **Read `docs/rules.md` first.** Check the change isn't already covered
   by an existing rule, and decide the severity under *both* profiles
   (`server` and `client`) and the direction (`request` / `response` /
   `both`). If the tool cannot confidently decide compatibility from the
   schema alone, the rule must return `UNKNOWN` — never guess.
2. **Add a golden fixture pair first.** Create a new directory under
   `fixtures/rules/` named `rNN-<slug>` (next free number after R31)
   with `base.yaml`, `head.yaml`, `head_neg.yaml`, and `expected.json`
   pinning the exact `(rule, severity, location)` set the pair must
   produce under both profiles. The fixture comes before the
   implementation: it is the specification of the rule. See "How to add
   a golden fixture pair" below and `tests/test_rule_fixtures.py`, which
   picks up every `fixtures/rules/rNN-*/` directory automatically.
3. **Implement the rule in `contractguard/rules.py`.** Add a `_rNN`
   function (next free number after R31), register it in the `RULES`
   table with its name, direction, and server/client severities, and wire
   it into `classify()`. If the diff engine doesn't emit the change kind
   your rule needs, extend `contractguard/diff.py` first — rules consume
   `Change` objects, they don't re-parse specs.
4. **Document it in `docs/rules.md`.** Add the rule to the table
   (rule, change, direction, server, client severities) and, if the
   reasoning is subtle, a paragraph under "The rules that need the most
   care". The table and the code must agree; the test suite checks the
   code, reviewers check the table.
5. **Add unit tests in `tests/test_contractguard.py`.** At minimum, a
   test that builds two tiny specs as text and asserts the classification
   under both profiles. Prefer this over fixture-only coverage: it makes
   the rule testable in isolation.
6. **Run the full suite and `python3 -m contractguard rules`** and confirm
   the new rule appears with the right severities.

A rule PR that changes an existing rule's severity is a breaking change
for users' CI — say so explicitly in the PR description and in the
`CHANGELOG.md` entry (see below).

## How to add a golden fixture pair

There are two fixture formats. **New rules use the per-rule format:**
`fixtures/rules/rNN-<slug>/`, with four files — `base.yaml`,
`head.yaml`, `head_neg.yaml` (a change that must *not* trigger the
rule), and `expected.json` with `positive` / `negative` sets under both
`server` and `client` profiles. `tests/test_rule_fixtures.py` picks up
every such directory automatically.

The older **demo fixtures** live in `fixtures/<category>/`, where
`<category>` is one of `breaking`, `non-breaking`, or `ambiguous` (use
`ambiguous` when the correct classification is `UNKNOWN`). Each demo
fixture directory contains exactly three files:

- `base.yaml` — the baseline OpenAPI spec (the "before").
- `head.yaml` — the changed OpenAPI spec (the "after").
- `expected.json` — the pinned result, e.g.:

```json
{
  "profile": "server",
  "findings": [
    {"rule": "R01", "severity": "BREAKING", "location": "GET /users/{id}"}
  ]
}
```

Rules for fixtures:

- **Minimal.** Each pair should exercise one rule (or one coherent
  change). Don't bundle five unrelated changes into one fixture — a
  failing test should point at exactly one thing.
- **Realistic.** Write specs that look like a real API (paths,
  operations, `application/json` bodies), not abstract fragments.
- **Exact.** `expected.json` pins the *complete* set of
  `(rule, severity, location)` findings. If your change produces extra
  findings you didn't expect, that's a signal — investigate before
  editing `expected.json` to match.
- **Both profiles where it matters.** If the severity differs between
  the `server` and `client` profiles, add a unit test asserting the
  client-profile result too; a single `expected.json` only pins one
  profile.

To verify a new fixture by hand before wiring it into the tests:

```bash
python3 -m contractguard check --base fixtures/<name>/base.yaml \
                              --head fixtures/<name>/head.yaml --format json
```

## Other contributions

- **Parser / YAML-subset work** (`yamlmini.py`, `parser.py`): the parser
  deliberately rejects anchors/aliases/tags, multi-document streams, and
  complex keys with a clear error. Extending that support is welcome, but
  it must come with fixtures proving the new syntax parses *and* that
  previously rejected input still errors clearly.
- **Report formats** (`report.py`): new output formats must be
  machine-checkable — add an example under `examples/` and a test
  asserting its structure (e.g. valid SARIF 2.1.0).
- **Docs:** fixes to `docs/`, the README examples, or `ARCHITECTURE.md`
  are welcome. Keep examples runnable — every command in the README and
  docs should work from a clean checkout.
- **Bug reports:** open an issue with a minimal `base.yaml`/`head.yaml`
  pair that reproduces the problem, the command you ran, and the output
  you got versus what you expected. That pair usually becomes a fixture.

## PR expectations

- **Small and focused.** One rule, one bug, or one docs change per PR.
  Large PRs that mix a rule change with a refactor will be asked to split.
- **Tests included.** Code changes without a test (unit test and/or
  fixture) will not be merged, except for docs-only PRs.
- **No new dependencies.** The project is stdlib-only by design. If you
  think a dependency is unavoidable, open an issue first and make the case.
- **No invented behaviour.** ContractGuard reports `UNKNOWN` when it
  cannot decide compatibility. Don't "fix" an UNKNOWN by guessing — fix
  it by documenting why it's undecidable, or by adding the information
  the rule would need.
- **Changelog entry.** User-visible changes go in `CHANGELOG.md` under
  `## Unreleased`. Follow the existing format (Added / Changed / Fixed).
- **Style:** plain, readable Python 3.10+; type hints where they help;
  no formatter is enforced, but keep lines and functions short and match
  the surrounding code.
- **CI must pass.** The suite must be green on Python 3.10+ before merge.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
By participating, you agree to abide by its terms. Be kind, be specific,
and assume good faith — especially when disagreeing about whether a
change is "breaking". That disagreement is the whole point of the tool;
resolve it with evidence (client behaviour, spec text), not volume.

## Questions?

Open a GitHub Discussion or an issue. For a rule-classification question,
include a minimal spec pair — it's the fastest way to get a useful answer.
