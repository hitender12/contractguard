"""Edge-case and full-rule-coverage tests for ContractGuard.

Run: python -m unittest discover -s tests

Scope of this file (see also tests/test_contractguard.py):
- Weird YAML handled (or rejected) by the bundled yamlmini parser.
- Deeply nested schemas and a large generated spec (performance sanity).
- Positive AND negative cases for ALL 27 compatibility rules R01-R27,
  under both the ``server`` and ``client`` profiles where the rule's
  severity depends on the profile.
- Golden-fixture checks for the two fixtures added alongside this file
  (fixtures/breaking-enum-narrowing/ and
  fixtures/non-breaking-optional-addition/), using the same
  (rule, severity, location) comparison as TestGoldenFixtures.

Every test is deterministic and offline. Expectations below were verified
against the tool's actual output before being written down; where the
tool's behaviour is surprising (R11, R27 swap) the test pins the actual
behaviour and says so in its docstring instead of asserting the ideal.
"""

import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contractguard.baseline import load_base, load_head
from contractguard.diff import Change, diff_contracts
from contractguard.parser import SpecError, parse_spec_text
from contractguard.rules import classify
from contractguard.yamlmini import UnsupportedYAML, YAMLParseError, parse_yaml

ROOT = os.path.join(os.path.dirname(__file__), "..")
FIXTURES = os.path.join(ROOT, "fixtures")


def _spec(text: str):
    return parse_spec_text(text)


def _findings(base_text: str, head_text: str, profile: str = "server"):
    return classify(
        diff_contracts(_spec(base_text), _spec(head_text)), profile=profile
    )


def _by_rule(findings, rule_id: str):
    return [f for f in findings if f.rule_id == rule_id]


def _pairs(findings, rule_id: str):
    return [(f.rule_id, f.severity) for f in _by_rule(findings, rule_id)]


def _minimal(paths_yaml: str) -> str:
    return (
        "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\npaths:\n" + paths_yaml
    )


_OK = "'200':\n          description: ok\n"


def _resp_obj(props: str, required=None) -> str:
    """GET /u returning an object with the given properties YAML."""
    req = ""
    if required:
        req = "\n                required: [" + ", ".join(required) + "]"
    return _minimal(
        "  /u:\n    get:\n      responses:\n        '200':\n"
        "          description: ok\n          content:\n"
        "            application/json:\n              schema:\n"
        "                type: object" + req + "\n"
        "                properties:\n" + props
    )


def _req_obj(props: str, required=None, body_required: bool = True) -> str:
    """POST /u with a request-body object with the given properties YAML."""
    req = ""
    if required:
        req = "\n              required: [" + ", ".join(required) + "]"
    return _minimal(
        "  /u:\n    post:\n      requestBody:\n"
        f"        required: {'true' if body_required else 'false'}\n"
        "        content:\n          application/json:\n            schema:\n"
        "              type: object" + req + "\n"
        "              properties:\n" + props
        + "      responses:\n        '201':\n          description: ok\n"
    )


def _get_with_param(param_yaml: str) -> str:
    return _minimal(
        "  /u:\n    get:\n      parameters:\n" + param_yaml
        + "      responses:\n        " + _OK
    )


def _field(name: str, *lines: str) -> str:
    """One object property, e.g. _field('id', 'type: integer')."""
    out = f"                  {name}:\n"
    for line in lines:
        out += f"                    {line}\n"
    return out


# ---------------------------------------------------------------------------
# YAML edge cases
# ---------------------------------------------------------------------------


