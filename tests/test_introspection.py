# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for object discovery, property change previews, and script checks."""

import ast
import base64
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ansys.mechanical.mcp import introspection, tools
from ansys.mechanical.mcp.errors import InvalidArgumentsError, StalePreviewError
from tests.test_reliability_fixes import (
    Items,
    assert_ironpython_compatible,
    make_context,
    run_mechanical_script,
)

SCRIPT_BUILDERS = [
    introspection.find_objects_script,
    introspection.describe_object_script,
    introspection.preview_change_script,
    introspection.apply_change_script,
    introspection.check_script_script,
]


def connected(response):
    """Return a context whose Mechanical answers every script with ``response``."""
    mechanical = MagicMock()
    mechanical.run_python_script.return_value = (
        response if isinstance(response, str) else json.dumps(response)
    )
    return make_context(mechanical), mechanical


def sent_payload(mechanical) -> dict:
    """Decode the arguments embedded in the last script sent to Mechanical."""
    script = mechanical.run_python_script.call_args.args[0]
    encoded = re.search(r'_mcp_payload\("([A-Za-z0-9+/=]+)"\)', script).group(1)
    return json.loads(base64.b64decode(encoded))


def script_texts(module) -> list[str]:
    """Return the string literals of a module, with f-string fields replaced by ``X``."""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    fragments = {
        id(part)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for part in node.values
    }
    texts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in fragments:
                texts.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            texts.append(
                "".join(
                    part.value if isinstance(part, ast.Constant) else "X" for part in node.values
                )
            )
    return texts


def dumps_calls(text: str) -> list[str]:
    """Return the full text of every ``json.dumps(...)`` call in ``text``."""
    calls = []
    for match in re.finditer(r"json\.dumps\(", text):
        depth, index = 0, match.end() - 1
        while index < len(text):
            depth += {"(": 1, ")": -1}.get(text[index], 0)
            if depth == 0:
                break
            index += 1
        calls.append(text[match.start() : index + 1])
    return calls


# ---------------------------------------------------------------------------
# Generated Mechanical scripts
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGeneratedScripts:
    @pytest.mark.parametrize("builder", SCRIPT_BUILDERS)
    def test_scripts_are_ironpython_compatible_and_ascii(self, builder):
        script = builder({"value": "Lastfall \u00dc \u2713", "chains": [["Model"]]})
        assert_ironpython_compatible(script)
        assert script.isascii()

    @pytest.mark.parametrize("builder", SCRIPT_BUILDERS)
    def test_arguments_cannot_break_out_of_the_script(self, builder):
        hostile = '"); import os; os.remove("x"); ("'
        script = builder({"value": hostile, "source": hostile})
        assert hostile not in script
        assert "import os" not in script

    def test_every_mechanical_side_json_dumps_keeps_non_ascii_text(self):
        # IronPython 2.7 raises for non-ASCII text unless ensure_ascii=False.
        calls = [
            call
            for module in (tools, introspection)
            for text in script_texts(module)
            for call in dumps_calls(text)
        ]
        assert len(calls) >= 15
        offenders = [call for call in calls if "ensure_ascii=False" not in call]
        assert not offenders, offenders

    def test_payload_round_trips_unicode(self):
        args = {"value": "Pr\u00fcfung \u2713", "object_id": 7}
        assert json.loads(base64.b64decode(introspection._encode(args))) == args


