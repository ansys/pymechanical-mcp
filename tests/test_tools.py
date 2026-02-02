"""Tests for MCP tools functionality."""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
from mcp.types import ImageContent, TextContent

from ansys.mechanical.mcp.tools import (
    check_mechanical_status,
    connect_to_mechanical,
    disconnect_from_mechanical,
    launch_mechanical,
    run_python_script,
    run_multiple_scripts,
)


@pytest.mark.unit
class TestCheckMechanicalStatus:
    """Tests for check_mechanical_status tool."""

    def test_check_status_with_mechanical(self, mock_context):
        """Test checking Mechanical status when Mechanical is available."""
        # Mock get_product_info method
        mock_context.request_context.lifespan_context.mechanical.get_product_info = MagicMock(return_value="Product Info")
        mock_context.request_context.lifespan_context.mechanical.busy = False
        mock_context.request_context.lifespan_context.mechanical.exited = False

        result = check_mechanical_status.fn(mock_context)

        assert isinstance(result, str)
        # Check for JSON structure
        import json

        data = json.loads(result)
        assert "connection" in data
        assert "version" in data["connection"]

    def test_check_status_without_mechanical(self, mock_context_no_mechanical):
        """Test checking Mechanical status when Mechanical is not available."""
        result = check_mechanical_status.fn(mock_context_no_mechanical)

        # Should return helpful error message instead of raising exception
        assert isinstance(result, str)
        assert "No Mechanical connection available" in result
        assert "connect_to_mechanical" in result

    def test_check_status_with_exited_mechanical(self, mock_context):
        """Test checking status when Mechanical has exited."""
        mock_context.request_context.lifespan_context.mechanical.exited = True

        result = check_mechanical_status.fn(mock_context)

        assert isinstance(result, str)
        assert "Mechanical instance has exited" in result
        assert "reconnect or launch" in result

    def test_check_status_returns_connection_info(self, mock_context):
        """Test status extraction returns proper connection information."""
        import json

        # Mock get_product_info method
        mock_context.request_context.lifespan_context.mechanical.get_product_info = MagicMock(return_value="Product Info")
        mock_context.request_context.lifespan_context.mechanical.busy = False
        mock_context.request_context.lifespan_context.mechanical.exited = False

        result = check_mechanical_status.fn(mock_context)

        data = json.loads(result)

        # Verify connection section is present
        assert "connection" in data
        assert "version" in data["connection"]
        assert "project_directory" in data["connection"]
        assert "is_alive" in data["connection"]


@pytest.mark.unit
class TestRunMechanicalScript:
    """Tests for run_python_script tool."""

    def test_run_script_success(self, mock_context):
        """Test running a Mechanical script successfully."""
        script = "print('hello')"
        result = run_python_script.fn(mock_context, script)

        assert isinstance(result, str)
        assert "Script executed successfully" in result

        # Verify that Mechanical's run_python_script method was called
        mock_context.request_context.lifespan_context.mechanical.run_python_script.assert_called_once_with(script)

    def test_run_script_with_arguments(self, mock_context):
        """Test running a Mechanical script with arguments."""
        script = "result = 1 + 2; print(result)"
        result = run_python_script.fn(mock_context, script)

        assert isinstance(result, str)
        assert "Script executed successfully" in result

    def test_run_script_without_mechanical(self, mock_context_no_mechanical):
        """Test running a script when Mechanical is not available."""
        result = run_python_script.fn(mock_context_no_mechanical, "print('test')")

        # Should return helpful error message instead of raising exception
        assert isinstance(result, str)
        assert "No Mechanical connection available" in result
        assert "connect_to_mechanical" in result

    def test_run_multiple_scripts(self, mock_context):
        """Test running multiple Mechanical scripts sequentially."""
        scripts = ["print('1')", "print('2')", "print('3')"]

        for script in scripts:
            result = run_python_script.fn(mock_context, script)
            assert "Script executed successfully" in result

        # Verify all scripts were called
        assert mock_context.request_context.lifespan_context.mechanical.run_python_script.call_count == len(scripts)


