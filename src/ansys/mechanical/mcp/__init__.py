"""PyMechanical MCP Server - Model Context Protocol server for Ansys Mechanical.

This package provides a Model Context Protocol (MCP) server that enables
AI assistants to interact with Ansys Mechanical through PyMechanical.
It leverages the Mechanical scripting API to perform structural analysis,
preprocessing, solving, and postprocessing tasks.

"""

__version__ = "0.1.0"


from ansys.mechanical.mcp.server import (
    app,
    launcher,
)

__all__ = [
    "app",
    "launcher",
    "__version__",
]