class TestYamlEdgeCases(unittest.TestCase):
    def test_empty_document_is_none(self):
        self.assertIsNone(parse_yaml(""))
        self.assertIsNone(parse_yaml("\n\n"))

    def test_comments_only_document_is_none(self):
        self.assertIsNone(parse_yaml("# just a comment\n# another\n"))

    def test_comment_after_value_and_full_line_comments(self):
        doc = parse_yaml("a: 1 # trailing\n# standalone\nb: 2\n")
        self.assertEqual(doc, {"a": 1, "b": 2})

    def test_odd_three_space_indentation(self):
        # yamlmini accepts any consistent indent width, not just 2.
        doc = parse_yaml("a:\n   b: 1\n   c:\n      d: 2\n")
        self.assertEqual(doc, {"a": {"b": 1, "c": {"d": 2}}})

    def test_quoted_keys_values_and_number_like_strings(self):
        doc = parse_yaml("'a b': \"x y\"\n'200': ok\nn: '200'\nv: '3.0.3'\nb: 'true'\n")
        self.assertEqual(doc["a b"], "x y")
        self.assertEqual(doc["200"], "ok")
        self.assertEqual(doc["n"], "200")
        self.assertIsInstance(doc["n"], str)
        self.assertEqual(doc["v"], "3.0.3")
        self.assertEqual(doc["b"], "true")
        self.assertIsInstance(doc["b"], str)

    def test_quoted_string_with_colon_and_url(self):
        doc = parse_yaml("a: 'http://example.com:8080/y'\n")
        self.assertEqual(doc["a"], "http://example.com:8080/y")

    def test_empty_values_and_empty_flow_collections(self):
        doc = parse_yaml("a:\nb: 2\nc: []\nd: {}\n")
        self.assertIsNone(doc["a"])
        self.assertEqual(doc["c"], [])
        self.assertEqual(doc["d"], {})

    def test_unicode_values(self):
        self.assertEqual(parse_yaml("a: café ☃\n"), {"a": "café ☃"})

    def test_block_scalar_literal_and_strip_chomping(self):
        doc = parse_yaml("a: |\n  line one\n  line two\nb: |-\n  x\n  y\n")
        self.assertEqual(doc["a"], "line one\nline two\n")
        self.assertEqual(doc["b"], "x\ny")  # |- strips the trailing newline

    def test_nested_flow_collections(self):
        doc = parse_yaml("a: {b: [1, {c: 2}], d: {}}\n")
        self.assertEqual(doc, {"a": {"b": [1, {"c": 2}], "d": {}}})

    def test_tabs_rejected(self):
        with self.assertRaises(YAMLParseError):
            parse_yaml("a:\n\tb: 1\n")

    def test_anchors_and_aliases_rejected(self):
        with self.assertRaises(UnsupportedYAML):
            parse_yaml("a: &anchor\n  b: 1\n")

    def test_multiline_single_quoted_scalar_rejected(self):
        # yamlmini does not fold a quoted scalar across lines.
        with self.assertRaises(YAMLParseError):
            parse_yaml("a: 'single\n  continued'\n")

    def test_nested_sequence_of_sequences_rejected(self):
        with self.assertRaises(YAMLParseError):
            parse_yaml("a:\n  - - 1\n    - 2\n  - 3\n")

    def test_duplicate_key_last_value_wins(self):
        # Documented behaviour (not necessarily ideal): no error, the
        # later value silently overwrites the earlier one.
        self.assertEqual(parse_yaml("a: 1\na: 2\n"), {"a": 2})

    def test_empty_spec_text_rejected(self):
        with self.assertRaises(SpecError):
            parse_spec_text("")

    def test_spec_with_no_paths_parses_to_empty_contract(self):
        contract = _spec(
            "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\npaths: {}\n"
        )
        self.assertEqual(contract.operations, {})


# ---------------------------------------------------------------------------
# Deep nesting + large specs
# ---------------------------------------------------------------------------


def _nested_object(depth: int, leaf_type: str) -> dict:
    """{"type": "object", "properties": {"n0": {... "leaf": {type}}}}."""
    schema: dict = {"type": leaf_type}
    for level in reversed(range(depth)):
        schema = {
            "type": "object",
            "properties": {f"n{level}": schema},
        }
    return schema


def _json_spec(schema: dict) -> str:
    return json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/u": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {
                                    "application/json": {"schema": schema}
                                },
                            }
                        }
                    }
                }
            },
        }
    )