# ---------------------------------------------------------------------------
# API name extraction
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestExtractApiChains:
    def parts(self, script):
        chains, error, _ = introspection.extract_api_chains(script)
        assert error is None
        return [chain["parts"] for chain in chains]

    def test_collects_chains_rooted_in_session_names(self):
        assert self.parts("Model.Mesh.ElementSize = Quantity('1 [mm]')") == [
            ["Model", "Mesh", "ElementSize"],
            ["Quantity"],
        ]

    def test_calls_and_subscripts_end_a_chain(self):
        assert self.parts("x = Model.Analyses[0].Solution\ny = Model.AddForce().Name") == [
            ["Model", "Analyses"],
            ["Model", "AddForce"],
        ]

    def test_names_defined_by_the_script_are_skipped(self):
        script = (
            "import os\nfrom json import dumps as d\nmesh = 1\n"
            "def f(a, *b, **c):\n    return a.X + b.Y + c.Z\n"
            "for i in range(2):\n    pass\n"
            "with open('f') as h:\n    pass\n"
            "try:\n    pass\nexcept Exception as e:\n    e.args\n"
            "q = [k.V for k in []]\ng = lambda w: w.T\n"
            "class C:\n    pass\n"
            "os.path.join(mesh.Q, d, C, h)\n"
        )
        assert self.parts(script) == [["range"], ["open"], ["Exception"]]

    def test_python2_statements_are_not_names(self):
        assert self.parts("print('a')\nexec('b')") == []

    def test_reports_line_and_column_and_deduplicates(self):
        chains, _, _ = introspection.extract_api_chains("a = 1\nb = Model.Mesh\nc = Model.Mesh")
        assert chains == [{"parts": ["Model", "Mesh"], "line": 2, "column": 5}]

    def test_star_import_is_reported(self):
        _, _, star = introspection.extract_api_chains("from os.path import *")
        assert star

    def test_python3_syntax_error_returns_no_chains(self):
        chains, error, _ = introspection.extract_api_chains("print 'hello'")
        assert chains == []
        assert error["line"] == 1

    def test_number_of_checked_chains_is_capped(self):
        limit = introspection.MAX_CHECKED_CHAINS
        ctx, mechanical = connected(
            {"success": True, "engine_syntax": {"valid": True}, "resolutions": []}
        )
        exact = "\n".join(f"x = Model.A{i}" for i in range(limit))
        result = json.loads(tools.check_script(ctx, script=exact))
        assert "note" not in result["api_check"]
        result = json.loads(tools.check_script(ctx, script=exact + "\ny = Model.B"))
        assert len(sent_payload(mechanical)["chains"]) == limit
        assert str(limit) in result["api_check"]["note"]


@pytest.mark.unit
def test_close_matches_prefers_case_insensitive_match():
    assert introspection.close_matches("force", ["Force", "Forces", "Torque"])[0] == "Force"
    assert introspection.close_matches("NumberOfStep", ["NumberOfSteps", "Name"]) == [
        "NumberOfSteps"
    ]
    assert introspection.close_matches("xyz", ["Force"]) == []


# ---------------------------------------------------------------------------
# Preview tokens
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestPreviewTokens:
    def test_token_is_single_use(self):
        store, session = {}, object()
        token = introspection.store_preview(store, session, 5, "Name", "a", "fp")
        assert introspection.take_preview(store, token, session, 5, "Name", "a")["fingerprint"]
        with pytest.raises(StalePreviewError):
            introspection.take_preview(store, token, session, 5, "Name", "a")

    def test_expired_token_is_rejected(self, monkeypatch):
        store, session = {}, object()
        token = introspection.store_preview(store, session, 5, "Name", "a", "fp")
        now = introspection.time.monotonic() + introspection.PREVIEW_TTL_SECONDS + 1
        monkeypatch.setattr(introspection.time, "monotonic", lambda: now)
        with pytest.raises(StalePreviewError, match="expired"):
            introspection.take_preview(store, token, session, 5, "Name", "a")

    def test_token_from_another_session_is_rejected(self):
        store = {}
        token = introspection.store_preview(store, object(), 5, "Name", "a", "fp")
        with pytest.raises(StalePreviewError, match="different Mechanical session"):
            introspection.take_preview(store, token, object(), 5, "Name", "a")

    @pytest.mark.parametrize(
        ("object_id", "name", "value"), [(6, "Name", "a"), (5, "Other", "a"), (5, "Name", "b")]
    )
    def test_token_for_another_change_is_rejected(self, object_id, name, value):
        store, session = {}, object()
        token = introspection.store_preview(store, session, 5, "Name", "a", "fp")
        with pytest.raises(InvalidArgumentsError):
            introspection.take_preview(store, token, session, object_id, name, value)

    def test_boolean_and_integer_values_are_different_changes(self):
        store, session = {}, object()
        token = introspection.store_preview(store, session, 5, "Flag", True, "fp")
        with pytest.raises(InvalidArgumentsError):
            introspection.take_preview(store, token, session, 5, "Flag", 1)

    def test_store_is_bounded(self):
        store, session = {}, object()
        tokens = [
            introspection.store_preview(store, session, i, "Name", "a", "fp")
            for i in range(introspection.MAX_PENDING_PREVIEWS + 3)
        ]
        assert len(store) == introspection.MAX_PENDING_PREVIEWS
        assert tokens[0] not in store
        assert tokens[-1] in store


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
NEW_TOOLS = [
    (tools.find_objects, {}),
    (tools.describe_object, {"object_id": 1}),
    (tools.preview_property_change, {"object_id": 1, "property_name": "Name", "value": "a"}),
    (
        tools.apply_property_change,
        {"object_id": 1, "property_name": "Name", "value": "a", "preview_token": "t"},
    ),
    (tools.check_script, {"script": "x = 1"}),
]


