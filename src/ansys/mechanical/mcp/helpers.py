"""Helper functions for PyMechanical-MCP."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ansys.mechanical.core import Mechanical

logger = logging.getLogger(__name__)


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