class TestDeepNesting(unittest.TestCase):
    def test_identical_deep_schema_has_no_findings(self):
        text = _json_spec(_nested_object(12, "string"))
        self.assertEqual(_findings(text, text), [])

    def test_type_change_at_depth_12_is_breaking(self):
        base = _json_spec(_nested_object(12, "string"))
        head = _json_spec(_nested_object(12, "integer"))
        findings = _findings(base, head)
        self.assertEqual(_pairs(findings, "R21"), [("R21", "BREAKING")])
        self.assertEqual(len(findings), 1)
        leaf = ".".join(f"n{i}" for i in range(12))
        self.assertEqual(
            findings[0].location, f"GET /u > response 200.{leaf}"
        )

    def test_deep_schema_survives_ref_and_allof(self):
        # A $ref to a deeply nested component schema still resolves.
        base = (
            "openapi: 3.0.3\ninfo:\n  title: T\n  version: '1'\npaths:\n"
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n          content:\n"
            "            application/json:\n              schema:\n"
            "                $ref: '#/components/schemas/Deep'\n"
            "components:\n  schemas:\n    Deep:\n      type: object\n"
            "      properties:\n        a:\n          type: object\n"
            "          properties:\n            b:\n"
            "              type: object\n"
            "              properties:\n                c:\n"
            "                  type: string\n"
        )
        head = base.replace("type: string", "type: integer")
        findings = _findings(base, head)
        self.assertEqual(_pairs(findings, "R21"), [("R21", "BREAKING")])
        self.assertIn("a.b.c", findings[0].location)


def _large_spec(n_ops: int, changed_op: int | None = None) -> str:
    """A spec with n_ops GET operations, each with a param + object schema."""
    lines = ["openapi: 3.0.3", "info:", "  title: T", "  version: '1'", "paths:"]
    for i in range(n_ops):
        leaf = "integer" if i != changed_op else "string"
        lines += [
            f"  /item{i}:",
            "    get:",
            "      parameters:",
            "        - name: limit",
            "          in: query",
            "          required: false",
            "          schema:",
            "            type: integer",
            "      responses:",
            "        '200':",
            "          description: ok",
            "          content:",
            "            application/json:",
            "              schema:",
            "                type: object",
            "                properties:",
            "                  id:",
            f"                    type: {leaf}",
            "                  name:",
            "                    type: string",
        ]
    return "\n".join(lines) + "\n"


class TestLargeSpecPerformance(unittest.TestCase):
    def test_300_operations_identical_is_fast_and_clean(self):
        text = _large_spec(300)
        start = time.monotonic()
        findings = _findings(text, text)
        elapsed = time.monotonic() - start
        self.assertEqual(findings, [])
        # Generous bound for a slow CI box; observed locally ~0.1s.
        self.assertLess(elapsed, 5.0, f"300-op diff took {elapsed:.2f}s")

    def test_300_operations_single_change_found(self):
        base = _large_spec(300)
        head = _large_spec(300, changed_op=150)
        start = time.monotonic()
        findings = _findings(base, head)
        elapsed = time.monotonic() - start
        self.assertEqual(_pairs(findings, "R21"), [("R21", "BREAKING")])
        self.assertEqual(len(findings), 1)
        self.assertIn("/item150", findings[0].location)
        self.assertLess(elapsed, 5.0, f"300-op diff took {elapsed:.2f}s")

    def test_300_operations_one_removed(self):
        base = _large_spec(300)
        head = _large_spec(299)  # drops /item299
        findings = _findings(base, head)
        self.assertEqual(_pairs(findings, "R01"), [("R01", "BREAKING")])
        self.assertEqual(len(findings), 1)


# ---------------------------------------------------------------------------
# No-op changes: nothing semantic changed, so no findings at all
# ---------------------------------------------------------------------------


class TestNoOpChanges(unittest.TestCase):
    def test_identical_specs(self):
        text = _resp_obj(_field("id", "type: integer"))
        self.assertEqual(_findings(text, text), [])

    def test_description_only_change(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n"
        )
        head = base.replace("description: ok", "description: changed wording")
        self.assertEqual(_findings(base, head), [])

    def test_info_title_and_version_only_change(self):
        base = _resp_obj(_field("id", "type: integer"))
        head = base.replace("title: T", "title: Renamed").replace(
            "version: '1'", "version: '2'"
        )
        self.assertEqual(_findings(base, head), [])


# ---------------------------------------------------------------------------
# All 27 rules, server profile (plus client flips where they differ)
# ---------------------------------------------------------------------------