@pytest.mark.unit
class TestToolErrors:
    @pytest.mark.parametrize(("tool", "kwargs"), NEW_TOOLS)
    def test_fail_explicitly_when_disconnected(self, tool, kwargs):
        result = json.loads(tool(make_context(None), **kwargs))
        assert result["success"] is False
        assert result["error_code"] == "not_connected"

    @pytest.mark.parametrize(("tool", "kwargs"), NEW_TOOLS)
    def test_mechanical_failure_is_an_upstream_error(self, tool, kwargs):
        ctx, mechanical = connected("{}")
        mechanical.run_python_script.side_effect = RuntimeError("rpc failed")
        if tool is tools.apply_property_change:
            store = ctx.request_context.lifespan_context.change_previews
            kwargs = {
                **kwargs,
                "preview_token": introspection.store_preview(
                    store, mechanical, 1, "Name", "a", "fp"
                ),
            }
        result = json.loads(tool(ctx, **kwargs))
        assert result["error_code"] == "upstream_error"
        assert "rpc failed" in result["error"]

    @pytest.mark.parametrize("response", ["not json", "[1, 2]", ""])
    def test_unexpected_response_is_an_upstream_error(self, response):
        ctx, _ = connected(response)
        result = json.loads(tools.find_objects(ctx))
        assert result["error_code"] == "upstream_error"

    @pytest.mark.parametrize(
        ("kwargs", "message"), [({"limit": 0}, "limit"), ({"max_depth": -1}, "max_depth")]
    )
    def test_find_objects_validates_arguments(self, kwargs, message):
        ctx, mechanical = connected("{}")
        result = json.loads(tools.find_objects(ctx, **kwargs))
        assert result["error_code"] == "invalid_arguments"
        assert message in result["error"]
        mechanical.run_python_script.assert_not_called()


@pytest.mark.unit
class TestFindAndDescribe:
    def test_find_objects_sends_arguments(self):
        ctx, mechanical = connected({"success": True, "objects": []})
        tools.find_objects(ctx, name_contains="Kraft \u00fc", category="Force", limit=5)
        assert sent_payload(mechanical) == {
            "name_contains": "Kraft \u00fc",
            "category": "Force",
            "parent_id": None,
            "max_depth": None,
            "limit": 5,
        }

    def test_unknown_category_returns_suggestions_only(self):
        ctx, _ = connected(
            {
                "success": False,
                "error_code": "invalid_arguments",
                "error": "Unknown object category Forc.",
                "details": {"candidates": ["Force", "FixedSupport", "Pressure"]},
            }
        )
        result = json.loads(tools.find_objects(ctx, category="Forc"))
        assert result["details"] == {"suggestions": ["Force"]}

    def test_describe_object_returns_mechanical_payload(self):
        payload = {"success": True, "object": {"object_id": 3}, "properties": []}
        ctx, mechanical = connected(payload)
        assert json.loads(tools.describe_object(ctx, 3, details_only=False)) == payload
        assert sent_payload(mechanical) == {
            "object_id": 3,
            "details_only": False,
            "name_contains": None,
            "include_methods": False,
        }


