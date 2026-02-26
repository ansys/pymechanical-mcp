"""Helper functions for PyMechanical-MCP."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ansys.mechanical.core import Mechanical

logger = logging.getLogger(__name__)


def list_instances(
    instances: bool = False, long: bool = False, cmd: bool = False, location: bool = False
) -> str:
    """
    List running Mechanical instances on the system.

    This function scans all running processes to identify Ansys Mechanical instances
    that are using gRPC communication. It returns a formatted table with information
    about each discovered instance.

    Parameters
    ----------
    instances : bool, optional
        If True, only show main Mechanical instances (exclude child processes).
        If False, show all Mechanical-related processes. Default is False.
    long : bool, optional
        If True, enable verbose output including command line and working directory.
        This automatically sets both `cmd` and `location` to True. Default is False.
    cmd : bool, optional
        If True, include the command line arguments in the output table.
        Default is False.
    location : bool, optional
        If True, include the working directory path in the output table.
        Default is False.

    Returns
    -------
    str
        A formatted table string containing information about Mechanical instances.
        The table includes columns for process name, status, gRPC port, PID,
        and optionally command line and working directory based on the parameters.

    Notes
    -----
    - This function identifies Mechanical processes by looking for "AnsysWBU" or
      "mechanical" in the process name or command line.
    - Only processes with status RUNNING, IDLE, or SLEEPING are considered valid.
    """
    import psutil
    from tabulate import tabulate

    mechanical_instances = []

    def is_grpc_based(proc):
        """Check if process uses gRPC."""
        cmdline = proc.cmdline()
        # Check for --port flag or grpc indicators
        return "--port" in cmdline or "-grpc" in cmdline or any("grpc" in arg.lower() for arg in cmdline)

    def get_port(proc):
        """Extract port from command line."""
        cmdline = proc.cmdline()
        if "--port" in cmdline:
            try:
                ind_port = cmdline.index("--port")
                return cmdline[ind_port + 1]
            except (IndexError, ValueError):
                pass
        return "N/A"

    def is_valid_process(proc):
        """Check if process is a valid Mechanical instance."""
        valid_status = proc.status() in [
            psutil.STATUS_RUNNING,
            psutil.STATUS_IDLE,
            psutil.STATUS_SLEEPING,
        ]
        name_lower = proc.name().lower()
        cmdline_str = " ".join(proc.cmdline()).lower()
        
        # Check for Mechanical process indicators
        is_mechanical = (
            "ansyswbu" in name_lower or
            "mechanical" in name_lower or
            "ansys mechanical" in cmdline_str or
            "ansys-mechanical" in cmdline_str
        )
        
        return valid_status and is_mechanical

    for proc in psutil.process_iter():
        try:
            if is_valid_process(proc):
                # Check if it's a main process or child
                if len(proc.children(recursive=True)) < 2:
                    proc.ansys_instance = False
                else:
                    proc.ansys_instance = True
                mechanical_instances.append(proc)

        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            continue

    # Configure output columns
    if long:
        cmd = True
        location = True

    if instances:
        headers = ["Name", "Status", "gRPC port", "PID"]
    else:
        headers = ["Name", "Is Instance", "Status", "gRPC port", "PID"]

    if cmd:
        headers.append("Command line")
    if location:
        headers.append("Working directory")

    table = []
    for each_p in mechanical_instances:
        if instances and not each_p.ansys_instance:
            continue

        proc_line = []
        proc_line.append(each_p.name())

        if not instances:
            proc_line.append(each_p.ansys_instance)

        proc_line.extend([each_p.status(), get_port(each_p), each_p.pid])

        if cmd:
            proc_line.append(" ".join(each_p.cmdline()))

        if location:
            try:
                proc_line.append(each_p.cwd())
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                proc_line.append("N/A")

        table.append(proc_line)

    return str(tabulate(table, headers))


def get_info(mechanical: "Mechanical") -> dict[str, str | dict[str, Any]]:
    """
    Get information from the Mechanical instance.

    Parameters
    ----------
    mechanical : Mechanical
        Mechanical instance

    Returns
    -------
    dict[str, str | dict[str, Any]]
        Dictionary containing Mechanical information
    """
    info: dict[str, str | dict[str, Any]] = {}

    # Basic connection information
    try:
        info["connection"] = {
            "version": mechanical.version,
            "project_directory": str(mechanical.project_directory),
            "is_alive": mechanical.is_alive,
            "name": mechanical.name if hasattr(mechanical, "name") else "N/A",
            "busy": mechanical.busy if hasattr(mechanical, "busy") else False,
            "exited": mechanical.exited if hasattr(mechanical, "exited") else False,
        }
    except Exception as e:
        logger.warning(f"Error extracting connection info: {e}")
        info["connection"] = {"error": str(e)}

    # Product information
    try:
        product_info = mechanical.get_product_info()
        info["product_info"] = {
            "raw": product_info if product_info else "N/A",
        }
    except Exception as e:
        logger.warning(f"Error extracting product info: {e}")
        info["product_info"] = {"error": str(e)}

    # Try to get model information via script
    try:
        script = """
import json
model_info = {}

# Get Project info
project = ExtAPI.DataModel.Project
model_info['product_version'] = project.ProductVersion

# Get Model name
model = Model
model_info['model_name'] = model.Name if hasattr(model, 'Name') else 'N/A'

json.dumps(model_info)
"""
        result = mechanical.run_python_script(script)
        if result:
            import json
            model_data = json.loads(result)
            info["model"] = model_data
    except Exception as e:
        logger.warning(f"Error extracting model info via script: {e}")
        info["model"] = {"error": str(e)}

    return info
