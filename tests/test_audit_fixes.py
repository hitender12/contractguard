"""Regression tests for the 2026-11-11 independent QA audit findings.

Each test is named for the finding it pins (B1-B14, plus the gap items
from the audit). The per-rule golden fixtures in test_rule_fixtures.py
cover the rule behaviour itself; these tests cover the surrounding
claims (docs, reports, CLI wiring, parser behaviour).
"""

import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contractguard.baseline import load_base, load_head
from contractguard.cli import main
from contractguard.diff import diff_contracts
from contractguard.parser import parse_spec_text
from contractguard.policy import Policy, policy_from_dict
from contractguard.report import render_json, render_sarif, render_terminal
from contractguard.rules import RULES, classify
from contractguard.yamlmini import UnsupportedYAML, parse_yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _spec(text: str):
    return parse_spec_text(text)


def _findings(base_text: str, head_text: str, profile: str = "server"):
    base = _spec(base_text)
    head = _spec(head_text)
    return classify(diff_contracts(base, head), profile=profile)


def _minimal(paths_yaml: str) -> str:
    return (
        "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\npaths:\n" + paths_yaml
    )


class TestB5ReadmeExampleMatchesReality(unittest.TestCase):
    def test_readme_example_is_verbatim_tool_output(self):
        """The README's first example block is the real breaking-fixture output."""
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as h:
            readme = h.read()
        match = re.search(r"```text\n(.*?)```", readme, re.DOTALL)
        self.assertIsNotNone(match, "README has no ```text example block")
        expected = match.group(1).rstrip("\n")
        old_cwd = os.getcwd()
        try:
            os.chdir(ROOT)
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(
                    [
                        "check",
                        "--base", "fixtures/breaking/base.yaml",
                        "--head", "fixtures/breaking/head.yaml",
                    ]
                )
            self.assertEqual(code, 1)
        finally:
            os.chdir(old_cwd)
        self.assertEqual(buf.getvalue().rstrip("\n"), expected)


class TestB7MultiDocumentRejected(unittest.TestCase):
    def test_second_document_rejected(self):
        with self.assertRaises(UnsupportedYAML):
            parse_yaml("a: 1\n---\nb: 2\n")

    def test_content_after_end_marker_rejected(self):
        with self.assertRaises(UnsupportedYAML):
            parse_yaml("a: 1\n...\nb: 2\n")

    def test_leading_document_marker_accepted(self):
        self.assertEqual(parse_yaml("---\na: 1\n"), {"a": 1})

    def test_indented_marker_inside_block_scalar_is_content(self):
        doc = parse_yaml("a: |\n  line one\n  ---\n  line two\n")
        self.assertEqual(doc["a"], "line one\n---\nline two\n")


