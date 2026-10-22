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

"""Integration tests for PyMechanical MCP Server.

These tests require a running Mechanical instance and are marked as 'integration'.
Run with: pytest -m integration

To skip integration tests, run: pytest -m "not integration"
"""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from ansys.mechanical.mcp.server import PyMechanicalAppContext
from ansys.mechanical.mcp.tools import (
    check_mechanical_status,
    run_python_script,
)

ON_CI = os.getenv("ON_CI", "false").lower() == "true"
ON_LOCAL = os.getenv("ON_LOCAL", "false" if ON_CI else "true").lower() == "true"


def _get_real_mechanical_connection():
    """Create a real Mechanical connection for integration tests.

    Returns
    -------
    tuple
        (mechanical, externally_managed) where externally_managed is True when
        connected to a pre-started gRPC server and False when launched locally.
    """
    from ansys.mechanical.core import connect_to_mechanical, launch_mechanical

    start_instance = os.getenv("PYMECHANICAL_START_INSTANCE", "true").lower() == "true"

    if start_instance:
        # Local launch mode (developer machine with Mechanical installed)
        launch_kwargs = {"cleanup_on_exit": False, "loglevel": "ERROR"}
        transport_mode = os.getenv("PYMECHANICAL_TRANSPORT_MODE")
        if transport_mode:
            launch_kwargs["transport_mode"] = transport_mode
        return launch_mechanical(**launch_kwargs), False

    # CI/remote mode: connect to an already running gRPC server
    ip = os.getenv("PYMECHANICAL_IP", "127.0.0.1")
    port = int(os.getenv("PYMECHANICAL_PORT", "10000"))
    transport_mode = os.getenv("PYMECHANICAL_TRANSPORT_MODE")

    kwargs = {"ip": ip, "port": port, "cleanup_on_exit": False}
    if transport_mode:
        kwargs["transport_mode"] = transport_mode

    return connect_to_mechanical(**kwargs), True


@pytest.fixture
def real_context(mock_mechanical):
    """Module-level context fixture using a mock Mechanical for persistent session tests."""
    context = MagicMock()
    context.request_context = MagicMock()
    # Attach a python_session mock with metadata dict to simulate persistent session
    py_session = MagicMock()
    py_session.metadata = {}
    lc = PyMechanicalAppContext(mechanical=mock_mechanical)
    lc.python_session = py_session
    context.request_context.lifespan_context = lc
    return context


@pytest.fixture(scope="class")
def real_mechanical():
    """Connect to a real Mechanical instance for integration tests.

    This requires Mechanical to be running on localhost:10000.
    Skip these tests if Mechanical is not available locally.
    """
    try:
        mechanical, externally_managed = _get_real_mechanical_connection()

        yield mechanical

        # Only terminate when this test launched the process locally.
        if not externally_managed:
            mechanical.exit()

    except Exception as e:
        # Fail hard in CI, skip locally when Mechanical is unavailable.
        if ON_CI:
            raise e
        else:
            pytest.skip(f"Mechanical not available: {e}")