@pytest.mark.unit
class TestRunMultipleScripts:
    """Tests for run_multiple_scripts tool."""

    def test_run_multiple_scripts_success(self, mock_context):
        """Test running multiple Mechanical scripts successfully."""
        scripts = ["print('1')", "x = 1 + 2", "print(x)"]
        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            "Script executed"
        )

        result = run_multiple_scripts.fn(mock_context, scripts)

        assert isinstance(result, str)
        assert "Executed 3 scripts" in result
        assert "Script 1: Success" in result
        assert "Script 2: Success" in result
        assert "Script 3: Success" in result

        # Verify that Mechanical's run_python_script method was called 3 times
        assert mock_context.request_context.lifespan_context.mechanical.run_python_script.call_count == 3

    def test_run_multiple_scripts_with_output(self, mock_context):
        """Test running multiple scripts with Mechanical output."""
        scripts = ["print('1')", "print('2')"]
        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = ["1", "2"]

        result = run_multiple_scripts.fn(mock_context, scripts)

        assert "Executed 2 scripts" in result
        assert "Script 1: Success - 1" in result
        assert "Script 2: Success - 2" in result

    def test_run_multiple_scripts_empty_list(self, mock_context):
        """Test running multiple scripts with an empty list."""
        result = run_multiple_scripts.fn(mock_context, [])

        assert "No scripts provided" in result

    def test_run_multiple_scripts_without_mechanical(self, mock_context_no_mechanical):
        """Test running multiple scripts when Mechanical is not available."""
        scripts = ["print('1')", "print('2')"]
        result = run_multiple_scripts.fn(mock_context_no_mechanical, scripts)

        # Should return helpful error message instead of raising exception
        assert isinstance(result, str)
        assert "No Mechanical connection available" in result
        assert "connect_to_mechanical" in result

    def test_run_multiple_scripts_single_script(self, mock_context):
        """Test running a single script through multiple scripts."""
        scripts = ["print('hello')"]
        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = "hello"

        result = run_multiple_scripts.fn(mock_context, scripts)

        assert "Executed 1 scripts" in result
        assert "Script 1: Success" in result

    def test_run_multiple_scripts_error_handling(self, mock_context):
        """Test error handling when script execution fails."""
        scripts = ["print('1')", "invalid_syntax((", "print('2')"]
        # First script succeeds, second fails, third succeeds
        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = [
            "1",
            Exception("Invalid syntax"),
            "2",
        ]

        result = run_multiple_scripts.fn(mock_context, scripts)

        # Should continue with remaining scripts even if one fails
        assert "Executed 3 scripts" in result
        assert "Script 1: Success" in result
        assert "Script 2: Error - Invalid syntax" in result
        assert "Script 3: Success" in result

    def test_run_multiple_scripts_large_batch(self, mock_context):
        """Test running a large batch of scripts."""
        # Create 10 scripts
        scripts = [f"x_{i} = {i}" for i in range(1, 11)]
        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = "ok"

        result = run_multiple_scripts.fn(mock_context, scripts)

        assert "Executed 10 scripts" in result
        # Verify run_python_script was called for each script
        assert mock_context.request_context.lifespan_context.mechanical.run_python_script.call_count == 10

    def test_run_multiple_scripts_sequential_execution(self, mock_context):
        """Test that scripts are executed in the correct sequence."""
        scripts = ["SCRIPT1", "SCRIPT2", "SCRIPT3"]
        call_order = []

        def track_calls(script):
            call_order.append(script)
            return "ok"

        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = track_calls

        run_multiple_scripts.fn(mock_context, scripts)

        # Verify scripts were called in order
        assert call_order == scripts