@pytest.mark.unit
class TestPropertyChangeTools:
    PREVIEW = {
        "success": True,
        "target": {"object_id": 3, "property": "NumberOfSteps"},
        "current_value": 1,
        "proposed_value": 3,
        "validation": {"valid": True, "errors": [], "warnings": []},
        "no_change": False,
        "fingerprint": '["int", 1]',
    }

    def test_valid_preview_issues_a_token_and_hides_the_fingerprint(self):
        ctx, mechanical = connected(self.PREVIEW)
        result = json.loads(tools.preview_property_change(ctx, 3, "NumberOfSteps", 3))
        assert "fingerprint" not in result
        assert result["expires_in_seconds"] == introspection.PREVIEW_TTL_SECONDS
        assert "Nothing was changed" in result["note"]
        store = ctx.request_context.lifespan_context.change_previews
        assert store[result["preview_token"]]["fingerprint"] == '["int", 1]'
        assert sent_payload(mechanical) == {
            "object_id": 3,
            "property_name": "NumberOfSteps",
            "value": 3,
        }

    def test_invalid_preview_issues_no_token(self):
        invalid = {**self.PREVIEW, "validation": {"valid": False, "errors": ["bad"]}}
        ctx, _ = connected(invalid)
        result = json.loads(tools.preview_property_change(ctx, 3, "NumberOfSteps", -1))
        assert "preview_token" not in result
        assert ctx.request_context.lifespan_context.change_previews == {}

    def test_unknown_property_returns_suggestions(self):
        ctx, _ = connected(
            {
                "success": False,
                "error_code": "invalid_arguments",
                "error": "Object 3 has no API property NumberOfStep.",
                "details": {"candidates": ["NumberOfSteps", "Name"]},
            }
        )
        result = json.loads(tools.preview_property_change(ctx, 3, "NumberOfStep", 3))
        assert result["details"]["suggestions"] == ["NumberOfSteps"]

    def test_apply_sends_the_previewed_fingerprint(self):
        ctx, mechanical = connected(self.PREVIEW)
        token = json.loads(tools.preview_property_change(ctx, 3, "NumberOfSteps", 3))[
            "preview_token"
        ]
        mechanical.run_python_script.return_value = json.dumps({"success": True, "value": 3})
        result = json.loads(tools.apply_property_change(ctx, 3, "NumberOfSteps", 3, token))
        assert result == {"success": True, "value": 3}
        assert sent_payload(mechanical)["fingerprint"] == '["int", 1]'

    def test_apply_without_valid_token_does_not_touch_mechanical(self):
        ctx, mechanical = connected("{}")
        result = json.loads(tools.apply_property_change(ctx, 3, "NumberOfSteps", 3, "unknown"))
        assert result["error_code"] == "stale_preview"
        mechanical.run_python_script.assert_not_called()

    def test_apply_with_other_value_does_not_touch_mechanical(self):
        ctx, mechanical = connected(self.PREVIEW)
        token = json.loads(tools.preview_property_change(ctx, 3, "NumberOfSteps", 3))[
            "preview_token"
        ]
        mechanical.run_python_script.reset_mock()
        result = json.loads(tools.apply_property_change(ctx, 3, "NumberOfSteps", 4, token))
        assert result["error_code"] == "invalid_arguments"
        mechanical.run_python_script.assert_not_called()


@pytest.mark.unit
class TestCheckScript:
    def check(self, script, resolutions, engine_syntax=None, **kwargs):
        ctx, mechanical = connected(
            {
                "success": True,
                "engine_syntax": engine_syntax or {"valid": True},
                "resolutions": resolutions,
                "product_version": "2026 R1",
                "python_engine": "IronPython 2.7.4",
            }
        )
        result = json.loads(tools.check_script(ctx, script=script, **kwargs))
        return result, mechanical

    def test_valid_script(self):
        result, mechanical = self.check("x = Model.Mesh", [{"status": "ok"}])
        assert result["valid"] is True
        assert result["executed"] is False
        assert result["api_check"] == {
            "performed": True,
            "checked_count": 1,
            "problems": [],
            "unverified": [],
        }
        assert sent_payload(mechanical) == {
            "source": "x = Model.Mesh",
            "chains": [["Model", "Mesh"]],
        }

    def test_missing_member_is_an_error_with_suggestions(self):
        result, _ = self.check(
            "s = Model.Mesh.GetMeshStatistics()",
            [{"status": "missing", "index": 2, "candidates": ["GenerateMesh", "GetMeshStatus"]}],
        )
        assert result["valid"] is False
        assert result["api_check"]["problems"] == [
            {
                "line": 1,
                "column": 5,
                "severity": "error",
                "chain": "Model.Mesh.GetMeshStatistics",
                "message": "'Model.Mesh' has no member 'GetMeshStatistics'.",
                "suggestions": ["GetMeshStatus"],
            }
        ]

    def test_undefined_name_is_an_error(self):
        result, _ = self.check("a = MissingModel.Mesh", [{"status": "undefined", "index": 0}])
        assert result["valid"] is False
        assert result["api_check"]["problems"][0]["chain"] == "MissingModel"

    def test_undefined_name_is_a_warning_after_star_import(self):
        result, _ = self.check(
            "from os.path import *\nz = joinx('a')", [{"status": "undefined", "index": 0}]
        )
        assert result["valid"] is True
        assert result["api_check"]["problems"][0]["severity"] == "warning"

    def test_unverified_chain_is_reported_without_failing(self):
        result, _ = self.check(
            "x = Model.NamedSelections.Children",
            [{"status": "unverified", "index": 1, "reason": "value is None"}],
        )
        assert result["valid"] is True
        assert result["api_check"]["unverified"] == [
            {"line": 1, "column": 5, "chain": "Model.NamedSelections", "reason": "value is None"}
        ]

    def test_engine_only_syntax_error_is_explained(self):
        result, _ = self.check(
            "y = f'{1}'", [], engine_syntax={"valid": False, "message": "invalid syntax"}
        )
        assert result["valid"] is False
        assert result["python3_syntax"] == {"valid": True}
        assert "IronPython 2.7.4" in result["engine_syntax"]["note"]

    def test_python2_script_skips_the_api_check(self):
        result, mechanical = self.check("print 'hello'", [])
        assert result["valid"] is True
        assert result["python3_syntax"]["valid"] is False
        assert result["api_check"]["performed"] is False
        assert sent_payload(mechanical)["chains"] == []

    def test_reads_script_from_file(self, tmp_path):
        path = tmp_path / "script.py"
        path.write_text("x = Model", encoding="utf-8")
        result, mechanical = self.check(None, [{"status": "ok"}], file_path=str(path))
        assert result["valid"] is True
        assert sent_payload(mechanical)["source"] == "x = Model"

    def test_missing_file_is_invalid_arguments(self, tmp_path):
        ctx, mechanical = connected("{}")
        result = json.loads(tools.check_script(ctx, file_path=str(tmp_path / "missing.py")))
        assert result["error_code"] == "invalid_arguments"
        mechanical.run_python_script.assert_not_called()

    def test_only_python_files_are_read(self, tmp_path):
        secret = tmp_path / "secrets.env"
        secret.write_text("TOKEN=abc", encoding="utf-8")
        ctx, mechanical = connected("{}")
        result = json.loads(tools.check_script(ctx, file_path=str(secret)))
        assert result["error_code"] == "invalid_arguments"
        mechanical.run_python_script.assert_not_called()

    def test_requires_a_script(self):
        ctx, _ = connected("{}")
        assert json.loads(tools.check_script(ctx))["error_code"] == "invalid_arguments"