@pytest.mark.integration
@pytest.mark.slow
class TestMechanicalIntegration:
    """Integration tests that require a real Mechanical connection.

    This class combines all basic Mechanical integration tests to share a single
    Mechanical instance, reducing test execution time.
    """

    @pytest.fixture()
    def mechanical(self, real_mechanical):
        real_mechanical.clear()
        return real_mechanical

    @pytest.fixture
    def real_context(self, real_mechanical):
        """Create a real context with actual Mechanical connection."""
        from unittest.mock import MagicMock

        from ansys.mechanical.mcp.server import PyMechanicalAppContext

        context = MagicMock()
        context.request_context = MagicMock()
        context.request_context.lifespan_context = PyMechanicalAppContext(
            mechanical=real_mechanical
        )

        return context

    def test_real_check_mechanical_status(self, real_context):
        """Test checking Mechanical status with a real connection."""
        import json

        result = check_mechanical_status(real_context)

        assert isinstance(result, str)
        # Check for JSON structure
        data = json.loads(result)
        assert "connection" in data
        assert "version" in data["connection"]

    def test_real_run_script(self, real_context):
        """Test running a Mechanical script with a real connection."""
        # Use a safe script that doesn't affect the model
        script = "print('Hello from Mechanical')"
        result = run_python_script(real_context, script)

        assert isinstance(result, str)
        assert "Script executed successfully" in result


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not ON_LOCAL, reason="Only run on local environments")
class TestLaunchMechanicalIntegration:
    """Integration tests for launch_mechanical tool.

    Consolidated to minimize expensive launch_mechanical calls.
    Other test cases are covered by unit tests in test_tools.py.
    """

    @pytest.fixture
    def clean_context(self):
        """Create a clean context with no Mechanical connection."""
        from ansys.mechanical.mcp.server import PyMechanicalAppContext

        context = MagicMock()
        context.send_notification = AsyncMock(return_value=None)
        context.request_context = MagicMock()
        context.request_context.lifespan_context = PyMechanicalAppContext(mechanical=None)

        return context

    @pytest.mark.asyncio
    async def test_launch_mechanical_basic_workflow(self, clean_context):
        """Test launching Mechanical with default parameters and executing scripts.

        This test combines multiple scenarios:
        - Launch with default parameters
        - Verify connection info
        - Execute scripts
        - Check status
        """
        from ansys.mechanical.mcp.tools import (
            check_mechanical_status,
            disconnect_from_mechanical,
            launch_mechanical,
            run_python_script,
        )

        try:
            # Launch Mechanical
            result = await launch_mechanical(clean_context)

            # Verify successful launch
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result
            assert "Version:" in result

            # Verify Mechanical was stored in context
            assert clean_context.request_context.lifespan_context.mechanical is not None

            mechanical = clean_context.request_context.lifespan_context.mechanical
            assert mechanical.is_alive is True
            assert mechanical.version is not None

            # Execute a simple script
            script_result = run_python_script(clean_context, "print('test')")
            assert "Script executed successfully" in script_result

            # Check status
            status_result = check_mechanical_status(clean_context)
            import json

            status_data = json.loads(status_result)
            assert "connection" in status_data
            assert "version" in status_data["connection"]

            # Test launching when already connected
            result2 = await launch_mechanical(clean_context)
            assert "Already connected to a Mechanical instance" in result2
            assert "disconnect first" in result2.lower()

        finally:
            # Clean up
            await disconnect_from_mechanical(clean_context)

    @pytest.mark.asyncio
    async def test_launch_mechanical_custom_parameters(self, clean_context):
        """Test launching Mechanical with custom parameters.

        This test combines:
        - Custom port
        - Custom version
        """

        from ansys.mechanical.mcp.tools import (
            disconnect_from_mechanical,
            launch_mechanical,
        )

        try:
            result = await launch_mechanical(clean_context, port=10050)

            # Verify successful launch
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result

            # Verify Mechanical instance was created
            mechanical = clean_context.request_context.lifespan_context.mechanical
            assert mechanical is not None
            assert mechanical.is_alive is True

        finally:
            # Disconnect Mechanical
            await disconnect_from_mechanical(clean_context)


@pytest.mark.integration
@pytest.mark.slow
class TestPythonPersistentSessionIntegration:
    """Integration tests for connecting to Mechanical in persistent Python session."""

    @pytest.fixture
    def persistent_real_context(self, real_mechanical):
        """Context wired with REAL Mechanical and a mocked persistent session."""
        ctx = MagicMock()
        ctx.request_context = MagicMock()
        lc = PyMechanicalAppContext(mechanical=real_mechanical)
        py_session = MagicMock()
        py_session.metadata = {}
        lc.python_session = py_session
        ctx.request_context.lifespan_context = lc
        return ctx

    async def test_run_python_code_executes_simple(self, persistent_real_context, capsys):
        """Light-weight execution test using mocked python_session near integration suite."""
        import json
        from unittest.mock import MagicMock

        from ansys.mechanical.mcp.tools import run_python_code

        # Attach a mocked persistent python session to the real_context lifespan
        session = MagicMock()
        session.metadata = {
            "mechanical": persistent_real_context.request_context.lifespan_context.mechanical
        }
        # Simulate a normal dict-shaped execution result
        session.execute.return_value = {
            "success": True,
            "stdout": "hello\n",
            "stderr": "",
        }
        persistent_real_context.request_context.lifespan_context.python_session = session

        with capsys.disabled():
            result = await run_python_code(persistent_real_context, code="print('hello')")
        data = json.loads(result)
        assert data["success"] is True
        assert data["stdout"].strip() == "hello"


