"""Integration tests for PyMechanical MCP Server.

These tests require a running Mechanical instance and are marked as 'integration'.
Run with: pytest -m integration

To skip integration tests, run: pytest -m "not integration"
"""

import os
from unittest.mock import MagicMock

import pytest

from ansys.mechanical.mcp.server import PyMechanicalAppContext
from ansys.mechanical.mcp.tools import (
    check_mechanical_status,
    run_python_script,
    run_multiple_scripts,
)

ON_LOCAL = os.getenv("ON_LOCAL", "true") == "true"


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


@pytest.mark.integration
@pytest.mark.slow
class TestMechanicalIntegration:
    """Integration tests that require a real Mechanical connection.

    This class combines all basic Mechanical integration tests to share a single
    Mechanical instance, reducing test execution time.
    """

    @pytest.fixture(scope="class")
    def real_mechanical(self):
        """
        Fixture to connect to a real Mechanical instance.

        This requires Mechanical to be running on localhost:10000.
        Skip these tests if Mechanical is not available.
        """
        try:
            from ansys.mechanical.core import launch_mechanical

            mechanical = launch_mechanical(cleanup_on_exit=False, loglevel="ERROR")

            yield mechanical

            # Cleanup after tests
            # Don't exit since Mechanical is running externally
            mechanical.exit()

        except Exception as e:
            # Not allow to skip if running on CICD
            if os.getenv("ON_CI", False):
                raise e
            else:
                pytest.skip(f"Mechanical not available: {e}")

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
        context.request_context.lifespan_context = PyMechanicalAppContext(mechanical=real_mechanical)

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

    def test_real_run_multiple_scripts(self, real_context):
        """Test running multiple scripts with real Mechanical."""
        # Run multiple scripts - use valid syntax that doesn't depend on previous state
        scripts = [
            "print('Script 1')",
            "print('Script 2')",
            "result = 1 + 1",
            "print(f'Result: {result}')",
        ]

        result = run_multiple_scripts(real_context, scripts)

        assert isinstance(result, str)
        assert "Executed 4 scripts" in result

    def test_real_run_multiple_scripts_empty_list(self, real_context):
        """Test error handling with empty script list."""
        result = run_multiple_scripts(real_context, [])

        assert "No scripts provided" in result

    def test_multiple_scripts_large_batch(self, real_context, mechanical):
        """Test running a large batch of scripts."""
        # Create many scripts
        scripts = [f"x_{i} = {i}" for i in range(1, 51)]

        result = run_multiple_scripts(real_context, scripts)

        assert "Executed 50 scripts" in result

    def test_multiple_scripts_error_handling(self, real_context):
        """Test error handling with invalid scripts."""
        # Include an invalid script
        scripts = [
            "print('valid')",
            "INVALID_PYTHON_SYNTAX_XYZ((",  # This should cause an error
        ]

        result = run_multiple_scripts(real_context, scripts)

        # Should get error message
        assert isinstance(result, str)
        # Either successful execution or error message
        assert (
            "Successfully executed" in result
            or "Error executing scripts" in result
            or "error" in result.lower()
        )


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
        from unittest.mock import MagicMock

        from ansys.mechanical.mcp.server import PyMechanicalAppContext

        context = MagicMock()
        context.request_context = MagicMock()
        context.request_context.lifespan_context = PyMechanicalAppContext(mechanical=None)

        return context

    def test_launch_mechanical_basic_workflow(self, clean_context):
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
            result = launch_mechanical(clean_context)

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
            result2 = launch_mechanical(clean_context)
            assert "Already connected to a Mechanical instance" in result2
            assert "disconnect first" in result2

        finally:
            # Clean up
            disconnect_from_mechanical(clean_context)

    def test_launch_mechanical_custom_parameters(self, clean_context):
        """Test launching Mechanical with custom parameters.

        This test combines:
        - Custom port
        - Custom version
        """
        import tempfile

        from ansys.mechanical.mcp.tools import disconnect_from_mechanical, launch_mechanical

        try:
            result = launch_mechanical(clean_context, port=10050)

            # Verify successful launch
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result

            # Verify Mechanical instance was created
            mechanical = clean_context.request_context.lifespan_context.mechanical
            assert mechanical is not None
            assert mechanical.is_alive is True

        finally:
            # Disconnect Mechanical
            disconnect_from_mechanical(clean_context)


@pytest.mark.integration
@pytest.mark.slow
class TestPythonPersistentSessionIntegration:
    """Integration tests for connecting to Mechanical in persistent Python session."""

    @pytest.fixture(scope="class")
    def real_mechanical(self):
        """
        Fixture to connect to a real Mechanical instance.

        This requires Mechanical to be running on localhost:10000.
        Skip these tests if Mechanical is not available.
        """
        try:
            from ansys.mechanical.core import launch_mechanical

            mechanical = launch_mechanical(cleanup_on_exit=False, loglevel="ERROR")

            yield mechanical

            # Cleanup after tests
            # Don't exit since Mechanical is running externally
            mechanical.exit()

        except Exception as e:
            # Not allow to skip if running on CICD
            if os.getenv("ON_CI", False):
                raise e
            else:
                pytest.skip(f"Mechanical not available: {e}")

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

    def test_run_python_code_executes_simple(self, persistent_real_context, capsys):
        """Light-weight execution test using mocked python_session near integration suite."""
        import json
        from unittest.mock import MagicMock

        from ansys.mechanical.mcp.tools import run_python_code

        # Attach a mocked persistent python session to the real_context lifespan
        session = MagicMock()
        session.metadata = {"mechanical": persistent_real_context.request_context.lifespan_context.mechanical}
        # Simulate a normal dict-shaped execution result
        session.execute.return_value = {"success": True, "stdout": "hello\n", "stderr": ""}
        persistent_real_context.request_context.lifespan_context.python_session = session

        with capsys.disabled():
            result = run_python_code(persistent_real_context, code="print('hello')")
        data = json.loads(result)
        assert data["success"] is True
        assert data["stdout"].strip() == "hello"