_RESP_ID = _field("id", "type: integer")
_RESP_ID_NAME = _RESP_ID + _field("name", "type: string")
_REQ_NAME = _field("name", "type: string")
_OPT_PARAM = (
    "        - name: q\n          in: query\n"
    "          required: false\n          schema:\n            type: string\n"
)
_REQ_PARAM = _OPT_PARAM.replace("required: false", "required: true")
_POST_NO_BODY = (
    "  /u:\n    post:\n      responses:\n        '201':\n          description: ok\n"
)


class TestRulesOperationsAndResponses(unittest.TestCase):
    # R01 / R02
    def test_r01_operation_removed_breaking(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        " + _OK
            + "  /v:\n    get:\n      responses:\n        " + _OK
        )
        head = _minimal("  /v:\n    get:\n      responses:\n        " + _OK)
        for profile in ("server", "client"):
            self.assertEqual(
                _pairs(_findings(base, head, profile), "R01"),
                [("R01", "BREAKING")],
            )

    def test_r02_operation_added_safe(self):
        base = _minimal("  /u:\n    get:\n      responses:\n        " + _OK)
        head = _minimal(
            "  /u:\n    get:\n      responses:\n        " + _OK
            + "  /v:\n    get:\n      responses:\n        " + _OK
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R02"), [("R02", "SAFE")]
        )

    # R03 / R04
    def test_r03_response_removed_breaking(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n        '404':\n"
            "          description: not found\n"
        )
        head = _minimal(
            "  /u:\n    get:\n      responses:\n        " + _OK
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R03"), [("R03", "BREAKING")]
        )

    def test_r04_response_added_safe(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        " + _OK
        )
        head = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n        '404':\n"
            "          description: not found\n"
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R04"), [("R04", "SAFE")]
        )


class TestRulesParameters(unittest.TestCase):
    # R05 / R06
    def test_r05_required_parameter_added(self):
        base = _minimal("  /u:\n    get:\n      responses:\n        " + _OK)
        head = _get_with_param(_REQ_PARAM)
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R05"),
            [("R05", "BREAKING")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R05"),
            [("R05", "WARNING")],
        )

    def test_r06_optional_parameter_added_safe(self):
        base = _minimal("  /u:\n    get:\n      responses:\n        " + _OK)
        head = _get_with_param(_OPT_PARAM)
        self.assertEqual(
            _pairs(_findings(base, head), "R06"), [("R06", "SAFE")]
        )

    # R07 / R08
    def test_r07_required_parameter_removed(self):
        base, head = _get_with_param(_REQ_PARAM), _minimal(
            "  /u:\n    get:\n      responses:\n        " + _OK
        )
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R07"),
            [("R07", "SAFE")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R07"),
            [("R07", "BREAKING")],
        )

    def test_r08_optional_parameter_removed_safe(self):
        base, head = _get_with_param(_OPT_PARAM), _minimal(
            "  /u:\n    get:\n      responses:\n        " + _OK
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R08"), [("R08", "SAFE")]
        )

    # R09 / R10
    def test_r09_parameter_optional_to_required(self):
        base, head = _get_with_param(_OPT_PARAM), _get_with_param(_REQ_PARAM)
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R09"),
            [("R09", "BREAKING")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R09"),
            [("R09", "SAFE")],
        )

    def test_r10_parameter_required_to_optional(self):
        base, head = _get_with_param(_REQ_PARAM), _get_with_param(_OPT_PARAM)
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R10"),
            [("R10", "SAFE")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R10"),
            [("R10", "BREAKING")],
        )

    def test_r11_parameter_moved_is_breaking(self):
        """A parameter moved query -> header emits R11 BREAKING.

        Regression test for the audit finding B1: the diff used to key
        parameters by (name, location), so a move was seen as an
        optional-parameter removal (R08) plus an optional-parameter
        addition (R06) -- both SAFE. Parameters are now matched by name,
        so a location move emits parameter-location-changed (R11).
        """
        base = _get_with_param(_OPT_PARAM)
        head = _get_with_param(
            _OPT_PARAM.replace("in: query", "in: header")
        )
        for profile in ("server", "client"):
            findings = _findings(base, head, profile)
            self.assertEqual(_pairs(findings, "R11"), [("R11", "BREAKING")])
            self.assertEqual(
                sorted((f.rule_id, f.severity) for f in findings),
                [("R11", "BREAKING")],
            )


