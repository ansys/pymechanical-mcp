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

"""End-to-end MCP protocol tests for tool visibility modes (dynamic vs. --static-tools).

These tests use FastMCP's in-memory ``Client`` to exercise the real MCP
protocol surface (``tools/list``, ``tools/call``, ``prompts/get``) against the
actual registered ``app``, without needing a real Mechanical installation or a
subprocess transport. Mechanical connections are mocked at the
``ansys.mechanical.core`` boundary only.
"""

from unittest.mock import MagicMock, patch

from fastmcp import Client
import pytest

# Ensure tools/prompts/contexts/toolsets are registered (mirrors launcher() imports).
from ansys.mechanical.mcp import contexts, prompts, tools, toolsets  # noqa: F401
from ansys.mechanical.mcp.server import app
from ansys.mechanical.mcp.tools import REQUIRES_MECHANICAL_TAG


@pytest.fixture(autouse=True)
def _reset_tool_visibility():
    """Ensure REQUIRES_MECHANICAL_TAG is enabled (visible) before/after each test.

    ``app.disable``/``app.enable`` mutate GLOBAL visibility on the shared
    ``app`` singleton (unlike session-scoped ``ctx.enable_components``), so
    tests in this module must restore a clean slate to avoid leaking state
    into other test modules that import the same ``app`` instance.
    """
    app.enable(tags={REQUIRES_MECHANICAL_TAG})
    yield
    app.enable(tags={REQUIRES_MECHANICAL_TAG})


def _make_mock_mechanical():
    mechanical = MagicMock()
    mechanical.version = "2024 R2"
    mechanical.project_directory = "/tmp/mechanical_project"
    mechanical.list_files = MagicMock(return_value=["a.mechdb"])
    mechanical.exit = MagicMock()
    return mechanical


@pytest.mark.asyncio
async def test_dynamic_mode_hides_then_reveals_tools_after_connect():
    """Default (dynamic) mode: Mechanical tools hidden until launch_mechanical succeeds."""
    # Simulate what launcher() does by default (--static-tools NOT passed).
    app.disable(tags={REQUIRES_MECHANICAL_TAG})

    mock_mechanical = _make_mock_mechanical()

    async with Client(app) as client:
        tool_list = await client.list_tools()
        tool_names = {t.name for t in tool_list}

        assert "check_mechanical_status" in tool_names
        assert "launch_mechanical" in tool_names
        assert "run_python_script" not in tool_names
        assert "list_files" not in tool_names
        assert "export_results" not in tool_names

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            result = await client.call_tool("launch_mechanical", {})
            assert "Successfully launched Mechanical" in result.data

        tool_list_after = await client.list_tools()
        tool_names_after = {t.name for t in tool_list_after}
        assert "run_python_script" in tool_names_after
        assert "list_files" in tool_names_after
        assert "export_results" in tool_names_after


@pytest.mark.asyncio
async def test_static_mode_exposes_all_tools_immediately():
    """--static-tools mode: all tools visible from the very first tools/list call."""
    # Do NOT call app.disable — this simulates --static-tools being passed.

    async with Client(app) as client:
        tool_list = await client.list_tools()
        tool_names = {t.name for t in tool_list}

        assert "check_mechanical_status" in tool_names
        assert "launch_mechanical" in tool_names
        # The key difference vs. dynamic mode: these are visible immediately too.
        assert "run_python_script" in tool_names
        assert "list_files" in tool_names
        assert "export_results" in tool_names


@pytest.mark.asyncio
async def test_static_mode_calling_tool_before_connect_returns_clean_message():
    """--static-tools mode: calling a Mechanical tool before connecting must not crash."""
    async with Client(app) as client:
        result = await client.call_tool("list_files", {})
        assert "No Mechanical connection available" in result.data
        assert "connect_to_mechanical" in result.data


@pytest.mark.asyncio
async def test_static_mode_tool_works_normally_after_connect():
    """--static-tools mode: tool works normally once connected (not just "visible")."""
    mock_mechanical = _make_mock_mechanical()

    async with Client(app) as client:
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            await client.call_tool("launch_mechanical", {})

        result = await client.call_tool("list_files", {})
        assert "a.mechdb" in result.data


@pytest.mark.asyncio
async def test_system_prompt_matches_active_mode(monkeypatch):
    """The system_prompt MCP prompt should reflect the active --static-tools setting."""
    from ansys.mechanical.mcp import prompts as prompts_module

    # Dynamic (no _cli_config / static_tools False)
    monkeypatch.setattr(app, "_cli_config", {"static_tools": False}, raising=False)
    async with Client(app) as client:
        result = await client.get_prompt("system_prompt")
        text = result.messages[0].content.text
        assert "uses connection-aware tool visibility" in text

    # Static
    monkeypatch.setattr(app, "_cli_config", {"static_tools": True}, raising=False)
    async with Client(app) as client:
        result = await client.get_prompt("system_prompt")
        text = result.messages[0].content.text
        assert "exposes the full tool surface from startup" in text

    # Sanity: build_system_prompt itself is exercised directly too.
    assert "connection-aware" in prompts_module.build_system_prompt(False)
    assert "full tool surface" in prompts_module.build_system_prompt(True)
