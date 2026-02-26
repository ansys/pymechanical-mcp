"""List of tools in PyMechanical-MCP."""

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from fastmcp.server import Context
from fastmcp.server.server import get_logger
from mcp.types import ImageContent, TextContent

# Import Mechanical at module level to avoid import during tool execution
# The import happens during server startup, before STDIO transport is active
from ansys.mechanical import core as pymechanical  # pyright: ignore[reportMissingTypeStubs]
from ansys.mechanical.mcp import app
from ansys.mechanical.mcp.server import session

logger = get_logger(__name__)


# Access type-safe lifespan context in tools
@app.tool()
def check_mechanical_status(ctx: Context) -> str:
    """Check the status of Mechanical initialization.

    This tool retrieves comprehensive information from the connected Mechanical
    instance including version, project directory, and connection status.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.

    Returns
    -------
    str
        JSON string containing comprehensive Mechanical status information including:
        - connection: Basic connection info (version, project_directory, is_alive)
        - product_info: Product version and build information

        Returns an error message if Mechanical is not available or has exited.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        from ansys.mechanical.mcp.helpers import get_info

        # Check if Mechanical has exited
        if hasattr(mechanical, "exited") and mechanical.exited:
            return "Mechanical instance has exited. Please reconnect or launch a new instance."

        info = get_info(mechanical)

        # Return as formatted JSON
        return json.dumps(info, indent=2)

    except Exception as e:
        error_msg = f"Error checking Mechanical status: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali"})
def check_mechanical_installed(ctx: Context) -> str:
    """Check if Mechanical is installed on the system.

    This tool uses PyMechanical's check_valid_mechanical function to verify if a valid
    ANSYS/Mechanical installation is available on the system.

    Returns
    -------
    str
        Status message indicating whether Mechanical is installed or not.
    """
    logger.info("Checking if Mechanical is installed...")

    try:
        from ansys.mechanical.core.mechanical import check_valid_mechanical

        is_installed = check_valid_mechanical()

        if is_installed:
            logger.info("Mechanical installation found")
            return "Mechanical is installed on this system."
        else:
            logger.info("Mechanical installation not found")
            return (
                "Mechanical is not installed on this system or cannot be found in the "
                "standard locations. Please ensure ANSYS/Mechanical is properly installed "
                "and the installation path is correct."
            )

    except Exception as e:
        error_msg = f"Error checking Mechanical installation: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool()
def run_python_script(ctx: Context, script: str) -> str:
    """Execute a Python script inside Mechanical.

    This tool runs a Python script block inside the connected Mechanical instance
    using Mechanical's scripting API. The script has access to Mechanical's
    ExtAPI, DataModel, Model, Tree, and Graphics entry points.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    script : str
        The Python script to execute inside Mechanical.

    Returns
    -------
    str
        Script execution result. Returns the string value of the last executed
        statement, or an empty string if the value cannot be returned as a string.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        result = mechanical.run_python_script(script)
        return f"Script executed successfully. Result: {result}"
    except Exception as e:
        error_msg = f"Error executing script: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool()
def run_python_script_from_file(ctx: Context, file_path: str) -> str:
    """Execute a Python script file inside Mechanical.

    This tool runs the contents of a Python file inside the connected Mechanical
    instance. The file must be accessible from the local filesystem.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    file_path : str
        Path to the Python script file to execute.

    Returns
    -------
    str
        Script execution result.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if not Path(file_path).exists():
        return f"Script file not found: {file_path}"

    try:
        result = mechanical.run_python_script_from_file(file_path)
        return f"Script file executed successfully. Result: {result}"
    except Exception as e:
        error_msg = f"Error executing script file: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali"})
def run_multiple_scripts(ctx: Context, scripts: list[str]) -> str:
    """Execute multiple Python scripts inside Mechanical in sequence.

    This tool runs multiple Python scripts inside the connected Mechanical instance
    in sequence. This is useful for multi-step workflows where each script builds
    on the previous one.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    scripts : list[str]
        List of Python scripts to execute inside Mechanical.

    Returns
    -------
    str
        Execution results for all scripts.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if not scripts:
        return "No scripts provided to execute."

    results = []
    for i, script in enumerate(scripts, 1):
        try:
            result = mechanical.run_python_script(script)
            results.append(f"Script {i}: Success - {result}")
        except Exception as e:
            results.append(f"Script {i}: Error - {str(e)}")
            # Continue with remaining scripts even if one fails

    return f"Executed {len(scripts)} scripts:\n" + "\n".join(results)


