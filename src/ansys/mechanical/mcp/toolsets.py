# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0

"""Toolset definitions for PyAnsysMCPService discovery.

Exposes the ``toolsets://definition`` MCP resource that groups every tool
registered on the PyMechanical MCP server into logical, user-facing
categories. Each toolset entry follows the schema agreed across the Ansys
MCP family:

``{"name": str, "description": str, "skill": str, "tools": list[str]}``

The catalogue is a pure discovery aid; it does not affect tool visibility,
gating, or runtime behavior. Visibility is still controlled by the existing
``REQUIRES_MECHANICAL_TAG`` / ``aali`` / ``locked_connection`` tags applied
in :mod:`ansys.mechanical.mcp.tools`.
"""

from typing import Any

from ansys.mechanical.mcp import app

#: Master catalogue mapping every logical toolset to its metadata + tool list.
_TOOLSET_CATALOGUE: dict[str, dict[str, Any]] = {
    "lifecycle": {
        "description": (
            "Tools for installing, launching, attaching to, disconnecting "
            "from, and tearing down Mechanical sessions."
        ),
        "skill": (
            "Call check_mechanical_installed once at startup to confirm the "
            "Mechanical binary is on disk. Call check_mechanical_status "
            "before every workflow to see whether this MCP already has a "
            "live Mechanical connection. Use list_mechanical_instances to "
            "discover running Mechanical processes, connect_to_mechanical "
            "to attach to one (or the user-supplied host:port), and "
            "launch_mechanical to start a new instance. Use "
            "disconnect_from_mechanical for a graceful detach and "
            "clear_mechanical to fully release the process."
        ),
        "tools": [
            "check_mechanical_installed",
            "check_mechanical_status",
            "list_mechanical_instances",
            "launch_mechanical",
            "connect_to_mechanical",
            "disconnect_from_mechanical",
            "clear_mechanical",
        ],
    },
    "scripting": {
        "description": (
            "Tools for executing Mechanical (IronPython) scripts and "
            "Python snippets against the live Mechanical session."
        ),
        "skill": (
            "Use run_python_code to execute an inline snippet, "
            "run_python_script to execute an inline Mechanical script "
            "string against ExtAPI, run_python_script_from_file to execute "
            "a .py file uploaded to the Mechanical working directory, and "
            "run_multiple_scripts to execute several scripts in one round "
            "trip. All script tools share the same persistent ExtAPI session."
        ),
        "tools": [
            "run_python_code",
            "run_python_script",
            "run_python_script_from_file",
            "run_multiple_scripts",
        ],
    },
    "project-management": {
        "description": ("Tools for saving, opening, and locating Mechanical project files."),
        "skill": (
            "Use save_project to persist the current project (optionally "
            "save-as a new path), open_project to load a .mechdb file, and "
            "get_project_directory to retrieve the working directory used "
            "by the active session."
        ),
        "tools": [
            "save_project",
            "open_project",
            "get_project_directory",
        ],
    },
    "file-management": {
        "description": (
            "Tools for transferring files to/from the Mechanical working "
            "directory and listing its contents."
        ),
        "skill": (
            "Use upload_file to send a local file (geometry, script, deck) "
            "to the Mechanical working directory, download_file to retrieve "
            "a generated file (results, logs, exports), and list_files to "
            "enumerate the working directory."
        ),
        "tools": [
            "upload_file",
            "download_file",
            "list_files",
        ],
    },
    "simulation": {
        "description": "Tools for running the Mechanical solver.",
        "skill": (
            "Use solve_analysis to invoke the Mechanical solver on the "
            "configured analysis system. Confirm boundary conditions, "
            "mesh, and material assignments are in place first by calling "
            "get_model_info."
        ),
        "tools": [
            "solve_analysis",
        ],
    },
    "inspection": {
        "description": (
            "Tools for inspecting the active Mechanical model, capturing "
            "screenshots, and reading session logs."
        ),
        "skill": (
            "Use get_model_info to retrieve a structured summary of the "
            "active model (geometry, mesh, materials, analyses, BCs, "
            "results). Use screenshot to capture the current 3D view as a "
            "PNG for the user. Use get_mechanical_logs to read application "
            "messages or solver output for diagnostics."
        ),
        "tools": [
            "get_model_info",
            "screenshot",
            "get_mechanical_logs",
        ],
    },
    "results": {
        "description": ("Tools for extracting and exporting Mechanical solver results."),
        "skill": (
            "Use export_results after a successful solve_analysis call to "
            "write result objects to disk. Use create_custom_plot to render "
            "user-defined post-processing plots (contour, vector, or "
            "user-supplied expression) on the solved mesh."
        ),
        "tools": [
            "export_results",
            "create_custom_plot",
        ],
    },
    "guidelines": {
        "description": (
            "Reference tool for retrieving PyMechanical / Ansys Mechanical "
            "scripting guidelines (workflow, geometry, materials, meshing, "
            "analysis setup, boundary conditions, solution, "
            "postprocessing, named selections, general rules)."
        ),
        "skill": (
            "Call get_guidelines_for once per topic before generating "
            "PyMechanical / ExtAPI code. It returns the authoritative "
            "scripting patterns and best practices for the requested "
            "workflow step."
        ),
        "tools": [
            "get_guidelines_for",
        ],
    },
}


def _build_toolsets() -> list[dict[str, Any]]:
    """Return the toolset catalogue as the list[dict] payload expected by clients."""
    return [
        {
            "name": name,
            "description": entry["description"],
            "skill": entry["skill"],
            "tools": list(entry["tools"]),
        }
        for name, entry in _TOOLSET_CATALOGUE.items()
    ]


@app.resource(
    "toolsets://definition",
    name="toolsets_definition",
    description="Toolset definitions for PyAnsysMCPService discovery.",
    mime_type="application/json",
)
def get_toolsets() -> list[dict[str, Any]]:
    """Return toolset definitions for PyAnsysMCPService discovery."""
    return _build_toolsets()
