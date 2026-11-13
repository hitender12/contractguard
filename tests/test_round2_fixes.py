"""Regression tests for the 2026-11-11 round-2 independent re-audit.

Each test is named for the finding it pins (N10b, N4, N1b, N23, N18,
N6/N16). The per-rule golden fixtures in test_rule_fixtures.py cover
R32/R33/R34 themselves; these tests cover the surrounding behaviour
(CLI validation, parser cycle-safety, YAML duplicate rejection, and
the rule boundaries).
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contractguard.baseline import load_base, load_head
from contractguard.cli import main
from contractguard.diff import diff_contracts
from contractguard.parser import RefError, SpecError, parse_spec_text
from contractguard.rules import classify
from contractguard.yamlmini import YAMLParseError, parse_yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")
BREAKING_BASE = os.path.join(ROOT, "fixtures", "breaking", "base.yaml")
BREAKING_HEAD = os.path.join(ROOT, "fixtures", "breaking", "head.yaml")


def _spec(text: str):
    return parse_spec_text(text)


def _findings(base_text: str, head_text: str, profile: str = "server"):
    base = _spec(base_text)
    head = _spec(head_text)
    return classify(diff_contracts(base, head), profile=profile)


def _pairs(findings, rule_id):
    return [(f.rule_id, f.severity) for f in findings if f.rule_id == rule_id]


def _minimal(paths_yaml: str) -> str:
    return (
        "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\npaths:\n" + paths_yaml
    )


def _run_cli(argv):
    """Run main() capturing stdout/stderr; return (exit_code, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class TestN10bFailOnUnknownSeverityRejected(unittest.TestCase):
    def test_fail_on_bogus_exits_2_with_clean_error(self):
        code, _out, err = _run_cli([
            "check", "--base", BREAKING_BASE, "--head", BREAKING_HEAD,
            "--fail-on", "BOGUS",
        ])
        self.assertEqual(code, 2)
        self.assertIn("unknown severities in fail_on", err)
        self.assertNotIn("Traceback", err)

    def test_warn_on_bogus_exits_2_with_clean_error(self):
        code, _out, err = _run_cli([
            "check", "--base", BREAKING_BASE, "--head", BREAKING_HEAD,
            "--warn-on", "BOGUS",
        ])
        self.assertEqual(code, 2)
        self.assertIn("unknown severities in warn_on", err)
        self.assertNotIn("Traceback", err)

    def test_fail_on_valid_severity_still_works(self):
        # BREAKING fails the breaking fixture; UNKNOWN alone does not.
        code, _out, _err = _run_cli([
            "check", "--base", BREAKING_BASE, "--head", BREAKING_HEAD,
            "--fail-on", "BREAKING",
        ])
        self.assertEqual(code, 1)
        code, _out, _err = _run_cli([
            "check", "--base", BREAKING_BASE, "--head", BREAKING_HEAD,
            "--fail-on", "UNKNOWN",
        ])
        self.assertEqual(code, 0)

    def test_fail_on_empty_list_means_nothing_fails(self):
        code, _out, _err = _run_cli([
            "check", "--base", BREAKING_BASE, "--head", BREAKING_HEAD,
            "--fail-on",
        ])
        self.assertEqual(code, 0)


class TestN4EnumReorderIsNotAChange(unittest.TestCase):
    def _enum_spec(self, enum):
        return _minimal(
            "  /u:\n"
            "    get:\n"
            "      responses:\n"
            "        '200':\n"
            "          description: ok\n"
            "          content:\n"
            "            application/json:\n"
            "              schema:\n"
            "                type: object\n"
            "                properties:\n"
            "                  role:\n"
            "                    type: string\n"
            f"                    enum: {enum}\n"
        )

    def test_reorder_only_emits_no_finding(self):
        findings = _findings(
            self._enum_spec("[admin, user]"), self._enum_spec("[user, admin]")
        )
        self.assertEqual(findings, [])

    def test_narrowing_still_fires_r24_breaking(self):
        findings = _findings(
            self._enum_spec("[admin, user]"), self._enum_spec("[admin]")
        )
        self.assertEqual(_pairs(findings, "R24"), [("R24", "BREAKING")])

    def test_widening_still_fires_r24_safe(self):
        findings = _findings(
            self._enum_spec("[admin]"), self._enum_spec("[admin, user]")
        )
        self.assertEqual(_pairs(findings, "R24"), [("R24", "SAFE")])


RECURSIVE_SPEC = """openapi: 3.0.3
info:
  title: T
  version: '1'
paths:
  /nodes:
    get:
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Node'
components:
  schemas:
    Node:
      type: object
      properties:
        value:
          type: string
        child:
          $ref: '#/components/schemas/Node'
    OtherNode:
      type: object
      properties:
        value:
          type: string
"""


class TestN1bRecursiveSchemasAreCycleSafe(unittest.TestCase):
    def test_recursive_schema_parses(self):
        contract = _spec(RECURSIVE_SPEC)
        op = contract.operations[("GET", "/nodes")]
        schema = op.responses["200"].content["application/json"].schema
        self.assertEqual(schema.type, "object")
        # The recursive child is an unexpanded marker, not an expansion.
        child = schema.properties["child"]
        self.assertTrue(child.recursive_ref)
        self.assertEqual(child.ref, "#/components/schemas/Node")

    def test_identical_recursive_schemas_have_no_findings(self):
        self.assertEqual(_findings(RECURSIVE_SPEC, RECURSIVE_SPEC), [])

    def test_recursive_ref_target_change_is_r34_unknown(self):
        head = RECURSIVE_SPEC.replace(
            "        child:\n          $ref: '#/components/schemas/Node'",
            "        child:\n          $ref: '#/components/schemas/OtherNode'",
        )
        findings = _findings(RECURSIVE_SPEC, head)
        self.assertEqual(_pairs(findings, "R34"), [("R34", "UNKNOWN")])
        self.assertEqual(len(findings), 1)

    def test_recursive_ref_replaced_by_inline_schema_is_r34(self):
        head = RECURSIVE_SPEC.replace(
            "        child:\n          $ref: '#/components/schemas/Node'",
            "        child:\n          type: object\n          properties:\n            value:\n              type: string\n",
        )
        findings = _findings(RECURSIVE_SPEC, head)
        self.assertEqual(_pairs(findings, "R34"), [("R34", "UNKNOWN")])

    def test_content_change_to_recursive_target_is_caught_at_first_occurrence(self):
        head = RECURSIVE_SPEC.replace(
            "        value:\n          type: string\n        child:",
            "        value:\n          type: integer\n        child:",
        )
        findings = _findings(RECURSIVE_SPEC, head)
        self.assertEqual(_pairs(findings, "R21"), [("R21", "BREAKING")])
        self.assertEqual(_pairs(findings, "R34"), [])

    def test_indirect_recursion_parses(self):
        spec = """openapi: 3.0.3
info:
  title: T
  version: '1'
paths:
  /a:
    get:
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/A'
components:
  schemas:
    A:
      type: object
      properties:
        b:
          $ref: '#/components/schemas/B'
    B:
      type: object
      properties:
        a:
          $ref: '#/components/schemas/A'
"""
        contract = _spec(spec)
        schema = contract.operations[("GET", "/a")].responses["200"].content[
            "application/json"
        ].schema
        self.assertTrue(schema.properties["b"].properties["a"].recursive_ref)

    def test_ref_only_cycle_is_still_rejected(self):
        spec = """openapi: 3.0.3
info:
  title: T
  version: '1'
paths:
  /a:
    get:
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/A'
components:
  schemas:
    A:
      $ref: '#/components/schemas/B'
    B:
      $ref: '#/components/schemas/A'
"""
        with self.assertRaises(RefError):
            _spec(spec)

    def test_deep_inline_nesting_still_rejected(self):
        schema = {"type": "string"}
        for _ in range(30):
            schema = {"type": "object", "properties": {"n": schema}}
        text = json.dumps({
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {"/u": {"get": {"responses": {"200": {
                "description": "ok",
                "content": {"application/json": {"schema": schema}},
            }}}}},
        })
        with self.assertRaises(RefError):
            _spec(text)


class TestN23DuplicateYamlKeysRejected(unittest.TestCase):
    def test_duplicate_key_in_spec_is_a_spec_error(self):
        text = _minimal(
            "  /u:\n"
            "    get:\n"
            "      responses:\n"
            "        '200':\n"
            "          description: ok\n"
            "          content:\n"
            "            application/json:\n"
            "              schema:\n"
            "                type: string\n"
            "                type: integer\n"
        )
        with self.assertRaises(SpecError) as ctx:
            _spec(text)
        self.assertIn("duplicate key", str(ctx.exception))

    def test_duplicate_key_in_sequence_item_rejected(self):
        with self.assertRaises(YAMLParseError):
            parse_yaml("a:\n  - name: x\n    name: y\n")

    def test_duplicate_key_in_flow_mapping_rejected(self):
        with self.assertRaises(YAMLParseError):
            parse_yaml("a: {b: 1, b: 2}\n")


class TestN18OutputWriteFailureIsClean(unittest.TestCase):
    def test_output_to_unwritable_path_exits_2(self):
        code, _out, err = _run_cli([
            "check", "--base", BREAKING_BASE, "--head", BREAKING_HEAD,
            "--output", "/nonexistent-dir-xyz/report.txt",
        ])
        self.assertEqual(code, 2)
        self.assertIn("cannot write output file", err)
        self.assertNotIn("Traceback", err)


def _op_spec(operation_id_line: str) -> str:
    return _minimal(
        "  /items:\n"
        "    get:\n"
        f"{operation_id_line}"
        "      responses:\n"
        "        '200':\n"
        "          description: ok\n"
        "          content:\n"
        "            application/json:\n"
        "              schema:\n"
        "                type: object\n"
        "                properties:\n"
        "                  name:\n"
        "                    type: string\n"
    )


class TestN6OperationIdCompared(unittest.TestCase):
    def test_rename_is_r32_warning(self):
        findings = _findings(
            _op_spec("      operationId: listItems\n"),
            _op_spec("      operationId: listAllItems\n"),
        )
        self.assertEqual(_pairs(findings, "R32"), [("R32", "WARNING")])
        self.assertEqual(findings[0].location, "GET /items")

    def test_added_operation_id_is_r32_safe(self):
        findings = _findings(_op_spec(""), _op_spec("      operationId: listItems\n"))
        self.assertEqual(_pairs(findings, "R32"), [("R32", "SAFE")])

    def test_removed_operation_id_is_r32_warning(self):
        findings = _findings(
            _op_spec("      operationId: listItems\n"), _op_spec("")
        )
        self.assertEqual(_pairs(findings, "R32"), [("R32", "WARNING")])

    def test_unchanged_operation_id_is_silent(self):
        findings = _findings(
            _op_spec("      operationId: listItems\n"),
            _op_spec("      operationId: listItems\n"),
        )
        self.assertEqual(findings, [])


def _servers_spec(servers_yaml: str) -> str:
    return (
        "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\n"
        + servers_yaml
        + "paths:\n"
        "  /items:\n"
        "    get:\n"
        "      responses:\n"
        "        '200':\n"
        "          description: ok\n"
        "          content:\n"
        "            application/json:\n"
        "              schema:\n"
        "                type: object\n"
        "                properties:\n"
        "                  name:\n"
        "                    type: string\n"
    )


class TestN16ServersCompared(unittest.TestCase):
    def test_server_url_changed_is_r33_warning(self):
        findings = _findings(
            _servers_spec("servers:\n  - url: https://api.example.com\n"),
            _servers_spec("servers:\n  - url: https://api2.example.com\n"),
        )
        self.assertEqual(_pairs(findings, "R33"), [("R33", "WARNING")])
        self.assertEqual(findings[0].location, "servers")

    def test_server_url_added_is_r33_safe(self):
        findings = _findings(
            _servers_spec("servers:\n  - url: https://api.example.com\n"),
            _servers_spec(
                "servers:\n"
                "  - url: https://api.example.com\n"
                "  - url: https://staging.example.com\n"
            ),
        )
        self.assertEqual(_pairs(findings, "R33"), [("R33", "SAFE")])

    def test_server_url_removed_is_r33_warning(self):
        findings = _findings(
            _servers_spec(
                "servers:\n"
                "  - url: https://api.example.com\n"
                "  - url: https://staging.example.com\n"
            ),
            _servers_spec("servers:\n  - url: https://api.example.com\n"),
        )
        self.assertEqual(_pairs(findings, "R33"), [("R33", "WARNING")])

    def test_reorder_changing_default_is_r33_warning(self):
        findings = _findings(
            _servers_spec(
                "servers:\n"
                "  - url: https://api.example.com\n"
                "  - url: https://staging.example.com\n"
            ),
            _servers_spec(
                "servers:\n"
                "  - url: https://staging.example.com\n"
                "  - url: https://api.example.com\n"
            ),
        )
        self.assertEqual(_pairs(findings, "R33"), [("R33", "WARNING")])

    def test_reorder_keeping_default_is_r33_safe(self):
        findings = _findings(
            _servers_spec(
                "servers:\n"
                "  - url: https://api.example.com\n"
                "  - url: https://staging.example.com\n"
                "  - url: https://eu.example.com\n"
            ),
            _servers_spec(
                "servers:\n"
                "  - url: https://api.example.com\n"
                "  - url: https://eu.example.com\n"
                "  - url: https://staging.example.com\n"
            ),
        )
        self.assertEqual(_pairs(findings, "R33"), [("R33", "SAFE")])

    def test_no_servers_on_either_side_is_silent(self):
        findings = _findings(_servers_spec(""), _servers_spec(""))
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
