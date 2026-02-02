"""Basic tests for PyMechanical MCP Server package."""

import pytest

import ansys.mechanical.mcp


@pytest.mark.unit
def test_version():
    """Test that version is defined and is a string."""
    assert hasattr(ansys.mechanical.mcp, "__version__")
    assert isinstance(ansys.mechanical.mcp.__version__, str)
    assert len(ansys.mechanical.mcp.__version__) > 0


@pytest.mark.unit
def test_package_imports():
    """Test that all expected functions and classes can be imported."""
    from ansys.mechanical.mcp import (
        app,
    )

    assert app is not None


@pytest.mark.unit
def test_all_exports():
    """Test that __all__ contains all expected exports."""
    from ansys.mechanical.mcp import __all__

    expected_exports = [
        "app",
        "launcher",
        "__version__",
    ]

    assert set(__all__) == set(expected_exports)


@pytest.mark.unit
def test_app_context_creation(app_context):
    """Test that PyMechanicalAppContext can be created with Mechanical instance."""
    assert app_context.mechanical is not None
    assert hasattr(app_context.mechanical, "version")


@pytest.mark.unit
def test_app_context_no_mechanical(app_context_no_mechanical):
    """Test that PyMechanicalAppContext can be created without Mechanical instance."""
    assert app_context_no_mechanical.mechanical is None