@app.tool(tags={"aali", "locked_connection"})
def launch_mechanical(
    ctx: Context,
    exec_file: str | None = None,
    port: int | None = None,
    batch: bool = True,
    version: str | None = None,
) -> str:
    """Launch a new Mechanical instance.

    This tool starts a new Mechanical instance using PyMechanical's launch_mechanical
    function. The launched instance will be automatically connected and stored in
    the context for subsequent operations.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    exec_file : str, optional
        The path to the Mechanical executable. If None, PyMechanical will attempt
        to find the executable automatically.
    port : int, optional
        The gRPC port for Mechanical to listen on. If None, defaults to 10000.
    batch : bool, optional
        Whether to launch Mechanical in batch mode. Default is True.
    version : str, optional
        Mechanical version to run (e.g., "252" for 2025 R2). If None, uses the
        latest installed version.

    Returns
    -------
    str
        Launch status message with Mechanical version and connection information.
    """
    logger.info("Launching new Mechanical instance...")

    try:
        # Check if there's already a connection
        if ctx.request_context.lifespan_context.mechanical is not None:
            return (
                "Already connected to a Mechanical instance. "
                "Please disconnect first using disconnect_from_mechanical tool."
            )

        # Launch new Mechanical instance
        kwargs: dict[str, Any] = {
            "batch": batch,
            "loglevel": "INFO",
            "cleanup_on_exit": True,
        }

        if exec_file is not None:
            kwargs["exec_file"] = exec_file

        if port is not None:
            kwargs["port"] = port

        if version is not None:
            kwargs["version"] = version

        # Launch Mechanical
        mechanical = pymechanical.launch_mechanical(**kwargs)

        # Store in context for later use
        ctx.request_context.lifespan_context.mechanical = mechanical

        logger.info("Mechanical launched successfully!")
        return (
            f"Successfully launched Mechanical\n"
            f"Version: {mechanical.version}\n"
            f"Project Directory: {mechanical.project_directory}\n"
        )

    except Exception as e:
        error_msg = f"Failed to launch Mechanical: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali", "locked_connection"})
def connect_to_mechanical(
    ctx: Context, port: int = 10000, ip: str = "127.0.0.1"
) -> str:
    """Connect to an existing Mechanical instance.

    This tool establishes a connection to a running Mechanical instance using the
    provided port and IP address. The connection is stored for subsequent
    operations and can be closed using the disconnect_from_mechanical tool.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    port : int, optional
        The gRPC port where Mechanical is listening. Default is 10000.
    ip : str, optional
        The IP address where Mechanical is running. Default is "127.0.0.1".

    Returns
    -------
    str
        Connection status message with Mechanical version information.
    """
    logger.info(f"Connecting to Mechanical instance at {ip}:{port}...")

    try:
        # Check if there's already a connection
        if ctx.request_context.lifespan_context.mechanical is not None:
            return (
                "Already connected to a Mechanical instance. "
                "Please disconnect first using disconnect_from_mechanical tool."
            )

        # Connect to existing Mechanical instance
        mechanical = pymechanical.connect_to_mechanical(
            ip=ip,
            port=port,
            cleanup_on_exit=False,
        )

        # Store in context for later use
        ctx.request_context.lifespan_context.mechanical = mechanical

        logger.info(f"Connected to Mechanical successfully at {ip}:{port}!")
        return (
            f"Successfully connected to Mechanical at {ip}:{port}\n"
            f"Version: {mechanical.version}\n"
        )

    except Exception as e:
        error_msg = f"Failed to connect to Mechanical at {ip}:{port}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali", "locked_connection"})