@pytest.mark.unit
class TestConnectToMechanical:
    """Tests for connect_to_mechanical tool."""

    def test_connect_default_parameters(self, mock_context_no_mechanical):
        """Test connecting to Mechanical with default parameters."""
        # Create a mock Mechanical instance
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10000

        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical):
            result = connect_to_mechanical.fn(mock_context_no_mechanical)

            # Verify successful connection
            assert isinstance(result, str)
            assert "Successfully connected to Mechanical" in result
            assert "127.0.0.1:10000" in result
            assert "2024 R2" in result

            # Verify Mechanical was stored in context
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical == mock_mechanical

    def test_connect_custom_port(self, mock_context_no_mechanical):
        """Test connecting to Mechanical with custom port."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R1"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10001

        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical) as mock_connect:
            result = connect_to_mechanical.fn(mock_context_no_mechanical, port=10001)

            # Verify connection with custom port
            assert "Successfully connected to Mechanical" in result
            assert "127.0.0.1:10001" in result

            # Verify connect_to_mechanical was called with correct parameters
            mock_connect.assert_called_once_with(
                ip="127.0.0.1",
                port=10001,
                cleanup_on_exit=False,
            )

    def test_connect_custom_ip(self, mock_context_no_mechanical):
        """Test connecting to Mechanical with custom IP address."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "192.168.1.100"
        mock_mechanical._port = 10000

        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical) as mock_connect:
            result = connect_to_mechanical.fn(mock_context_no_mechanical, ip="192.168.1.100")

            # Verify connection with custom IP
            assert "Successfully connected to Mechanical" in result
            assert "192.168.1.100:10000" in result

            # Verify connect_to_mechanical was called with correct parameters
            mock_connect.assert_called_once_with(
                ip="192.168.1.100",
                port=10000,
                cleanup_on_exit=False,
            )

    def test_connect_custom_ip_and_port(self, mock_context_no_mechanical):
        """Test connecting to Mechanical with both custom IP and port."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "10.0.0.50"
        mock_mechanical._port = 10099

        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical) as mock_connect:
            result = connect_to_mechanical.fn(mock_context_no_mechanical, port=10099, ip="10.0.0.50")

            # Verify connection with custom parameters
            assert "Successfully connected to Mechanical" in result
            assert "10.0.0.50:10099" in result

            # Verify connect_to_mechanical was called with correct parameters
            mock_connect.assert_called_once_with(
                ip="10.0.0.50",
                port=10099,
                cleanup_on_exit=False,
            )

    def test_connect_already_connected(self, mock_context):
        """Test connecting when already connected."""
        # Context already has a Mechanical connection
        result = connect_to_mechanical.fn(mock_context)

        # Verify appropriate error message
        assert "Already connected to a Mechanical instance" in result
        assert "disconnect first" in result

    def test_connect_connection_error(self, mock_context_no_mechanical):
        """Test handling connection errors."""
        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", side_effect=Exception("Connection refused")):
            result = connect_to_mechanical.fn(mock_context_no_mechanical, port=10000, ip="127.0.0.1")

            # Verify error message is returned
            assert "Failed to connect to Mechanical" in result
            assert "Connection refused" in result

            # Verify context remains empty
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is None

    def test_connect_network_error(self, mock_context_no_mechanical):
        """Test handling network errors during connection."""
        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", side_effect=ConnectionError("Network unreachable")):
            result = connect_to_mechanical.fn(mock_context_no_mechanical, port=10000, ip="192.168.1.999")

            # Verify error message
            assert "Failed to connect to Mechanical" in result
            assert "Network unreachable" in result

    def test_connect_timeout_error(self, mock_context_no_mechanical):
        """Test handling timeout errors during connection."""
        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", side_effect=TimeoutError("Connection timed out")):
            result = connect_to_mechanical.fn(mock_context_no_mechanical)

            # Verify timeout error is handled
            assert "Failed to connect to Mechanical" in result
            assert "Connection timed out" in result

    def test_connect_stores_mechanical_in_context(self, mock_context_no_mechanical):
        """Test that connected Mechanical instance is properly stored in context."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10000

        # Verify context starts with no Mechanical
        assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is None

        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical):
            result = connect_to_mechanical.fn(mock_context_no_mechanical)

            # Verify successful connection
            assert "Successfully connected" in result

            # Verify Mechanical is stored in context
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is not None
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical == mock_mechanical

    def test_connect_result_message(self, mock_context_no_mechanical):
        """Test that connect_to_mechanical returns informative success message."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10000

        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical):
            result = connect_to_mechanical.fn(mock_context_no_mechanical)

            # Verify the result contains connection information
            assert isinstance(result, str)
            assert "Successfully connected to Mechanical at 127.0.0.1:10000" in result
            assert "2024 R2" in result


@pytest.mark.unit
class TestDisconnectFromMechanical:
    """Tests for disconnect_from_mechanical tool."""

    def test_disconnect_success(self, mock_context):
        """Test disconnecting from Mechanical successfully."""
        # Store reference to check exit was called
        mechanical_ref = mock_context.request_context.lifespan_context.mechanical

        result = disconnect_from_mechanical.fn(mock_context)

        # Verify successful disconnection
        assert isinstance(result, str)
        assert "Successfully disconnected from Mechanical" in result

        # Verify exit was called on the original object
        mechanical_ref.exit.assert_called_once()

        # Verify Mechanical was removed from context
        assert mock_context.request_context.lifespan_context.mechanical is None

    def test_disconnect_no_connection(self, mock_context_no_mechanical):
        """Test disconnecting when no connection exists."""
        result = disconnect_from_mechanical.fn(mock_context_no_mechanical)

        # Verify appropriate message
        assert "No Mechanical connection to disconnect" in result

    def test_disconnect_clears_context(self, mock_context):
        """Test that disconnect properly clears the context."""
        mock_context.request_context.lifespan_context.mechanical._ip = "127.0.0.1"
        mock_context.request_context.lifespan_context.mechanical._port = 10000

        # Verify Mechanical exists before disconnect
        assert mock_context.request_context.lifespan_context.mechanical is not None

        disconnect_from_mechanical.fn(mock_context)

        # Verify Mechanical is cleared after disconnect
        assert mock_context.request_context.lifespan_context.mechanical is None

    def test_disconnect_error_during_exit(self, mock_context):
        """Test handling errors during disconnection."""
        mock_context.request_context.lifespan_context.mechanical._ip = "127.0.0.1"
        mock_context.request_context.lifespan_context.mechanical._port = 10000
        mock_context.request_context.lifespan_context.mechanical.exit.side_effect = Exception(
            "Disconnection error"
        )

        result = disconnect_from_mechanical.fn(mock_context)

        # Verify error message is returned
        assert "Error during disconnect" in result
        assert "Disconnection error" in result

        # Verify context is still cleared even on error
        assert mock_context.request_context.lifespan_context.mechanical is None

    def test_disconnect_connection_lost(self, mock_context):
        """Test disconnecting when connection is already lost."""
        mock_context.request_context.lifespan_context.mechanical._ip = "127.0.0.1"
        mock_context.request_context.lifespan_context.mechanical._port = 10000
        mock_context.request_context.lifespan_context.mechanical.exit.side_effect = ConnectionError(
            "Connection already closed"
        )

        result = disconnect_from_mechanical.fn(mock_context)

        # Verify error is handled gracefully
        assert "Error during disconnect" in result
        assert "Connection already closed" in result

        # Context should still be cleared
        assert mock_context.request_context.lifespan_context.mechanical is None

    def test_disconnect_return_message(self, mock_context):
        """Test that disconnect_from_mechanical returns informative message."""
        result = disconnect_from_mechanical.fn(mock_context)

        # Verify the result contains disconnection information
        assert isinstance(result, str)
        assert "Successfully disconnected from Mechanical" in result

    def test_disconnect_custom_ip_port(self, mock_context):
        """Test disconnecting from Mechanical with custom IP and port."""
        result = disconnect_from_mechanical.fn(mock_context)

        # Verify disconnection message
        assert "Successfully disconnected from Mechanical" in result


@pytest.mark.unit
class TestLaunchMechanical:
    """Tests for launch_mechanical tool."""

    def test_launch_default_parameters(self, mock_context_no_mechanical):
        """Test launching Mechanical with default parameters."""
        # Create a mock Mechanical instance
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical) as mock_launch:
            result = launch_mechanical.fn(mock_context_no_mechanical)

            # Verify successful launch
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result
            assert "2024 R2" in result

            # Verify launch_mechanical was called with correct parameters
            mock_launch.assert_called_once_with(
                batch=True,
                loglevel="INFO",
                cleanup_on_exit=True,
            )

            # Verify Mechanical was stored in context
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical == mock_mechanical

    def test_launch_with_port(self, mock_context_no_mechanical):
        """Test launching Mechanical with custom port."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical) as mock_launch:
            result = launch_mechanical.fn(mock_context_no_mechanical, port=10050)

            # Verify successful launch
            assert "Successfully launched Mechanical" in result

            # Verify launch_mechanical was called with correct port
            mock_launch.assert_called_once_with(
                batch=True,
                loglevel="INFO",
                cleanup_on_exit=True,
                port=10050,
            )

    def test_launch_with_version(self, mock_context_no_mechanical):
        """Test launching Mechanical with specific version."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical) as mock_launch:
            result = launch_mechanical.fn(mock_context_no_mechanical, version="252")

            # Verify successful launch
            assert "Successfully launched Mechanical" in result
            assert "2025 R2" in result

            # Verify launch_mechanical was called with version
            mock_launch.assert_called_once_with(
                batch=True,
                loglevel="INFO",
                cleanup_on_exit=True,
                version="252",
            )

    def test_launch_all_custom_parameters(self, mock_context_no_mechanical):
        """Test launching Mechanical with all custom parameters."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R1"
        mock_mechanical.project_directory = "/custom/work/dir"

        exec_path = "/path/to/mechanical"

        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical) as mock_launch:
            result = launch_mechanical.fn(
                mock_context_no_mechanical,
                exec_file=exec_path,
                port=10001,
                batch=False,
                version="241",
            )

            # Verify successful launch
            assert "Successfully launched Mechanical" in result
            assert "2024 R1" in result

            # Verify launch_mechanical was called with all parameters
            mock_launch.assert_called_once_with(
                batch=False,
                loglevel="INFO",
                cleanup_on_exit=True,
                exec_file=exec_path,
                port=10001,
                version="241",
            )

    def test_launch_already_connected(self, mock_context):
        """Test launching when already connected to Mechanical."""
        # Context already has a Mechanical connection
        result = launch_mechanical.fn(mock_context)

        # Verify appropriate error message
        assert "Already connected to a Mechanical instance" in result
        assert "disconnect first" in result

    def test_launch_error(self, mock_context_no_mechanical):
        """Test handling launch errors."""
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            side_effect=Exception("Mechanical executable not found"),
        ):
            result = launch_mechanical.fn(mock_context_no_mechanical)

            # Verify error message is returned
            assert "Failed to launch Mechanical" in result
            assert "Mechanical executable not found" in result

            # Verify context remains empty
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is None

    def test_launch_license_error(self, mock_context_no_mechanical):
        """Test handling license errors during launch."""
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            side_effect=Exception("No ANSYS license available"),
        ):
            result = launch_mechanical.fn(mock_context_no_mechanical)

            # Verify error message
            assert "Failed to launch Mechanical" in result
            assert "No ANSYS license available" in result

    def test_launch_stores_mechanical_in_context(self, mock_context_no_mechanical):
        """Test that launched Mechanical instance is properly stored in context."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        # Verify context starts with no Mechanical
        assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is None

        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical):
            result = launch_mechanical.fn(mock_context_no_mechanical)

            # Verify successful launch
            assert "Successfully launched Mechanical" in result

            # Verify Mechanical is stored in context
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is not None
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical == mock_mechanical

    def test_launch_result_message(self, mock_context_no_mechanical):
        """Test that launch_mechanical returns informative success message."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical):
            result = launch_mechanical.fn(mock_context_no_mechanical)

            # Verify the result contains launch information
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result
            assert "Version: 2024 R2" in result
            assert "Project Directory:" in result

    def test_launch_with_port_parameter(self, mock_context_no_mechanical):
        """Test launching Mechanical with specific port parameter."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical) as mock_launch:
            result = launch_mechanical.fn(mock_context_no_mechanical, port=10060)

            # Verify successful launch
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result

            # Verify launch_mechanical was called with port
            mock_launch.assert_called_once_with(
                batch=True,
                loglevel="INFO",
                cleanup_on_exit=True,
                port=10060,
            )

    def test_launch_connection_info_in_result(self, mock_context_no_mechanical):
        """Test that launch result contains all connection info."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/home/user/mechanical_work"

        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical):
            result = launch_mechanical.fn(mock_context_no_mechanical)

            # Verify all connection details are in result
            assert "Successfully launched Mechanical" in result
            assert "Version: 2024 R2" in result
            assert "Project Directory:" in result