class TestRulesRequestBody(unittest.TestCase):
    def _body(self, required: bool) -> str:
        return _minimal(
            "  /u:\n    post:\n      requestBody:\n"
            f"        required: {'true' if required else 'false'}\n"
            "        content:\n          application/json:\n            schema:\n"
            "              type: object\n              properties:\n"
            + _REQ_NAME
            + "      responses:\n        '201':\n          description: ok\n"
        )

    def test_r12_required_body_added(self):
        base = _minimal(_POST_NO_BODY)
        self.assertEqual(
            _pairs(_findings(base, self._body(True), "server"), "R12"),
            [("R12", "BREAKING")],
        )
        self.assertEqual(
            _pairs(_findings(base, self._body(True), "client"), "R12"),
            [("R12", "WARNING")],
        )

    def test_r13_optional_body_added_safe(self):
        base = _minimal(_POST_NO_BODY)
        self.assertEqual(
            _pairs(_findings(base, self._body(False)), "R13"),
            [("R13", "SAFE")],
        )

    def test_r14_body_removed(self):
        base = self._body(True)
        head = _minimal(_POST_NO_BODY)
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R14"),
            [("R14", "SAFE")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R14"),
            [("R14", "BREAKING")],
        )

    def test_r15_body_optional_to_required(self):
        self.assertEqual(
            _pairs(
                _findings(self._body(False), self._body(True), "server"),
                "R15",
            ),
            [("R15", "BREAKING")],
        )
        self.assertEqual(
            _pairs(
                _findings(self._body(False), self._body(True), "client"),
                "R15",
            ),
            [("R15", "SAFE")],
        )

    def test_r16_body_required_to_optional(self):
        self.assertEqual(
            _pairs(
                _findings(self._body(True), self._body(False), "server"),
                "R16",
            ),
            [("R16", "SAFE")],
        )
        self.assertEqual(
            _pairs(
                _findings(self._body(True), self._body(False), "client"),
                "R16",
            ),
            [("R16", "BREAKING")],
        )