def disconnect_from_mechanical(ctx: Context) -> str:
    """Disconnect from the connected Mechanical instance.

    This tool closes the connection to the Mechanical instance and releases
    the associated resources.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.

    Returns
    -------
    str
        Disconnection status message.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return "No Mechanical connection to disconnect."

    try:
        logger.info("Disconnecting from Mechanical...")

        # Exit the Mechanical connection
        mechanical.exit()

        # Clear from context
        ctx.request_context.lifespan_context.mechanical = None

        logger.info("Disconnected successfully!")
        return "Successfully disconnected from Mechanical"

    except Exception as e:
        error_msg = f"Error during disconnect: {str(e)}"
        logger.error(error_msg)
        # Still clear the reference even if disconnect failed
        ctx.request_context.lifespan_context.mechanical = None
        return error_msg


@app.tool()
def list_mechanical_instances() -> str:
    """List all Mechanical instances running on the local machine.

    This tool discovers Mechanical instances running on the machine by scanning
    for active gRPC servers and their associated metadata.

    Returns
    -------
    str
        Formatted table containing information about all running Mechanical instances
        including their names, status, gRPC ports, PIDs, and working directories.
    """
    logger.info("Searching for Mechanical instances...")

    from ansys.mechanical.mcp.helpers import list_instances

    # Use list_instances function with long=True for detailed output
    return list_instances(long=True, instances=True)


@app.tool()
def list_files(ctx: Context) -> str:
    """List files in the Mechanical working directory.

    This tool lists all files in the working directory of the connected
    Mechanical instance.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.

    Returns
    -------
    str
        List of files in the working directory.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        files = mechanical.list_files()
        if not files:
            return "No files found in the working directory."

        file_list = "\n".join(f"  - {f}" for f in files)
        return f"Files in working directory:\n{file_list}"
    except Exception as e:
        error_msg = f"Error listing files: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool()
def upload_file(ctx: Context, file_path: str) -> str:
    """Upload a file to the Mechanical instance.

    This tool uploads a local file to the Mechanical instance's working directory.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    file_path : str
        Path to the local file to upload.

    Returns
    -------
    str
        Upload status message.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if not Path(file_path).exists():
        return f"File not found: {file_path}"

    try:
        result = mechanical.upload(file_path, progress_bar=False)
        return f"Successfully uploaded file: {result}"
    except Exception as e:
        error_msg = f"Error uploading file: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool()
def download_file(ctx: Context, file_name: str, target_dir: str | None = None) -> str:
    """Download a file from the Mechanical instance.

    This tool downloads a file from the Mechanical instance's working directory
    to the local filesystem.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    file_name : str
        Name of the file to download from the Mechanical working directory.
    target_dir : str, optional
        Local directory to save the downloaded file. If None, uses current directory.

    Returns
    -------
    str
        Download status message with local file path.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        local_paths = mechanical.download(
            file_name,
            target_dir=target_dir,
            progress_bar=False,
        )
        if local_paths:
            return f"Successfully downloaded file(s): {', '.join(local_paths)}"
        else:
            return f"No files matching '{file_name}' found to download."
    except Exception as e:
        error_msg = f"Error downloading file: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool()
def clear_mechanical(ctx: Context) -> str:
    """Clear the Mechanical database.

    This tool clears the current database in the Mechanical instance,
    providing a fresh start for a new analysis.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.

    Returns
    -------
    str
        Clear status message.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        mechanical.clear()
        return "Mechanical database cleared successfully."
    except Exception as e:
        error_msg = f"Error clearing database: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool()
def get_project_directory(ctx: Context) -> str:
    """Get the project directory of the Mechanical instance.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.

    Returns
    -------
    str
        The project directory path.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        return f"Project directory: {mechanical.project_directory}"
    except Exception as e:
        error_msg = f"Error getting project directory: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool()
def get_model_info(ctx: Context) -> str:
    """Get information about the current model in Mechanical.

    This tool retrieves information about the current model including
    geometry, mesh, and analysis settings by executing a script inside
    Mechanical.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.

    Returns
    -------
    str
        JSON string containing model information.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        # Script to gather model information
        script = """
import json

model_info = {}

# Get Project info
project = ExtAPI.DataModel.Project
model_info['project'] = {
    'product_version': project.ProductVersion,
    'name': project.Name if hasattr(project, 'Name') else 'N/A',
}

