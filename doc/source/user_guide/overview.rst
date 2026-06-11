.. _ref_overview:

Overview
========

PyMechanical-MCP is a Model Context Protocol (MCP) server that connects
AI assistants to Ansys Mechanical through PyMechanical.

It enables natural-language workflows for structural, thermal, and modal
analysis setup and review.

Core capabilities
-----------------

- Manage Mechanical sessions (launch, attach, disconnect, clear)
- Execute Mechanical scripts and Python snippets in a persistent session
- Inspect model state (geometry, mesh, analyses, boundary conditions, results)
- Save/open project files and transfer artifacts
- Export result data and create custom plots
- Provide topic-specific workflow guidance with ``get_guidelines_for``

How it works
------------

PyMechanical-MCP runs a FastMCP server and exposes a set of tools that map
to Mechanical operations. A client (VS Code, Claude Code, Claude Desktop,
or a custom MCP client) invokes tools over STDIO or HTTP transport.

The server maintains a persistent application context that stores connection
state and execution session data across tool calls.

Connection-aware tool visibility
--------------------------------

Tools tagged with ``REQUIRES_MECHANICAL_TAG`` are hidden until a Mechanical
connection is established. This keeps the visible tool surface relevant to the
current state.

- Before connection: lifecycle and utility tools are available
- After connection: model/script/result tools are enabled
- After disconnect: connection-dependent tools are disabled again

If ``--connect-on-startup`` is used, connection-dependent tools are available
immediately and ``launch_mechanical`` / ``connect_to_mechanical`` /
``disconnect_from_mechanical`` are intentionally disabled.

Security and transport modes
----------------------------

PyMechanical supports multiple gRPC transport modes for connecting to
Mechanical:

- ``auto`` (default): resolve best mode by environment
- ``insecure``: plaintext gRPC
- ``mtls``: mutual TLS
- ``wnua``: Windows Named User Authentication

This allows local development, secured remote connectivity, and containerized
deployments with consistent MCP semantics.

Typical workflow
----------------

#. Check install/status (``check_mechanical_installed``, ``check_mechanical_status``)
#. Connect or launch Mechanical
#. Import geometry and set up analysis via scripting tools
#. Solve (``solve_analysis``)
#. Inspect and export results (``get_model_info``, ``export_results``, ``screenshot``)