class TestRulesSchemaFields(unittest.TestCase):
    # R17: field added
    def test_r17_required_request_field_added(self):
        base = _req_obj(_REQ_NAME, required=["name"])
        head = _req_obj(
            _REQ_NAME + _field("region", "type: string"),
            required=["name", "region"],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R17"),
            [("R17", "BREAKING")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R17"),
            [("R17", "WARNING")],
        )

    def test_r17_optional_request_field_added_safe(self):
        base = _req_obj(_REQ_NAME, required=["name"])
        head = _req_obj(
            _REQ_NAME + _field("region", "type: string"), required=["name"]
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R17"), [("R17", "SAFE")]
        )

    def test_r17_optional_response_field_added_safe(self):
        base = _resp_obj(_RESP_ID)
        head = _resp_obj(_RESP_ID + _field("timezone", "type: string"))
        self.assertEqual(
            _pairs(_findings(base, head), "R17"), [("R17", "SAFE")]
        )

    def test_r17_required_response_field_added(self):
        # Server profile: SAFE (old clients ignore the extra field);
        # client profile: WARNING (a new client reading it fails on old
        # servers that do not send it).
        base = _resp_obj(_RESP_ID)
        head = _resp_obj(
            _RESP_ID + _field("timezone", "type: string"),
            required=["timezone"],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R17"),
            [("R17", "SAFE")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R17"),
            [("R17", "WARNING")],
        )

    # R18: field removed
    def test_r18_response_field_removed_breaking(self):
        base = _resp_obj(_RESP_ID_NAME, required=["id"])
        head = _resp_obj(_RESP_ID)
        self.assertEqual(
            _pairs(_findings(base, head), "R18"), [("R18", "BREAKING")]
        )

    def test_r18_required_request_field_removed(self):
        base = _req_obj(_REQ_NAME, required=["name"])
        head = _req_obj("", required=[])
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R18"),
            [("R18", "WARNING")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R18"),
            [("R18", "BREAKING")],
        )

    def test_r18_optional_request_field_removed_safe(self):
        base = _req_obj(_REQ_NAME, required=[])
        head = _req_obj("", required=[])
        self.assertEqual(
            _pairs(_findings(base, head), "R18"), [("R18", "SAFE")]
        )

    # R19: required -> optional
    def test_r19_response_field_required_to_optional_warning(self):
        base = _resp_obj(_RESP_ID, required=["id"])
        head = _resp_obj(_RESP_ID, required=[])
        for profile in ("server", "client"):
            self.assertEqual(
                _pairs(_findings(base, head, profile), "R19"),
                [("R19", "WARNING")],
            )

    def test_r19_request_field_required_to_optional(self):
        base = _req_obj(_REQ_NAME, required=["name"])
        head = _req_obj(_REQ_NAME, required=[])
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R19"),
            [("R19", "SAFE")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R19"),
            [("R19", "BREAKING")],
        )

    # R20: optional -> required
    def test_r20_response_field_optional_to_required(self):
        base = _resp_obj(_RESP_ID, required=[])
        head = _resp_obj(_RESP_ID, required=["id"])
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R20"),
            [("R20", "SAFE")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R20"),
            [("R20", "WARNING")],
        )

    def test_r20_request_field_optional_to_required(self):
        base = _req_obj(_REQ_NAME, required=[])
        head = _req_obj(_REQ_NAME, required=["name"])
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R20"),
            [("R20", "BREAKING")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R20"),
            [("R20", "SAFE")],
        )


class TestRulesSchemaSemantics(unittest.TestCase):
    # R21: type changed
    def test_r21_response_type_change_breaking(self):
        base = _resp_obj(_field("email", "type: string"))
        head = _resp_obj(_field("email", "type: integer"))
        self.assertEqual(
            _pairs(_findings(base, head), "R21"), [("R21", "BREAKING")]
        )

    def test_r21_request_type_change_breaking(self):
        base = _req_obj(_field("count", "type: string"))
        head = _req_obj(_field("count", "type: integer"))
        self.assertEqual(
            _pairs(_findings(base, head), "R21"), [("R21", "BREAKING")]
        )

    def test_r21_array_items_type_change_breaking(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n          content:\n"
            "            application/json:\n              schema:\n"
            "                type: array\n                items:\n"
            "                  type: string\n"
        )
        head = base.replace("items:\n                  type: string",
                            "items:\n                  type: integer")
        findings = _findings(base, head)
        self.assertEqual(_pairs(findings, "R21"), [("R21", "BREAKING")])
        self.assertEqual(findings[0].location, "GET /u > response 200[]")

    def test_r21_type_removed_is_also_breaking(self):
        # Dropping `type:` entirely changes the type from string to absent.
        base = _resp_obj(_field("email", "type: string"))
        head = _resp_obj(_field("email", "description: free text"))
        self.assertEqual(
            _pairs(_findings(base, head), "R21"), [("R21", "BREAKING")]
        )

    # R22: format changed
    def test_r22_format_change_unknown(self):
        base = _resp_obj(
            _field("created_at", "type: string", "format: date-time")
        )
        head = _resp_obj(_field("created_at", "type: string", "format: date"))
        self.assertEqual(
            _pairs(_findings(base, head), "R22"), [("R22", "UNKNOWN")]
        )

    def test_r22_request_format_change_unknown(self):
        base = _req_obj(_field("email", "type: string", "format: email"))
        head = _req_obj(_field("email", "type: string"))
        self.assertEqual(
            _pairs(_findings(base, head), "R22"), [("R22", "UNKNOWN")]
        )

    # R23: nullable changed
    def test_r23_response_becomes_nullable_warning(self):
        base = _resp_obj(_field("nick", "type: string", "nullable: false"))
        head = _resp_obj(_field("nick", "type: string", "nullable: true"))
        self.assertEqual(
            _pairs(_findings(base, head), "R23"), [("R23", "WARNING")]
        )

    def test_r23_response_stops_being_nullable_safe(self):
        base = _resp_obj(_field("nick", "type: string", "nullable: true"))
        head = _resp_obj(_field("nick", "type: string", "nullable: false"))
        self.assertEqual(
            _pairs(_findings(base, head), "R23"), [("R23", "SAFE")]
        )

    def test_r23_request_becomes_nullable_safe(self):
        """A request field becoming nullable is SAFE (docs/rules.md).

        The server accepts null for the field, so existing callers that
        send null keep working and callers that never send null are
        unaffected. Regression test for audit finding B3: the rule used
        to return WARNING for any field becoming nullable, in either
        direction.
        """
        base = _req_obj(_field("nick", "type: string", "nullable: false"))
        head = _req_obj(_field("nick", "type: string", "nullable: true"))
        for profile in ("server", "client"):
            self.assertEqual(
                _pairs(_findings(base, head, profile), "R23"),
                [("R23", "SAFE")],
            )

    def test_r23_request_stops_being_nullable(self):
        base = _req_obj(_field("nick", "type: string", "nullable: true"))
        head = _req_obj(_field("nick", "type: string", "nullable: false"))
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R23"),
            [("R23", "BREAKING")],
        )
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R23"),
            [("R23", "SAFE")],
        )

    # R24: enum changed
    def test_r24_response_enum_narrowing_breaking(self):
        base = _resp_obj(
            _field("role", "type: string", "enum: [admin, user, guest]")
        )
        head = _resp_obj(_field("role", "type: string", "enum: [admin]"))
        self.assertEqual(
            _pairs(_findings(base, head), "R24"), [("R24", "BREAKING")]
        )

    def test_r24_response_enum_widening_safe(self):
        base = _resp_obj(_field("role", "type: string", "enum: [admin, user]"))
        head = _resp_obj(
            _field("role", "type: string", "enum: [admin, user, guest]")
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R24"), [("R24", "SAFE")]
        )

    def test_r24_request_enum_narrowing_profile_dependent(self):
        base = _req_obj(_field("role", "type: string", "enum: [admin, user]"))
        head = _req_obj(_field("role", "type: string", "enum: [admin]"))
        self.assertEqual(
            _pairs(_findings(base, head, "server"), "R24"),
            [("R24", "BREAKING")],
        )
        # Client profile, request direction: a new client only sends
        # values the old server still accepts.
        self.assertEqual(
            _pairs(_findings(base, head, "client"), "R24"),
            [("R24", "SAFE")],
        )

    def test_r24_enum_reordered_only_is_spuriously_flagged(self):
        """PINNED QUIRK: reordering an enum with identical values is
        flagged as R24 SAFE, not ignored.

        diff compares enum lists in order, so [admin, user] vs
        [user, admin] differs; with no values removed or added the rule
        falls through to the "widened" branch with an empty added list
        ("enum widened: added "). Harmless severity-wise (SAFE), but
        noisy: a reorder-only PR gets a finding it should not.
        """
        base = _resp_obj(_field("role", "type: string", "enum: [admin, user]"))
        head = _resp_obj(_field("role", "type: string", "enum: [user, admin]"))
        findings = _findings(base, head)
        self.assertEqual(_pairs(findings, "R24"), [("R24", "SAFE")])
        self.assertEqual(len(findings), 1)

    # R25: composite changed
    def test_r25_oneof_narrowing_unknown(self):
        base = _resp_obj(
            "                  metadata:\n"
            "                    oneOf:\n"
            "                      - type: string\n"
            "                      - type: integer\n"
        )
        head = _resp_obj(
            "                  metadata:\n"
            "                    oneOf:\n"
            "                      - type: string\n"
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R25"), [("R25", "UNKNOWN")]
        )

    def test_r25_anyof_change_unknown(self):
        base = _resp_obj(
            "                  metadata:\n"
            "                    anyOf:\n"
            "                      - type: string\n"
            "                      - type: integer\n"
        )
        head = _resp_obj(
            "                  metadata:\n"
            "                    anyOf:\n"
            "                      - type: string\n"
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R25"), [("R25", "UNKNOWN")]
        )

    def test_r25_unchanged_composite_is_no_finding(self):
        text = _resp_obj(
            "                  metadata:\n"
            "                    anyOf:\n"
            "                      - type: string\n"
            "                      - type: integer\n"
        )
        self.assertEqual(_findings(text, text), [])

    # R26: schema removed
    def test_r26_parameter_schema_removed_breaking(self):
        base = _get_with_param(
            "        - name: q\n          in: query\n"
            "          schema:\n            type: string\n"
        )
        head = _get_with_param("        - name: q\n          in: query\n")
        self.assertEqual(
            _pairs(_findings(base, head), "R26"), [("R26", "BREAKING")]
        )

    def test_r26_response_schema_removed_breaking(self):
        base = _resp_obj(_RESP_ID)
        head = _minimal(
            "  /u:\n    get:\n      responses:\n        '200':\n"
            "          description: ok\n          content:\n"
            "            application/json: {}\n"
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R26"), [("R26", "BREAKING")]
        )