# Get Model info
model = Model
model_info['model'] = {
    'name': model.Name if hasattr(model, 'Name') else 'N/A',
}

# Get Geometry info
if hasattr(model, 'Geometry') and model.Geometry is not None:
    geom = model.Geometry
    model_info['geometry'] = {
        'body_count': geom.Children.Count if hasattr(geom, 'Children') else 0,
    }
else:
    model_info['geometry'] = {'body_count': 0}

# Get Mesh info
if hasattr(model, 'Mesh') and model.Mesh is not None:
    mesh = model.Mesh
    model_info['mesh'] = {
        'node_count': mesh.Nodes.Count if hasattr(mesh, 'Nodes') and mesh.Nodes else 0,
        'element_count': mesh.Elements.Count if hasattr(mesh, 'Elements') and mesh.Elements else 0,
    }
else:
    model_info['mesh'] = {'node_count': 0, 'element_count': 0}

# Get Analysis count
if hasattr(model, 'Analyses') and model.Analyses is not None:
    model_info['analyses_count'] = model.Analyses.Count
else:
    model_info['analyses_count'] = 0

json.dumps(model_info)
"""
        result = mechanical.run_python_script(script)
        return result if result else json.dumps({"error": "Could not retrieve model info"})
    except Exception as e:
        error_msg = f"Error getting model info: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool()
def screenshot(
    ctx: Context,
    view_type: str = "model",
) -> list[TextContent | ImageContent]:
    """Capture a screenshot of the current Mechanical view.

    This tool captures the current graphics view from Mechanical as an image.
    It can capture model views, mesh views, or result contour plots.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    view_type : str, optional
        Type of view to capture: "model", "mesh", or "result". Default is "model".

    Returns
    -------
    list[TextContent | ImageContent]
        A list containing:
        - TextContent with the screenshot file path
        - ImageContent with the base64-encoded image data
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return [
            TextContent(
                type="text",
                text=(
                    "No Mechanical connection available. "
                    "Use connect_to_mechanical tool to establish a connection."
                ),
            )
        ]

    try:
        logger.info(f"Capturing Mechanical screenshot (type: {view_type})...")

        # Create a temporary file with .png extension
        temp_fd, temp_path = tempfile.mkstemp(suffix=".png", prefix="mechanical_screenshot_")
        os.close(temp_fd)

        # Script to capture screenshot using Mechanical's Graphics API
        script = f"""
import os

# Get the Graphics object
graphics = ExtAPI.Graphics

# Export the current view to image
graphics.ExportImage(r"{temp_path}", ImageExportFormat.PNG, GraphicsImageExportSettings())

r"{temp_path}"
"""
        try:
            result = mechanical.run_python_script(script)
            logger.info(f"Screenshot script result: {result}")
        except Exception as e:
            logger.warning(f"Graphics export failed: {e}")
            return [TextContent(type="text", text=f"Screenshot capture failed: {str(e)}")]

        # Verify file was created
        image_path = Path(temp_path)
        if not image_path.exists():
            return [TextContent(type="text", text=f"Screenshot file not created: {temp_path}")]

        # Read image data
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Encode to base64
        base64_data = base64.b64encode(image_data).decode("utf-8")

        # Determine mime type
        mime_type = "image/png"

        logger.info(f"Screenshot captured successfully: {temp_path}")

        # Return both text (file path) and image content
        return [
            TextContent(type="text", text=f"Screenshot saved to: {temp_path}"),
            ImageContent(type="image", data=base64_data, mimeType=mime_type),
        ]

    except Exception as e:
        error_msg = f"Failed to capture screenshot: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


####################################################################################################
# Tools that use the PersistentPythonSession


