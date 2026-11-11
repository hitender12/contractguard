"""Tests for ContractGuard.

Run: python -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contractguard.baseline import load_base, load_head
from contractguard.diff import diff_contracts
from contractguard.parser import (
    RefError,
    SpecError,
    normalize_spec,
    parse_spec_text,
)
from contractguard.policy import Policy, policy_from_dict
from contractguard.report import render_json, render_markdown, render_sarif
from contractguard.rules import classify
from contractguard.yamlmini import UnsupportedYAML, parse_yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXTURES = os.path.join(ROOT, "fixtures")


def _spec(text: str):
    return parse_spec_text(text)


def _findings(base_text: str, head_text: str, profile: str = "server"):
    base = _spec(base_text)
    head = _spec(head_text)
    return classify(diff_contracts(base, head), profile=profile)


def _by_rule(findings, rule_id: str):
    return [f for f in findings if f.rule_id == rule_id]


def _minimal(paths_yaml: str) -> str:
    return (
        "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\npaths:\n" + paths_yaml
    )


class TestYamlMini(unittest.TestCase):
    def test_nested_maps_and_lists(self):
        doc = parse_yaml(
            "a:\n  b: 1\n  c:\n    - x\n    - y: 2\n      z: 3\nd: [1, 2]\n"
        )
        self.assertEqual(
            doc, {"a": {"b": 1, "c": ["x", {"y": 2, "z": 3}]}, "d": [1, 2]}
        )

    def test_quoted_scalars_and_comments(self):
        doc = parse_yaml("a: 'it''s'  # comment\nb: \"x\\n y\"\nc: true\nd: null\n")
        self.assertEqual(doc["a"], "it's")
        self.assertEqual(doc["b"], "x\n y")
        self.assertIs(doc["c"], True)
        self.assertIsNone(doc["d"])

    def test_flow_mapping_and_block_scalar(self):
        doc = parse_yaml("a: {k: v, n: 2}\nb: |\n  line one\n  line two\n")
        self.assertEqual(doc["a"], {"k": "v", "n": 2})
        self.assertEqual(doc["b"], "line one\nline two\n")

    def test_anchors_rejected_clearly(self):
        with self.assertRaises(UnsupportedYAML):
            parse_yaml("a: &anchor\n  b: 1\n")

    def test_bad_indentation_rejected(self):
        with self.assertRaises(Exception):
            parse_yaml("a:\n b: 1\n  c: 2\n")


class TestParser(unittest.TestCase):
    def test_json_spec(self):
        doc = json.loads(
            '{"openapi": "3.0.0", "info": {"title": "T", "version": "1"}, '
            '"paths": {"/x": {"get": {"responses": {"200": {"description": "ok"}}}}}}'
        )
        contract = normalize_spec(doc)
        self.assertIn(("GET", "/x"), contract.operations)

    def test_ref_resolution(self):
        contract = _spec(
            "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\n"
            "paths:\n  /users:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n          content:\n"
            "            application/json:\n"
            "              schema:\n                $ref: '#/components/schemas/User'\n"
            "components:\n  schemas:\n    User:\n      type: object\n"
            "      properties:\n        id:\n          type: integer\n"
        )
        op = contract.operations[("GET", "/users")]
        schema = op.responses["200"].content["application/json"].schema
        self.assertEqual(schema.type, "object")
        self.assertIn("id", schema.properties)

    def test_remote_ref_rejected(self):
        with self.assertRaises(RefError):
            _spec(
                "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\n"
                "paths:\n  /x:\n    get:\n      responses:\n        '200':\n"
                "          description: ok\n          content:\n"
                "            application/json:\n"
                "              schema:\n                $ref: 'https://example.com/s.yaml#/User'\n"
            )

    def test_swagger_2_rejected(self):
        with self.assertRaises(SpecError):
            _spec("swagger: '2.0'\ninfo:\n  title: T\n  version: '1'\npaths: {}\n")

    def test_allof_merged(self):
        contract = _spec(
            "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\n"
            "paths:\n  /x:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n          content:\n"
            "            application/json:\n              schema:\n"
            "                allOf:\n"
            "                  - type: object\n"
            "                    properties:\n                      a:\n                        type: string\n"
            "                  - type: object\n"
            "                    properties:\n                      b:\n                        type: integer\n"
        )
        schema = contract.operations[("GET", "/x")].responses["200"].content[
            "application/json"
        ].schema
        self.assertEqual(set(schema.properties), {"a", "b"})


class TestRequiredClassifications(unittest.TestCase):
    """The classifications the task requires, tested directly."""

    def test_removed_endpoint_is_breaking(self):
        findings = _findings(
            _minimal("  /users:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
            _minimal("  /other:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
        )
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(findings, "R01")],
            [("R01", "BREAKING")],
        )

    def test_response_field_string_to_integer_is_breaking(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n          content:\n"
            "            application/json:\n              schema:\n"
            "                type: object\n                properties:\n"
            "                  email:\n                    type: string\n"
        )
        head = base.replace("type: string", "type: integer")
        findings = _findings(base, head)
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(findings, "R21")],
            [("R21", "BREAKING")],
        )

    def test_new_required_request_field_per_profile(self):
        base = _minimal(
            "  /u:\n    post:\n      requestBody:\n        required: true\n"
            "        content:\n          application/json:\n            schema:\n"
            "              type: object\n              required: [name]\n"
            "              properties:\n                name:\n                  type: string\n"
            "      responses:\n        '201':\n          description: ok\n"
        )
        head = base.replace(
            "required: [name]",
            "required: [name, region]",
        ).replace(
            "                name:\n                  type: string\n",
            "                name:\n                  type: string\n"
            "                region:\n                  type: string\n",
        )
        server = _findings(base, head, "server")
        client = _findings(base, head, "client")
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(server, "R17")],
            [("R17", "BREAKING")],
        )
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(client, "R17")],
            [("R17", "WARNING")],
        )

    def test_added_optional_response_field_is_safe(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n          content:\n"
            "            application/json:\n              schema:\n"
            "                type: object\n                properties:\n"
            "                  id:\n                    type: integer\n"
        )
        head = base.replace(
            "                  id:\n                    type: integer\n",
            "                  id:\n                    type: integer\n"
            "                  timezone:\n                    type: string\n",
        )
        findings = _findings(base, head)
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(findings, "R17")],
            [("R17", "SAFE")],
        )

    def test_enum_narrowing_is_breaking(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n          content:\n"
            "            application/json:\n              schema:\n"
            "                type: object\n                properties:\n"
            "                  role:\n                    type: string\n"
            "                    enum: [admin, user]\n"
        )
        head = base.replace("enum: [admin, user]", "enum: [admin]")
        findings = _findings(base, head)
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(findings, "R24")],
            [("R24", "BREAKING")],
        )
        # Widening is safe.
        widened = base.replace("enum: [admin, user]", "enum: [admin, user, guest]")
        findings = _findings(base, widened)
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(findings, "R24")],
            [("R24", "SAFE")],
        )

    def test_ambiguous_format_change_is_unknown(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n          content:\n"
            "            application/json:\n              schema:\n"
            "                type: object\n                properties:\n"
            "                  created_at:\n                    type: string\n"
            "                    format: date-time\n"
        )
        head = base.replace("format: date-time", "format: date")
        findings = _findings(base, head)
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(findings, "R22")],
            [("R22", "UNKNOWN")],
        )

    def test_profile_distinction_removed_required_field(self):
        base = _minimal(
            "  /u:\n    post:\n      requestBody:\n        required: true\n"
            "        content:\n          application/json:\n            schema:\n"
            "              type: object\n              required: [name]\n"
            "              properties:\n                name:\n                  type: string\n"
            "      responses:\n        '201':\n          description: ok\n"
        )
        head = base.replace("required: [name]", "required: []").replace(
            "                name:\n                  type: string\n", ""
        )
        server = _findings(base, head, "server")
        client = _findings(base, head, "client")
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(server, "R18")],
            [("R18", "WARNING")],
        )
        self.assertEqual(
            [(f.rule_id, f.severity) for f in _by_rule(client, "R18")],
            [("R18", "BREAKING")],
        )


class TestGoldenFixtures(unittest.TestCase):
    def _check_fixture(self, name: str):
        base_path = os.path.join(FIXTURES, name, "base.yaml")
        head_path = os.path.join(FIXTURES, name, "head.yaml")
        expected_path = os.path.join(FIXTURES, name, "expected.json")
        base, _ = load_base(base_file=base_path, base_ref=None, base_path=None)
        head, _ = load_head(head_file=head_path, head_ref=None, head_path=None)
        with open(expected_path, encoding="utf-8") as handle:
            expected = json.load(handle)
        findings = classify(
            diff_contracts(base, head), profile=expected["profile"]
        )
        got = sorted(
            (f.rule_id, f.severity, f.location) for f in findings
        )
        want = sorted(
            (f["rule"], f["severity"], f["location"])
            for f in expected["findings"]
        )
        self.assertEqual(got, want, f"fixture {name} mismatch")

    def test_breaking_fixture(self):
        self._check_fixture("breaking")

    def test_non_breaking_fixture(self):
        self._check_fixture("non-breaking")

    def test_ambiguous_fixture(self):
        self._check_fixture("ambiguous")


class TestPolicyAndReports(unittest.TestCase):
    def test_policy_default_fails_on_breaking(self):
        findings = _findings(
            _minimal("  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
            _minimal("  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
        )
        self.assertEqual(Policy().exit_code(findings), 1)

    def test_policy_can_allow_breaking(self):
        findings = _findings(
            _minimal("  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
            _minimal("  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
        )
        policy = policy_from_dict({"fail_on": [], "warn_on": ["BREAKING"]})
        self.assertEqual(policy.exit_code(findings), 0)

    def test_json_sarif_markdown_render(self):
        findings = _findings(
            _minimal("  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
            _minimal("  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
        )
        payload = json.loads(render_json(findings, "base", "head"))
        self.assertEqual(payload["summary"]["BREAKING"], 1)
        sarif = json.loads(render_sarif(findings, "base", "head"))
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertEqual(sarif["runs"][0]["results"][0]["level"], "error")
        markdown = render_markdown(findings, "base", "head")
        self.assertIn("## ContractGuard report", markdown)
        self.assertIn("R01", markdown)


class TestGitBaseline(unittest.TestCase):
    def test_base_from_git_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_text = _minimal(
                "  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"
            )
            head_text = _minimal(
                "  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"
            )
            spec_path = os.path.join(tmp, "api.yaml")
            with open(spec_path, "w", encoding="utf-8") as handle:
                handle.write(base_text)
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(
                ["git", "-c", "user.email=a@b.c", "-c", "user.name=t",
                 "add", "api.yaml"], cwd=tmp, check=True,
            )
            subprocess.run(
                ["git", "-c", "user.email=a@b.c", "-c", "user.name=t",
                 "commit", "-qm", "base"], cwd=tmp, check=True,
            )
            with open(spec_path, "w", encoding="utf-8") as handle:
                handle.write(head_text)
            # git show runs in the caller's cwd; scope it to the temp repo
            # to keep the test hermetic.
            import contractguard.baseline as baseline_mod

            original = baseline_mod.spec_from_git

            def _scoped(ref, path, repo=None):
                return original(ref, path, repo=tmp)

            baseline_mod.spec_from_git = _scoped
            try:
                base, label = load_base(
                    base_file=None, base_ref="HEAD", base_path="api.yaml"
                )
            finally:
                baseline_mod.spec_from_git = original
            head, _ = load_head(head_file=spec_path, head_ref=None, head_path=None)
            findings = classify(diff_contracts(base, head), profile="server")
            self.assertTrue(any(f.rule_id == "R01" for f in findings))


if __name__ == "__main__":
    unittest.main()