class TestB8RuleUrlsResolve(unittest.TestCase):
    def test_every_rule_has_an_anchor_in_docs_rules(self):
        with open(os.path.join(ROOT, "docs", "rules.md"), encoding="utf-8") as h:
            docs = h.read()
        anchors = set(re.findall(r'<a id="(r\d+)"></a>', docs))
        for rule_id, *_ in RULES:
            self.assertIn(
                rule_id.lower(), anchors,
                f"docs/rules.md has no anchor for {rule_id}",
            )

    def test_finding_rule_urls_point_at_real_anchors(self):
        with open(os.path.join(ROOT, "docs", "rules.md"), encoding="utf-8") as h:
            docs = h.read()
        anchors = set(re.findall(r'<a id="(r\d+)"></a>', docs))
        findings = _findings(
            _minimal("  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
            _minimal("  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
        )
        for finding in findings:
            anchor = finding.rule_url.split("#", 1)[1]
            self.assertIn(anchor, anchors, f"dead rule_url {finding.rule_url}")


class TestB9InstallAndPython3(unittest.TestCase):
    def test_readme_has_install_instructions(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as h:
            readme = h.read()
        self.assertIn("pip install", readme)

    def test_no_bare_python_commands_in_docs(self):
        """Commands use python3 (this VM has no `python` binary)."""
        files = [
            os.path.join(ROOT, "README.md"),
            os.path.join(ROOT, "CONTRIBUTING.md"),
            os.path.join(ROOT, "demo.py"),
            os.path.join(ROOT, "docs", "adding-a-rule.md"),
            os.path.join(ROOT, "docs", "architecture-overview.md"),
            os.path.join(ROOT, "docs", "rules.md"),
        ]
        for path in files:
            with open(path, encoding="utf-8") as h:
                text = h.read()
            bad = re.findall(r"(?m)^\s*python(\s|$)", text)
            self.assertEqual(
                bad, [], f"{os.path.basename(path)} still uses bare `python`"
            )


class TestB10WarnOnIsHonoured(unittest.TestCase):
    def test_warns_and_classify_finding(self):
        findings = _findings(
            _minimal("  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
            _minimal("  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
        )
        policy = Policy()  # fail_on BREAKING, warn_on WARNING/UNKNOWN
        self.assertEqual(policy.classify_finding(findings[0]), "fail")
        # Two findings: R01 BREAKING (removed /u) and R02 SAFE (added /v).
        self.assertEqual(policy.summary_counts(findings), {"fail": 1, "warn": 0, "pass": 1})
        warning_policy = policy_from_dict({"fail_on": [], "warn_on": ["BREAKING"]})
        self.assertEqual(warning_policy.classify_finding(findings[0]), "warn")
        # warns() returns only the warned findings (R01), not the SAFE one.
        self.assertEqual(warning_policy.warns(findings), [findings[0]])
        self.assertEqual(warning_policy.exit_code(findings), 0)

    def test_fail_wins_on_overlap(self):
        findings = _findings(
            _minimal("  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
            _minimal("  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
        )
        policy = policy_from_dict({"fail_on": ["BREAKING"], "warn_on": ["BREAKING"]})
        self.assertEqual(policy.classify_finding(findings[0]), "fail")
        self.assertEqual(policy.exit_code(findings), 1)

    def test_json_and_terminal_show_policy(self):
        findings = _findings(
            _minimal("  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
            _minimal("  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"),
        )
        policy = Policy()
        payload = json.loads(render_json(findings, "b", "h", policy=policy))
        self.assertEqual(payload["policy"]["fail_on"], ["BREAKING"])
        self.assertEqual(payload["policy"]["outcomes"], {"fail": 1, "warn": 0, "pass": 1})
        terminal = render_terminal(findings, "b", "h", policy=policy)
        self.assertIn("[FAIL] BREAKING", terminal)
        self.assertIn("Policy: 1 fail, 0 warn, 1 pass", terminal)


class TestB11SarifLineNumbers(unittest.TestCase):
    def test_yaml_spec_gets_real_lines(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"
        )
        head = _minimal(
            "  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"
        )
        findings = _findings(base, head)
        # Both operations sit on line 7 of their spec (openapi/info/paths
        # take lines 1-5, the path key line 6, `get:` line 7).
        self.assertEqual(findings[0].line, 7)
        sarif = json.loads(render_sarif(findings, "b", "h"))
        region = sarif["runs"][0]["results"][0]["locations"][0][
            "physicalLocation"
        ]["region"]
        self.assertEqual(region, {"startLine": 7})

    def test_json_spec_omits_region_instead_of_fabricating(self):
        base = json.dumps(
            {"openapi": "3.0.0", "info": {"title": "T", "version": "1"},
             "paths": {"/u": {"get": {"responses": {"200": {"description": "ok"}}}}}}
        )
        head = json.dumps(
            {"openapi": "3.0.0", "info": {"title": "T", "version": "1"},
             "paths": {"/v": {"get": {"responses": {"200": {"description": "ok"}}}}}}
        )
        findings = _findings(base, head)
        self.assertIsNone(findings[0].line)
        sarif = json.loads(render_sarif(findings, "b.json", "h.json"))
        physical = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        self.assertNotIn("region", physical)


class TestB12UnknownKeywords(unittest.TestCase):
    def test_unknown_keyword_change_is_unknown(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"
            "          content:\n            application/json:\n              schema:\n"
            "                type: object\n                x-vendor-ext: abc\n"
            "                properties:\n                  id:\n                    type: integer\n"
        )
        head = base.replace("x-vendor-ext: abc", "x-vendor-ext: xyz")
        findings = _findings(base, head)
        self.assertEqual(
            [(f.rule_id, f.severity) for f in findings],
            [("R28", "UNKNOWN")],
        )

    def test_known_keyword_change_is_not_flagged(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"
            "          content:\n            application/json:\n              schema:\n"
            "                type: object\n                description: A thing\n"
            "                properties:\n                  id:\n                    type: integer\n"
        )
        head = base.replace("A thing", "Another thing")
        self.assertEqual(_findings(base, head), [])


class TestB13DocstringCitesCorrectRules(unittest.TestCase):
    def test_rules_docstring_cites_r22_r25(self):
        import contractguard.rules as rules_mod

        self.assertIn("R22/R25", rules_mod.__doc__)
        self.assertNotIn("R21/R24", rules_mod.__doc__)


class TestB14MediaTypeChanged(unittest.TestCase):
    def test_response_media_type_change_is_breaking(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"
            "          content:\n            application/json:\n              schema:\n"
            "                type: string\n"
        )
        head = base.replace("application/json", "text/plain")
        for profile in ("server", "client"):
            self.assertEqual(
                [(f.rule_id, f.severity) for f in _findings(base, head, profile)],
                [("R29", "BREAKING")],
            )


class TestRepoFlagAndDemo(unittest.TestCase):
    def test_repo_flag_scopes_git_baseline(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            base_text = _minimal(
                "  /u:\n    get:\n      responses:\n        '200':\n          description: ok\n"
            )
            head_text = _minimal(
                "  /v:\n    get:\n      responses:\n        '200':\n          description: ok\n"
            )
            spec_path = os.path.join(tmp, "api.yaml")
            with open(spec_path, "w", encoding="utf-8") as h:
                h.write(base_text)
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(
                ["git", "-c", "user.email=a@b.c", "-c", "user.name=t",
                 "add", "api.yaml"], cwd=tmp, check=True,
            )
            subprocess.run(
                ["git", "-c", "user.email=a@b.c", "-c", "user.name=t",
                 "commit", "-qm", "base"], cwd=tmp, check=True,
            )
            with open(spec_path, "w", encoding="utf-8") as h:
                h.write(head_text)
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            # Run from an unrelated cwd: without --repo this would fail.
            old_cwd = os.getcwd()
            try:
                os.chdir(tempfile.gettempdir())
                with redirect_stdout(buf):
                    code = main(
                        [
                            "check",
                            "--base-ref", "HEAD", "--base-path", "api.yaml",
                            "--head", spec_path,
                            "--repo", tmp,
                        ]
                    )
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 1)
            self.assertIn("R01", buf.getvalue())

    def test_demo_does_not_rewrite_examples(self):
        import hashlib

        def _hash(path):
            with open(path, "rb") as h:
                return hashlib.md5(h.read()).hexdigest()

        targets = [
            os.path.join(ROOT, "examples", "report.json"),
            os.path.join(ROOT, "examples", "report.sarif"),
            os.path.join(ROOT, "examples", "pr-summary.md"),
        ]
        before = {p: _hash(p) for p in targets}
        import demo as demo_mod

        self.assertEqual(demo_mod.run(write_examples=False), 0)
        after = {p: _hash(p) for p in targets}
        self.assertEqual(before, after)


class TestGitHubAction(unittest.TestCase):
    def test_action_yml_is_a_valid_composite_action(self):
        with open(os.path.join(ROOT, "action", "action.yml"), encoding="utf-8") as h:
            action = parse_yaml(h.read())
        self.assertEqual(action["runs"]["using"], "composite")
        for key in ("base", "head", "profile", "fail-on", "warn-on", "comment"):
            self.assertIn(key, action["inputs"], f"action missing input {key}")
        step_ids = [s["id"] for s in action["runs"]["steps"]]
        for required in ("install", "check", "comment", "gate"):
            self.assertIn(required, step_ids)
        self.assertIn("exit-code", action["outputs"])
        self.assertIn("breaking", action["outputs"])


class TestYamlBlockScalarInSequenceItems(unittest.TestCase):
    def test_block_scalar_after_dash_key(self):
        doc = parse_yaml(
            "steps:\n"
            "  - id: check\n"
            "    shell: bash\n"
            "    run: |\n"
            "      echo hello\n"
            "      echo world\n"
        )
        self.assertEqual(
            doc["steps"][0]["run"], "echo hello\necho world\n"
        )


if __name__ == "__main__":
    unittest.main()