@app.tool()
def run_python_code(
    ctx: Context,
    code: str,
    timeout: int = 60,
) -> str:
    """Execute Python code in the persistent Python session for data processing.

    IMPORTANT: This tool runs in a separate Python process and does NOT have access
    to the Mechanical gRPC connection. Use this for:
    - Custom data processing and analysis (NumPy, Pandas, SciPy)
    - Creating matplotlib plots and visualizations
    - Post-processing results exported from Mechanical
    - General Python computations

    For code that needs to run inside Mechanical (IronPython with ExtAPI, Model, etc.),
    use the 'run_python_script' tool instead.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    code : str
        The Python code to execute. Should use standard Python libraries.
        Does NOT have access to Mechanical's ExtAPI, Model, or other internal objects.
    timeout : int, optional
        Maximum time in seconds to allow for code execution. Default is 60 seconds.

    Returns
    -------
    str
        Execution result or error message. Returns JSON for structured output.
    """
    session = ctx.request_context.lifespan_context.python_session

    if session is None:
        return json.dumps(
            {
                "success": False,
                "error": "No Python session available. The persistent Python session was not initialized.",
            },
            ensure_ascii=False,
        )

    try:
        # Sanitize the input code
        sanitized_code = _sanitize_output(code)

        logger.info(f"Executing Python code in persistent session:\n{sanitized_code}")

        # Execute code in persistent session
        result = session.execute(sanitized_code, timeout=timeout)

        # Parse the result
        if isinstance(result, dict):
            stdout = _sanitize_output(result.get("stdout", ""))
            stderr = _sanitize_output(result.get("stderr", ""))

            if result.get("success"):
                return json.dumps(
                    {
                        "success": True,
                        "stdout": stdout,
                        "stderr": stderr,
                        "message": "Python code executed successfully",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                error_msg = result.get("error", "Unknown error occurred")
                error_msg = _sanitize_output(error_msg)
                return json.dumps(
                    {"success": False, "stdout": stdout, "stderr": stderr, "error": error_msg},
                    ensure_ascii=False,
                    indent=2,
                )
        else:
            return json.dumps(
                {
                    "success": True,
                    "stdout": _sanitize_output(str(result)) if result else "",
                    "stderr": "",
                    "message": "Python code executed successfully",
                },
                ensure_ascii=False,
                indent=2,
            )

    except TimeoutError:
        error_dict = {
            "success": False,
            "error": f"Python code execution timed out after {timeout} seconds",
        }
        logger.error(error_dict["error"])
        return json.dumps(error_dict, ensure_ascii=False)

    except Exception as e:
        error_dict = {"success": False, "error": f"Error executing Python code: {str(e)}"}
        logger.error(error_dict["error"])
        return json.dumps(error_dict, ensure_ascii=False)


@app.tool(tags={"aali"})
def create_custom_plot(
    ctx: Context,
    plot_code: str,
    plot_type: str = "matplotlib",
    timeout: int = 60,
) -> list[TextContent | ImageContent] | str:
    """Create a custom plot using matplotlib in the persistent Python session.

    IMPORTANT: This tool runs in a separate Python process and does NOT have access
    to the Mechanical gRPC connection. Use this for:
    - Visualizing data that was exported/saved from Mechanical
    - Creating plots from result files (CSV, TXT, etc.)
    - Post-processing visualizations

    For plots that need data directly from Mechanical, first use 'run_python_script'
    to export the data to a file, then use this tool to create the visualization.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    plot_code : str
        Python code to create the plot. Should use matplotlib.pyplot.
        For matplotlib, the code should create the figure/plot but NOT call plt.show().
        Use save_matplotlib_plot() helper function to return the plot.
    plot_type : str, optional
        Type of plot: "matplotlib" or "pyvista". Default is "matplotlib".
    timeout : int, optional
        Maximum time in seconds for plot generation. Default is 60 seconds.

    Returns
    -------
    list[TextContent | ImageContent]
        A list containing:
        - TextContent with the plot creation status message
        - ImageContent with the base64-encoded image data if successful
        or a JSON string with error details if failed.
    """
    session = ctx.request_context.lifespan_context.python_session

    if session is None:
        return [
            TextContent(
                type="text",
                text="No Python session available. The persistent Python session was not initialized.",
            )
        ]

    try:
        logger.info(f"Creating custom {plot_type} plot in persistent session")

        # Sanitize the plot code
        sanitized_plot_code = _sanitize_output(plot_code)

        # Execute the plot code
        result = session.execute(sanitized_plot_code, timeout=timeout)

        # Parse the result
        if isinstance(result, dict):
            stdout = _sanitize_output(result.get("stdout", ""))
            stderr = _sanitize_output(result.get("stderr", ""))

            if result.get("success"):
                # Try to extract plot data from stdout
                plot_data = stdout.strip()

                # Check if the output contains a base64 data URI
                if "data:image/png;base64," in plot_data:
                    # Extract the base64 part
                    base64_data = plot_data.split("data:image/png;base64,")[1].strip()

                    return [
                        TextContent(
                            type="text",
                            text=f"Custom {plot_type} plot created successfully",
                        ),
                        ImageContent(type="image", data=base64_data, mimeType="image/png"),
                    ]
                elif plot_data.startswith("Plot saved to"):
                    return [
                        TextContent(
                            type="text",
                            text=f"Custom {plot_type} plot created successfully\n{plot_data}",
                        )
                    ]
                else:
                    return [
                        TextContent(
                            type="text",
                            text=f"Plot created but unexpected output format:\n{stdout}",
                        )
                    ]
            else:
                error_msg = result.get("error", "Unknown error occurred")
                error_msg = _sanitize_output(error_msg)
                return [
                    TextContent(
                        type="text",
                        text=f"Error creating custom {plot_type} plot: {error_msg}\nStdout: {stdout}\nStderr: {stderr}",
                    )
                ]
        else:
            return [
                TextContent(
                    type="text",
                    text=f"Unexpected result format: {_sanitize_output(str(result)) if result else 'No result'}",
                )
            ]

    except TimeoutError:
        error_msg = f"Plot creation timed out after {timeout} seconds"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]

    except Exception as e:
        error_msg = f"Error creating custom plot: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


def _sanitize_output(text: str) -> str:
    """Sanitize output text to handle encoding issues.

    This function removes or replaces problematic Unicode characters that can cause
    encoding issues on Windows systems with limited character sets.

    Parameters
    ----------
    text : str
        The text to sanitize.

    Returns
    -------
    str
        The sanitized text with problematic characters removed or replaced.
    """
    if not isinstance(text, str):
        return text

    # Replace common problematic Unicode characters with ASCII alternatives
    replacements = {
        # Checkmarks and crosses
        "\u2713": "[OK]",  # checkmark
        "\u2717": "[X]",  # cross
        # Box drawing characters
        "\u2514": "\\",  # box drawing
        "\u2502": "|",  # box drawing
        "\u2500": "-",  # box drawing
        "\u2510": "\\",  # box drawing
        "\u250c": "/",  # box drawing
        "\u2518": "/",  # box drawing
        # Block elements
        "\u2588": "#",  # block
        "\u2589": "#",  # block
        "\u258a": "#",  # block
        "\u258c": "|",  # block
        "\u2590": "|",  # block
        # Superscript and subscript characters
        "\u00b9": "^1",  # superscript 1
        "\u00b2": "^2",  # superscript 2
        "\u00b3": "^3",  # superscript 3
        "\u2074": "^4",  # superscript 4
        "\u2075": "^5",  # superscript 5
        "\u2076": "^6",  # superscript 6
        "\u2077": "^7",  # superscript 7
        "\u2078": "^8",  # superscript 8
        "\u2079": "^9",  # superscript 9
        "\u2070": "^0",  # superscript 0
        # Other commonly problematic characters
        "\u2022": "*",  # bullet
        "\u2023": "*",  # triangular bullet
        "\u2219": "*",  # bullet operator
        "\u00a0": " ",  # non-breaking space
        "\u200b": "",  # zero-width space
        "\u200c": "",  # zero-width non-joiner
        "\u200d": "",  # zero-width joiner
        "\ufeff": "",  # zero-width no-break space
    }

    for unicode_char, replacement in replacements.items():
        text = text.replace(unicode_char, replacement)

    # Remove any remaining characters that can't be encoded in ascii
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        text = text.encode("ascii", errors="replace").decode("ascii")

    return text


# Conditionally disable tools based on session configuration
if session.on_aali:
    app.disable(tags={"aali"})

if session.locked_connection:
    app.disable(tags={"locked_connection"})
