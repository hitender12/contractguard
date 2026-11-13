"""Golden fixtures for every rule R01-R34, positive and negative.

Each directory under fixtures/rules/ holds base.yaml, head.yaml (the
change that must trigger the rule), head_neg.yaml (a closely related
change that must NOT trigger it), and expected.json with the exact
(rule, severity, location) sets under both profiles. This test pins
those sets; if a rule's severities change, update the fixture's
expected.json and docs/rules.md together.
"""

import json
import os
import unittest

from contractguard.baseline import load_base, load_head
from contractguard.diff import diff_contracts
from contractguard.rules import RULES, classify

ROOT = os.path.join(os.path.dirname(__file__), "..", "fixtures", "rules")


def _load_expected(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _triples(base_path, head_path, profile):
    base, _ = load_base(base_file=base_path, base_ref=None, base_path=None)
    head, _ = load_head(head_file=head_path, head_ref=None, head_path=None)
    findings = classify(diff_contracts(base, head), profile=profile)
    return sorted((f.rule_id, f.severity, f.location) for f in findings)


def _expected_triples(entries):
    return sorted((e["rule"], e["severity"], e["location"]) for e in entries)


class TestRuleFixtures(unittest.TestCase):
    def test_every_rule_has_a_fixture(self):
        rule_ids = {r[0] for r in RULES}
        fixture_rules = set()
        for name in os.listdir(ROOT):
            d = os.path.join(ROOT, name)
            if not os.path.isdir(d):
                continue
            self.assertTrue(
                name.startswith("r"), f"unexpected fixture dir {name}"
            )
            rule_id = "R" + name[1:3].upper()
            fixture_rules.add(rule_id)
            for fname in ("base.yaml", "head.yaml", "head_neg.yaml", "expected.json"):
                self.assertTrue(
                    os.path.exists(os.path.join(d, fname)),
                    f"{name} is missing {fname}",
                )
        missing = rule_ids - fixture_rules
        self.assertEqual(missing, set(), f"rules without fixtures: {missing}")

    def test_rule_fixtures(self):
        for name in sorted(os.listdir(ROOT)):
            d = os.path.join(ROOT, name)
            if not os.path.isdir(d):
                continue
            with self.subTest(fixture=name):
                expected = _load_expected(os.path.join(d, "expected.json"))
                rule_id = "R" + name[1:3].upper()
                for label, head_file in (
                    ("positive", "head.yaml"),
                    ("negative", "head_neg.yaml"),
                ):
                    for profile in ("server", "client"):
                        got = _triples(
                            os.path.join(d, "base.yaml"),
                            os.path.join(d, head_file),
                            profile,
                        )
                        want = _expected_triples(expected[label][profile])
                        self.assertEqual(
                            got, want, f"{name} {label} {profile} mismatch"
                        )
                        rules_seen = {t[0] for t in got}
                        if label == "positive":
                            self.assertIn(
                                rule_id, rules_seen,
                                f"{name} positive case must trigger {rule_id}",
                            )
                        else:
                            # Negative case: the rule must not fire with a
                            # non-SAFE severity. (One exception is
                            # deliberate: r24's negative case widens an
                            # enum, which fires R24 SAFE -- the rule
                            # fires, but only to say the change is safe.)
                            bad = {
                                t for t in got
                                if t[0] == rule_id and t[1] != "SAFE"
                            }
                            self.assertEqual(
                                bad, set(),
                                f"{name} negative case must not trigger "
                                f"{rule_id} as breaking/warning/unknown",
                            )


if __name__ == "__main__":
    unittest.main()