class TestRulesSecurity(unittest.TestCase):
    # R27: security changed
    def _secured(self, security_yaml: str) -> str:
        return _minimal(
            "  /u:\n    get:\n" + security_yaml
            + "      responses:\n        " + _OK
        )

    def test_r27_operation_security_added_warning(self):
        base = self._secured("")
        head = self._secured("      security:\n        - BearerAuth: []\n")
        self.assertEqual(
            _pairs(_findings(base, head), "R27"), [("R27", "WARNING")]
        )

    def test_r27_operation_security_removed_safe(self):
        base = self._secured("      security:\n        - BearerAuth: []\n")
        head = self._secured("")
        self.assertEqual(
            _pairs(_findings(base, head), "R27"), [("R27", "SAFE")]
        )

    def test_r27_security_scheme_swapped_is_warning(self):
        """Swapping BearerAuth for ApiKeyAuth changes which credentials a
        client needs, so it is WARNING.

        Regression test for the audit finding B4 (related): the rule
        used to only distinguish added vs not-added, so a swap from a
        non-empty base was reported SAFE. It now compares requirement
        sets, so added, removed, and swapped requirements are each
        classified correctly.
        """
        base = self._secured("      security:\n        - BearerAuth: []\n")
        head = self._secured("      security:\n        - ApiKeyAuth: []\n")
        self.assertEqual(
            _pairs(_findings(base, head), "R27"), [("R27", "WARNING")]
        )

    def test_r27_security_requirement_added_to_nonempty_is_warning(self):
        """Adding a second requirement to a non-empty list is WARNING."""
        base = self._secured("      security:\n        - BearerAuth: []\n")
        head = self._secured(
            "      security:\n        - BearerAuth: []\n        - ApiKeyAuth: []\n"
        )
        self.assertEqual(
            _pairs(_findings(base, head), "R27"), [("R27", "WARNING")]
        )

    def test_r27_global_security_added_warning(self):
        base = _minimal("  /u:\n    get:\n      responses:\n        " + _OK)
        head = base + "security:\n  - BearerAuth: []\n"
        findings = _findings(base, head)
        self.assertEqual(_pairs(findings, "R27"), [("R27", "WARNING")])
        self.assertEqual(findings[0].location, "security")

    def test_r27_global_security_removed_safe(self):
        base = _minimal(
            "  /u:\n    get:\n      responses:\n        " + _OK
        ) + "security:\n  - BearerAuth: []\n"
        head = _minimal("  /u:\n    get:\n      responses:\n        " + _OK)
        self.assertEqual(
            _pairs(_findings(base, head), "R27"), [("R27", "SAFE")]
        )


class TestClassifyFallbacks(unittest.TestCase):
    def test_r00_unclassified_change_kind_is_unknown(self):
        findings = classify([Change("weird-kind", "X", {})])
        self.assertEqual(
            [(f.rule_id, f.severity) for f in findings],
            [("R00", "UNKNOWN")],
        )

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError):
            classify([], profile="bogus")

    def test_empty_change_list_is_empty(self):
        self.assertEqual(classify([], profile="server"), [])
        self.assertEqual(classify([], profile="client"), [])


# ---------------------------------------------------------------------------
# Golden fixtures added with this file
# ---------------------------------------------------------------------------


class TestNewGoldenFixtures(unittest.TestCase):
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
        got = sorted((f.rule_id, f.severity, f.location) for f in findings)
        want = sorted(
            (f["rule"], f["severity"], f["location"])
            for f in expected["findings"]
        )
        self.assertEqual(got, want, f"fixture {name} mismatch")

    def test_breaking_enum_narrowing_fixture(self):
        self._check_fixture("breaking-enum-narrowing")

    def test_non_breaking_optional_addition_fixture(self):
        self._check_fixture("non-breaking-optional-addition")


if __name__ == "__main__":
    unittest.main()