@pytest.mark.unit
class TestConnectionLifecycle:
    """Tests for the full connection lifecycle."""

    def test_connect_use_disconnect_workflow(self, mock_context_no_mechanical):
        """Test complete workflow: connect, use, disconnect."""
        # Create mock Mechanical
        mock_mechanical = MagicMock()
        mock_mechanical.name = "Mechanical"
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/test"
        mock_mechanical.is_alive = True
        mock_mechanical.exited = False
        mock_mechanical.busy = False

        mock_mechanical.run_python_script = MagicMock(return_value="Script executed")
        mock_mechanical.get_product_info = MagicMock(return_value="Product Info")

        # Step 1: Connect
        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical):
            result = connect_to_mechanical.fn(mock_context_no_mechanical)
            assert "Successfully connected" in result

        # Step 2: Use Mechanical
        status = check_mechanical_status.fn(mock_context_no_mechanical)
        status_data = json.loads(status)
        assert "connection" in status_data
        assert status_data["connection"]["version"] == "2024 R2"

        script_result = run_python_script.fn(mock_context_no_mechanical, "print('test')")
        assert "Script executed successfully" in script_result

        # Step 3: Disconnect
        result = disconnect_from_mechanical.fn(mock_context_no_mechanical)
        assert "Successfully disconnected" in result

        # Step 4: Verify connection is cleared
        status_after = check_mechanical_status.fn(mock_context_no_mechanical)
        assert "No Mechanical connection available" in status_after

    def test_reconnect_after_disconnect(self, mock_context_no_mechanical):
        """Test that we can reconnect after disconnecting."""
        mock_mechanical1 = MagicMock()
        mock_mechanical1.version = "2024 R2"
        mock_mechanical1._ip = "127.0.0.1"
        mock_mechanical1._port = 10000

        mock_mechanical2 = MagicMock()
        mock_mechanical2.version = "2024 R1"
        mock_mechanical2._ip = "127.0.0.1"
        mock_mechanical2._port = 10001

        # First connection
        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical1):
            result = connect_to_mechanical.fn(mock_context_no_mechanical, port=10000)
            assert "Successfully connected" in result
            assert "10000" in result

        # Disconnect
        disconnect_from_mechanical.fn(mock_context_no_mechanical)

        # Second connection with different parameters
        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical2):
            result = connect_to_mechanical.fn(mock_context_no_mechanical, port=10001)
            assert "Successfully connected" in result
            assert "10001" in result

    def test_tools_without_connection(self, mock_context_no_mechanical):
        """Test that tools return appropriate messages without connection."""
        # Check status without connection
        status = check_mechanical_status.fn(mock_context_no_mechanical)
        assert "No Mechanical connection available" in status

        # Try to run script without connection
        script_result = run_python_script.fn(mock_context_no_mechanical, "print('test')")
        assert "No Mechanical connection available" in script_result