# ---------------------------------------------------------------------------
# Fixes to existing tools found while validating these tools
# ---------------------------------------------------------------------------
def _child(name, category):
    return SimpleNamespace(Name=name, DataModelObjectCategory=category)


@pytest.mark.unit
def test_model_info_does_not_list_analysis_settings_as_boundary_conditions():
    mechanical = MagicMock()
    mechanical.run_python_script.return_value = "{}"
    tools.get_model_info(make_context(mechanical))
    script = mechanical.run_python_script.call_args.args[0]

    analysis = SimpleNamespace(
        Name="Static Structural",
        AnalysisType="Static",
        Solution=SimpleNamespace(Status="SolveRequired"),
        Children=Items(
            [
                _child("Analysis Settings", "ANSYSAnalysisSettings"),
                _child("Lastfall \u00dc", "Force"),
                _child("Solution", "Solution"),
            ]
        ),
    )
    namespace = {
        "ExtAPI": SimpleNamespace(
            DataModel=SimpleNamespace(Project=SimpleNamespace(ProductVersion="2026 R1", Name="P")),
            Application=SimpleNamespace(ActiveUnitSystem="StandardMKS"),
        ),
        "Model": SimpleNamespace(
            Name="Model",
            Geometry=None,
            Mesh=None,
            Analyses=Items([analysis]),
            NamedSelections=None,
            Materials=SimpleNamespace(Children=Items([])),
        ),
        "DataModelObjectCategory": SimpleNamespace(Body="Body"),
    }
    info = json.loads(run_mechanical_script(script, namespace))
    assert info["boundary_conditions"] == [
        {"analysis_index": 0, "name": "Lastfall \u00dc", "type": "Force"}
    ]


@pytest.mark.unit
def test_mechanical_messages_keep_non_ascii_text():
    mechanical = MagicMock()
    message = SimpleNamespace(Severity="Warning", Source="Solver", Summary="Pr\u00fcfung \u2713")
    namespace = {"ExtAPI": SimpleNamespace(Application=SimpleNamespace(Messages=Items([message])))}
    mechanical.run_python_script.side_effect = lambda script: run_mechanical_script(
        script, dict(namespace)
    )
    result = json.loads(tools.get_mechanical_logs(make_context(mechanical), source="messages"))
    assert result["logs"] == "[Warning] Solver: Pr\u00fcfung \u2713"
