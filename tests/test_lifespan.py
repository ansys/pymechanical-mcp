"""Tests for MCP server lifespan management."""

from unittest.mock import MagicMock

import pytest

from ansys.mechanical.mcp.server import PyMechanicalAppContext, app


@pytest.mark.unit
def test_app_context_dataclass():
    """Test that PyMechanicalAppContext is properly defined as a dataclass."""
    from dataclasses import is_dataclass

    assert is_dataclass(PyMechanicalAppContext)

    # Test creating PyMechanicalAppContext with Mechanical
    mock_mechanical = MagicMock()
    ctx = PyMechanicalAppContext(mechanical=mock_mechanical)
    assert ctx.mechanical == mock_mechanical

    # Test creating PyMechanicalAppContext without Mechanical
    ctx_none = PyMechanicalAppContext(mechanical=None)
    assert ctx_none.mechanical is None


@pytest.mark.unit
def test_mcp_server_initialization():
    """Test that MCP server is properly initialized."""
    assert app is not None
    assert app.name == "PyMechanical MCP Server"


@pytest.mark.unit
def test_mcp_server_has_tools():
    """Test that MCP server has registered tools."""
    # The mcp server should have tools registered
    # This is a basic check to ensure tools are defined
    from ansys.mechanical.mcp.tools import check_mechanical_status, run_python_script

    assert callable(check_mechanical_status)
    assert callable(run_python_script)