@pytest.mark.unit
class TestLaunchWorkflow:
    """Tests for launch and usage workflow."""

    def test_launch_use_disconnect_workflow(self, mock_context_no_mechanical):
        """Test complete workflow: launch, use, disconnect."""
        # Create mock Mechanical
        mock_mechanical = MagicMock()
        mock_mechanical.name = "Mechanical"
        mock_mechanical.check_status = "Running"
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"
        mock_mechanical.is_alive = True
        mock_mechanical.is_local = True
        mock_mechanical._exited = False
        mock_mechanical._exiting = False
        mock_mechanical.exited = False
        mock_mechanical.busy = False

        mock_mechanical.run_python_script = MagicMock(return_value="Script executed")
        mock_mechanical.get_product_info = MagicMock(return_value="Product Info")

        # Step 1: Launch
        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical):
            result = launch_mechanical.fn(mock_context_no_mechanical)
            assert "Successfully launched Mechanical" in result

        # Step 2: Use Mechanical
        status = check_mechanical_status.fn(mock_context_no_mechanical)
        status_data = json.loads(status)
        assert "connection" in status_data
        assert status_data["connection"]["version"] == "2024 R2"

        script_result = run_python_script.fn(mock_context_no_mechanical, "print('test')")
        assert "Script executed successfully" in script_result

        # Step 3: Disconnect
        result = disconnect_from_mechanical.fn(mock_context_no_mechanical)
        assert "Successfully disconnected" in result

        # Step 4: Verify connection is cleared
        status_after = check_mechanical_status.fn(mock_context_no_mechanical)
        assert "No Mechanical connection available" in status_after

    def test_launch_after_disconnect(self, mock_context_no_mechanical):
        """Test that we can launch after disconnecting."""
        mock_mechanical1 = MagicMock()
        mock_mechanical1.version = "2024 R2"
        mock_mechanical1.project_directory = "/tmp/ansys_mechanical_1234"

        mock_mechanical2 = MagicMock()
        mock_mechanical2.version = "2024 R1"
        mock_mechanical2.project_directory = "/tmp/ansys_mechanical_5678"

        # First launch
        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical1):
            result = launch_mechanical.fn(mock_context_no_mechanical)
            assert "Successfully launched Mechanical" in result
            assert "2024 R2" in result

        # Disconnect
        disconnect_from_mechanical.fn(mock_context_no_mechanical)

        # Second launch
        with patch("ansys.mechanical.mcp.tools.pymechanical.launch_mechanical", return_value=mock_mechanical2):
            result = launch_mechanical.fn(mock_context_no_mechanical)
            assert "Successfully launched Mechanical" in result
            assert "2024 R1" in result

    def test_cannot_launch_when_connected(self, mock_context_no_mechanical):
        """Test that launching fails when already connected."""
        # First, connect to an existing instance
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10000

        with patch("ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical", return_value=mock_mechanical):
            connect_result = connect_to_mechanical.fn(mock_context_no_mechanical)
            assert "Successfully connected" in connect_result

        # Now try to launch - should fail
        launch_result = launch_mechanical.fn(mock_context_no_mechanical)
        assert "Already connected to a Mechanical instance" in launch_result
        assert "disconnect first" in launch_result