@pytest.mark.integration
@pytest.mark.slow
class TestObjectDiscoveryIntegration:
    """Object discovery, property change previews, and script checks on a live session."""

    @pytest.fixture
    def context(self, real_mechanical):
        real_mechanical.clear()
        real_mechanical.run_python_script(
            "analysis = Model.AddStaticStructuralAnalysis()\nanalysis.AddForce()\nNone"
        )
        ctx = MagicMock()
        ctx.request_context.lifespan_context = PyMechanicalAppContext(mechanical=real_mechanical)
        return ctx

    @staticmethod
    def _id(ctx, category):
        import json

        from ansys.mechanical.mcp.tools import find_objects

        return json.loads(find_objects(ctx, category=category))["objects"][0]["object_id"]

    def test_find_and_describe(self, context):
        import json

        from ansys.mechanical.mcp.tools import describe_api, find_objects

        found = json.loads(find_objects(context, category="force"))
        assert found["match_count"] == 1
        assert found["python_engine"]
        settings = json.loads(
            describe_api(context, object_id=self._id(context, "ANSYSAnalysisSettings"))
        )
        properties = {p["name"]: p for p in settings["properties"]}
        assert "Direct" in properties["SolverType"]["enum_values"]
        assert properties["NumberOfSteps"]["editable"] is True
        search = json.loads(describe_api(context, query="large deflection"))
        assert search["matches"][0]["name"] == "ANSYSAnalysisSettings.LargeDeflection"

    def test_installed_api_documentation(self, context):
        import json

        from ansys.mechanical.mcp.tools import describe_api

        result = json.loads(describe_api(context, query="Analysis.Solve"))
        assert result["success"] is True
        match = next(item for item in result["matches"] if item["name"] == "Analysis.Solve")
        documentation = match["documentation"]
        assert documentation["source_kind"] == "installed_xml"
        assert documentation["status"] in {
            "available",
            "missing",
            "unavailable",
            "no_descriptive_text",
        }
        if documentation["status"] == "available":
            assert documentation["source"].endswith(".xml")
            assert documentation["entries"]
            assert all(entry["member_id"].startswith("M:") for entry in documentation["entries"])
        assert "Solve(" in match["signature"]

    def test_large_model_summary_and_paging(self, real_mechanical, context):
        import json

        from ansys.mechanical.mcp.tools import find_objects, get_model_info

        for start in range(0, 1005, 50):
            real_mechanical.run_python_script(
                "with Tree.Suspend():\n"
                "    with Transaction():\n"
                "        for index in range(%d, %d):\n"
                "            selection = Model.AddNamedSelection()\n"
                "            selection.Name = 'Paging %%04d' %% index\n"
                "None" % (start, min(start + 50, 1005))
            )
        summary = json.loads(get_model_info(context))
        assert len(summary["named_selections"]) == 50
        assert summary["collection_info"]["named_selections"] == {
            "total_count": 1005,
            "returned_count": 50,
            "truncated": True,
            "find_objects": {"category": "NamedSelection"},
        }
        assert len(json.loads(get_model_info(context, max_items=None))["named_selections"]) == 1005
        assert json.loads(get_model_info(context, max_items=0))["named_selections"] == []
        offset, object_ids, fingerprints = 0, [], set()
        while True:
            page = json.loads(
                find_objects(context, category="NamedSelection", limit=500, offset=offset)
            )
            object_ids.extend(item["object_id"] for item in page["objects"])
            fingerprints.add(page["result_fingerprint"])
            if page["next_offset"] is None:
                break
            assert page["next_offset"] > offset
            offset = page["next_offset"]
        assert len(object_ids) == len(set(object_ids)) == 1005
        assert len(fingerprints) == 1
        real_mechanical.run_python_script(
            "DataModel.GetObjectById(%d).Name = u'Renamed \\u00dc'\nNone" % object_ids[-1]
        )
        changed = json.loads(find_objects(context, category="NamedSelection", limit=1))
        assert changed["match_count"] == 1005
        assert changed["result_fingerprint"] not in fingerprints

    def test_preview_apply_and_stale_preview(self, real_mechanical, context):
        import json

        from ansys.mechanical.mcp.tools import apply_property_change, preview_property_change

        mesh_id = self._id(context, "Mesh")
        bad = json.loads(preview_property_change(context, mesh_id, "ElementSize", "2 [N]"))
        assert bad["validation"]["valid"] is False

        preview = json.loads(preview_property_change(context, mesh_id, "ElementSize", "2 [mm]"))
        assert real_mechanical.run_python_script("str(Model.Mesh.ElementSize)") == "0 [m]"
        applied = json.loads(
            apply_property_change(
                context, mesh_id, "ElementSize", "2 [mm]", preview["preview_token"]
            )
        )
        assert applied["readback_matches"] is True

        force_id = self._id(context, "Force")
        name = "Lastfall \u00dc"
        stale = json.loads(preview_property_change(context, force_id, "Name", name))
        real_mechanical.run_python_script("Model.Analyses[0].Children[1].Name = 'Changed'")
        rejected = json.loads(
            apply_property_change(context, force_id, "Name", name, stale["preview_token"])
        )
        assert rejected["error_code"] == "stale_preview"
        assert real_mechanical.run_python_script("Model.Analyses[0].Children[1].Name") == "Changed"

    def test_check_script_does_not_run_the_script(self, real_mechanical, context):
        import json

        from ansys.mechanical.mcp.tools import check_script

        result = json.loads(
            check_script(context, script="Model.AddModalAnalysis()\nModel.Mesh.GetMeshStatistics()")
        )
        assert result["valid"] is False
        assert result["api_check"]["problems"][0]["chain"] == "Model.Mesh.GetMeshStatistics"
        assert real_mechanical.run_python_script("str(Model.Analyses.Count)") == "1"

        fstring = json.loads(check_script(context, script="x = f'{1}'"))
        if "IronPython" in fstring["python_engine"]:
            assert fstring["engine_syntax"]["valid"] is False
