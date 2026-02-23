"""Tests for error handling in PyMechanical MCP Server."""

from unittest.mock import MagicMock

import pytest

from ansys.mechanical.mcp.tools import check_mechanical_status, run_python_script


@pytest.mark.unit
class TestErrorHandling:
    """Tests for error handling in various scenarios."""

    def test_mechanical_script_failure(self, mock_context):
        """Test handling of Mechanical script failures."""
        # Make the run method raise an exception
        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = RuntimeError(
            "Mechanical script failed"
        )

        # The function catches exceptions and returns error messages
        result = run_python_script(mock_context, "INVALID_SCRIPT")
        assert "Error executing script" in result
        assert "Mechanical script failed" in result

    def test_none_mechanical_instance(self, mock_context_no_mechanical):
        """Test handling when Mechanical instance is None."""
        # Should return helpful error message instead of raising exception
        result = check_mechanical_status(mock_context_no_mechanical)
        assert isinstance(result, str)
        assert "No Mechanical connection available" in result

    def test_invalid_context_structure(self):
        """Test handling of invalid context structure."""
        # Create a context with missing mechanical attribute
        invalid_context = MagicMock()
        invalid_context.request_context = MagicMock()
        invalid_context.request_context.lifespan_context = MagicMock()
        invalid_context.request_context.lifespan_context.mechanical = None

        result = check_mechanical_status(invalid_context)
        assert "No Mechanical connection available" in result

    def test_mechanical_timeout(self, mock_context):
        """Test handling of Mechanical timeout scenarios."""
        # Simulate a timeout
        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = TimeoutError(
            "Mechanical script timed out"
        )

        # The function catches exceptions and returns error messages
        result = run_python_script(mock_context, "long_running_script()")
        assert "Error executing script" in result
        assert "timed out" in result

    def test_empty_script_string(self, mock_context):
        """Test handling of empty script string."""
        # This should not raise an error, but pass empty string to Mechanical
        result = run_python_script(mock_context, "")

        assert "Script executed successfully" in result
        mock_context.request_context.lifespan_context.mechanical.run_python_script.assert_called_once_with("")

    def test_very_long_script(self, mock_context):
        """Test handling of very long scripts."""
        # Mechanical should handle long scripts, our code should pass it through
        long_script = "print('X" + "X" * 1000 + "')"
        result = run_python_script(mock_context, long_script)

        assert "Script executed successfully" in result

