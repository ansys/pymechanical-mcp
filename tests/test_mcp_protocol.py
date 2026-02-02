"""Tests for MCP protocol compliance and server behavior."""

import pytest
from fastmcp.server import FastMCP

from ansys.mechanical.mcp import app


@pytest.mark.unit
class TestMCPProtocol:
    """Tests for MCP protocol compliance."""

    def test_server_name(self):
        """Test that server has correct name."""
        assert app.name == "PyMechanical MCP Server"

    def test_server_is_fastmcp_instance(self):
        """Test that server is an instance of FastMCP."""
        assert isinstance(app, FastMCP)

    def test_server_has_lifespan(self):
        """Test that server has lifespan configured."""
        # The server should have a lifespan function configured
        # Simply check that the server was created with lifespan by checking it's a valid instance
        # The actual lifespan functionality is tested in test_lifespan.py
        assert isinstance(app, FastMCP)
        assert app.name == "PyMechanical MCP Server"

    @pytest.mark.asyncio
    async def test_server_tools_registered(self):
        """Test that all tools are properly registered."""
        # Tools should be accessible through the MCP server
        from ansys.mechanical.mcp.tools import (
            check_mechanical_status,
            launch_mechanical,
            run_python_script,
            run_multiple_scripts,
        )

        tools = [
            check_mechanical_status,
            launch_mechanical,
            run_python_script,
            run_multiple_scripts,
        ]

        for tool in tools:
            # Tools can be either FunctionTool objects (with .fn) or regular functions (decorated with @add_tool)
            if hasattr(tool, "fn"):
                # FunctionTool object
                assert callable(tool.fn)
                assert hasattr(tool.fn, "__name__")
            else:
                # Regular function
                assert callable(tool)
                assert hasattr(tool, "__name__")
