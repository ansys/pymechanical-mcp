"""Unit tests for MCP CLI parsing and startup connection behavior."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_main_parses_defaults(monkeypatch):
    """Default args populate mcp._cli_config correctly and doesn't run server."""
    from ansys.mechanical.mcp import app as package_mcp
    from ansys.mechanical.mcp.server import launcher

    # Prevent actual asyncio.run from running
    with patch.object(asyncio, "run") as mock_run:
        launcher([])
        mock_run.assert_called_once()

    # Ensure mcp._cli_config attached and has defaults
    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["transport_type"] == "stdio"
    assert cfg["mechanical_ip"] == "127.0.0.1"
    assert cfg["mechanical_port"] == 10000
    assert cfg["connect_on_startup"] is False
    assert cfg["http_host"] == "127.0.0.1"
    assert cfg["http_port"] == 8080
    assert cfg["cors_origins"] is None


@pytest.mark.unit
def test_main_accepts_http_transport(monkeypatch):
    """Selecting http transport should work now."""
    from ansys.mechanical.mcp import app as package_mcp
    from ansys.mechanical.mcp.server import launcher

    # Prevent actual asyncio.run from running
    with patch.object(asyncio, "run") as mock_run:
        launcher(["--transport", "http"])
        mock_run.assert_called_once()

    # Ensure mcp._cli_config attached and has http transport
    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["transport_type"] == "http"


@pytest.mark.unit
def test_main_invalid_port_raises():
    """Providing an invalid port should cause argparse to exit."""
    from ansys.mechanical.mcp.server import launcher

    with pytest.raises(SystemExit):
        launcher(["--port", "70000"])  # out of 1-65535 should exit


def test_product_startup_attempts_connect_on_startup():
    """When connect_on_startup is True, MCP should attempt to connect to Mechanical."""
    from ansys.mechanical.mcp.server import PyMechanicalMCP, app

    # Prepare a fake Mechanical instance to be returned by connect_to_mechanical
    fake_mechanical = MagicMock()
    fake_mechanical.exit = MagicMock()

    # Mock connect_to_mechanical to return our fake instance
    with patch("ansys.mechanical.core.connect_to_mechanical", return_value=fake_mechanical) as mock_connect:
        # Create MCP instance and attach CLI config directly
        mcp = PyMechanicalMCP()
        setattr(
            mcp,
            "_cli_config",
            {
                "transport_type": "stdio",
                "mechanical_ip": "127.0.0.1",
                "mechanical_port": 10000,
                "connect_on_startup": True,
                "http_host": "127.0.0.1",
                "http_port": 8080,
                "cors_origins": None,
            },
        )
        mcp.create_context()
        mcp.product_startup()

        # Verify connect_to_mechanical was called with correct parameters
        mock_connect.assert_called_once_with(
            ip="127.0.0.1",
            port=10000,
            cleanup_on_exit=False,
        )

        # Verify Mechanical instance was stored in context
        assert mcp.context.mechanical == fake_mechanical

        # Test cleanup
        mcp.product_cleanup()
        fake_mechanical.exit.assert_called_once()
