# Adding a new compatibility rule

This is the standard path for the most common ContractGuard contribution.
It has six steps, in order. Don't skip the fixture step — the fixture is
the specification of the rule, and it comes before the implementation.

## Step 0 — Check the rule doesn't already exist

Read `docs/rules.md` (the full rule table, R01–R27) and run
`python -m contractguard rules`. Check whether your change is already
covered, possibly under a different name. Also check open issues and PRs
for a rule with the same idea.

Then decide the three things every rule needs:

1. **Direction** — `request`, `response`, or `both`. Ask: does this
   change affect what clients send, what they receive, or either?
2. **Severity under each profile** — `server` and `client` separately.
   The same change can be BREAKING under one and SAFE under the other
   (see R07, R09, R10 for examples). Work through a concrete client
   scenario for each profile; don't copy the severity from a similar
   rule without checking.
3. **Whether it's decidable at all.** If compatibility cannot be
   determined from the schema alone (like format changes, R22, or
   `anyOf` / `oneOf` / `not`, R25), the rule must return `UNKNOWN`.
   Never guess to make a rule look more decisive.

If you're unsure about any of the three, open an issue with a minimal
spec pair first and get agreement before writing code.

## Step 1 — Add a golden fixture pair first

Create a directory under `fixtures/` in the right category:

- `fixtures/breaking/` — the change breaks compatibility.
- `fixtures/non-breaking/` — the change is safe (or a warning).
- `fixtures/ambiguous/` — the correct classification is `UNKNOWN`.

Each fixture directory holds exactly three files:

- `base.yaml` — the baseline OpenAPI spec ("before").
- `head.yaml` — the changed spec ("after").
- `expected.json` — the pinned result:

```json
{
  "profile": "server",
  "findings": [
    {"rule": "R28", "severity": "BREAKING", "location": "GET /users/{id}"}
  ]
}
```

Guidelines:

- **Minimal.** One rule (or one coherent change) per fixture. A failing
  test should point at exactly one thing.
- **Realistic.** Write specs that look like a real API, with paths,
  operations, and `application/json` bodies.
- **Exact.** `expected.json` pins the *complete* finding set. If your
  change produces findings you didn't expect, investigate before editing
  the file to match — unexpected findings usually mean the diff or an
  existing rule needs attention, not the fixture.
- **One profile per fixture.** `expected.json` pins one profile (usually
  `server`). If the severity differs under `client`, cover that with a
  unit test (Step 4) instead.

Verify the fixture by hand before wiring it in:

```bash
python -m contractguard check --base fixtures/<name>/base.yaml \
                              --head fixtures/<name>/head.yaml --format json
```

At this point the output will *not* match your `expected.json` — that's
expected. The fixture is the failing test your implementation has to
satisfy.

## Step 2 — Extend the diff engine if needed

Rules consume `Change` objects from `contractguard/diff.py`; they never
re-parse specs. If the diff engine doesn't emit the change kind your rule
needs (for example, a new kind of schema change), add it in `diff.py`
first:

- Emit a distinct `Change.kind` for the new change.
- Give it a precise `location` (operation, schema path, direction).
- Carry `direction` (`request` / `response`) in `change.detail` — the
  rule needs it to decide severity.
- Don't put any severity logic in the diff. The diff describes; the rule
  judges.

If an existing change kind already covers your case, skip this step.

## Step 3 — Implement the rule in `contractguard/rules.py`

1. Add a `_rNN` function, using the next free number after R27. Follow
   the shape of the existing functions: it takes a `Change` and a
   `profile` and returns a `Finding` (or `None` when the change is not a
   compatibility event at all). The `Finding` needs:
   - `rule_id` (e.g. `"R28"`)
   - `severity` (`BREAKING`, `WARNING`, `SAFE`, or `UNKNOWN`)
   - `location` (from the change)
   - `message` — one line, what changed
   - `explanation` — which client behaviour may break, and why
   - `change_kind` — from the change
2. Register the rule in the `RULES` table with its name, direction, and
   server/client severities. This table is what `python -m contractguard
   rules` prints, so keep it accurate.
3. Wire the rule into `classify()` so the change kind dispatches to your
   `_rNN` function.

Keep the rule function small and declarative. If the severity depends on
the change details (direction, whether a field was required), put that
branching in the function — see R17–R20 and R23–R24 for the pattern —
and make sure each branch is covered by a test.

## Step 4 — Add unit tests

In `tests/test_contractguard.py`, add a test that builds two tiny specs
as text (no fixture files needed) and asserts the classification under
**both** profiles. This is the primary coverage for the rule: it makes
the rule testable in isolation and documents the profile difference, if
any.

Also add a golden-fixture test entry for the fixture from Step 1, if the
existing fixture-test loop doesn't pick it up automatically — check how
the current fixture tests enumerate `fixtures/*/` and follow that
pattern.

Then run the suite:

```bash
python -m unittest discover -s tests
python -m contractguard rules        # your rule appears, correct severities
python demo.py                       # demo still passes
```

## Step 5 — Document the rule in `docs/rules.md`

Add a row to the rule table: rule, change, direction, server severity,
client severity. If the reasoning is subtle — a severity that differs
between profiles, a direction that surprises people, or a case where the
rule deliberately returns UNKNOWN — add a short paragraph under
"The rules that need the most care" explaining why.

The table and the code in `rules.py` must agree. Reviewers check the
table; the test suite checks the code.

## Step 6 — Changelog and PR

- Add an entry under `## [Unreleased]` in `CHANGELOG.md` (Added section).
- If the PR changes an *existing* rule's severity, say so explicitly in
  the PR description — that is a breaking change for users' CI, and it
  belongs in the changelog as Changed, not Added.
- Open the PR small and focused: one rule per PR. See
  `CONTRIBUTING.md` for the full PR expectations.

## Worked example (shape of a rule)

A typical new rule looks like this in `rules.py` (simplified):

```python
def _r28(change: Change, profile: str) -> Finding:
    return Finding(
        "R28", "BREAKING", change.location,
        f"{change.location} changed",
        "Existing clients relying on the old behaviour will break because ...",
        change.kind,
    )
```

…plus one row in the `RULES` table, one dispatch entry in `classify()`,
one fixture pair, one unit test, and one row in `docs/rules.md`. That is
the whole contribution. If your change needs more than that, it's
probably two contributions — split it.
