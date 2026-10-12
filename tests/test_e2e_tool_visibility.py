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

These two tests use FastMCP's in-memory ``Client`` to exercise the real MCP
protocol surface (``tools/list``, ``tools/call``) against the actual
registered ``app``, as a regression safety net on top of the (faster) unit
tests in ``test_cli.py`` (launcher disable-logic), ``test_tools.py``
(per-tool ``enable_components``/``disable_components`` calls), and
``test_prompts.py`` (prompt selection) — all of which mock the relevant
calls rather than exercising FastMCP's actual visibility engine end-to-end.

Mechanical connections are mocked at the ``ansys.mechanical.core`` boundary
only; everything else (tool registration, visibility transforms, the MCP
protocol layer) is real.
"""

from unittest.mock import MagicMock, patch

from fastmcp import Client
import pytest

# Ensure tools/prompts/contexts/toolsets are registered (mirrors launcher() imports).
from ansys.mechanical.mcp import contexts, prompts, tools, toolsets  # noqa: F401
from ansys.mechanical.mcp.server import app
from ansys.mechanical.mcp.tools import REQUIRES_MECHANICAL_TAG


@pytest.fixture(autouse=True)
def _isolated_app_state():
    """Give each test a known-clean, isolated global ``app`` state.

    ``app`` is a module-level singleton shared by the whole test session.
    ``app.disable``/``app.enable`` (global visibility) and ``app._cli_config``
    (read by the real lifespan on ``Client`` connect) are both mutated by
    other test modules that call ``launcher()`` (e.g. ``test_cli.py``'s
    ``--connect-on-startup`` tests). Without resetting both here, a leaked
    ``connect_on_startup=True`` can make the real (unmocked) lifespan attempt
    a genuine Mechanical connection during these tests.
    """
    app.enable(tags={REQUIRES_MECHANICAL_TAG})
    setattr(app, "_cli_config", {"connect_on_startup": False, "static_tools": False})
    yield
    app.enable(tags={REQUIRES_MECHANICAL_TAG})
    setattr(app, "_cli_config", {"connect_on_startup": False, "static_tools": False})


def _make_mock_mechanical():
    mechanical = MagicMock()
    mechanical.version = "2024 R2"
    mechanical.project_directory = "/tmp/mechanical_project"
    mechanical.list_files = MagicMock(return_value=["a.mechdb"])
    mechanical.exit = MagicMock()
    return mechanical


@pytest.mark.asyncio
async def test_dynamic_mode_hides_tools_by_default():
    """Default (dynamic) mode: Mechanical-only tools are hidden until connected.

    Note: this only checks the initial ``tools/list`` snapshot. Visibility after
    launch, connect, and disconnect is covered by the protocol-level tests below.
    """
    # Simulate what launcher() does by default (--static-tools NOT passed).
    app.disable(tags={REQUIRES_MECHANICAL_TAG})

    mock_mechanical = _make_mock_mechanical()

    async with Client(app) as client:
        tool_names = {t.name for t in await client.list_tools()}
        assert "check_mechanical_status" in tool_names
        assert "launch_mechanical" in tool_names
        assert "run_python_script" not in tool_names
        assert "list_files" not in tool_names

        # The tool call itself must still work normally (only visibility differs).
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            result = await client.call_tool("launch_mechanical", {})
            assert "Successfully launched Mechanical" in result.data


@pytest.mark.asyncio
async def test_static_mode_exposes_all_tools_and_degrades_gracefully_before_connect():
    """--static-tools mode: all tools visible immediately.

    Pre-connect calls return a clean message instead of crashing, and the
    tool works normally once connected.
    """
    # Do NOT call app.disable — this simulates --static-tools being passed.
    mock_mechanical = _make_mock_mechanical()

    async with Client(app) as client:
        tool_names = {t.name for t in await client.list_tools()}
        # The key difference vs. dynamic mode: these are visible immediately.
        assert "run_python_script" in tool_names
        assert "list_files" in tool_names

        # Calling a Mechanical-only tool before connecting must not crash.
        result = await client.call_tool("list_files", {})
        assert "No Mechanical connection available" in result.data
        assert "connect_to_mechanical" in result.data

        # Once connected, the tool works normally (not just "visible").
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            await client.call_tool("launch_mechanical", {})

        result_after_connect = await client.call_tool("list_files", {})
        assert "a.mechdb" in result_after_connect.data


async def _tool_names(client):
    return {t.name for t in await client.list_tools()}


@pytest.mark.asyncio
async def test_dynamic_mode_reveals_tools_after_launch_and_hides_after_disconnect():
    """Connection tools must appear on later requests, not only within the launch call."""
    app.disable(tags={REQUIRES_MECHANICAL_TAG})
    mock_mechanical = _make_mock_mechanical()

    async with Client(app) as client:
        assert "screenshot" not in await _tool_names(client)

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            await client.call_tool("launch_mechanical", {"batch": True})

        names = await _tool_names(client)
        assert {"screenshot", "run_python_script", "disconnect_from_mechanical"} <= names
        assert "a.mechdb" in (await client.call_tool("list_files", {})).data

        await client.call_tool("disconnect_from_mechanical", {})
        mock_mechanical.exit.assert_called_once()
        names = await _tool_names(client)
        assert "screenshot" not in names
        assert "launch_mechanical" in names


@pytest.mark.asyncio
async def test_dynamic_mode_reveals_tools_after_connect():
    app.disable(tags={REQUIRES_MECHANICAL_TAG})
    mock_mechanical = _make_mock_mechanical()

    async with Client(app) as client:
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ):
            await client.call_tool("connect_to_mechanical", {"port": 10000})
        assert "screenshot" in await _tool_names(client)

        await client.call_tool("disconnect_from_mechanical", {})
        # An attached instance is released, not shut down.
        mock_mechanical.exit.assert_not_called()
        assert "screenshot" not in await _tool_names(client)


@pytest.mark.asyncio
async def test_static_mode_keeps_tools_visible_after_disconnect():
    setattr(app, "_cli_config", {"connect_on_startup": False, "static_tools": True})
    mock_mechanical = _make_mock_mechanical()

    async with Client(app) as client:
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            await client.call_tool("launch_mechanical", {"batch": True})
        await client.call_tool("disconnect_from_mechanical", {})
        assert "screenshot" in await _tool_names(client)
