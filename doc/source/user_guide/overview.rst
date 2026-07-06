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
- Open and save project files and transfer artifacts
- Export result data and create custom plots
- Provide topic-specific workflow guidance with ``get_guidelines_for``

How it works
------------

PyMechanical-MCP runs a FastMCP server and exposes a set of tools that map
to Mechanical operations. A client (VS Code, Claude Code, Claude Desktop,
or a custom MCP client) invokes tools over STDIO or HTTP transport.

The server maintains a persistent app context that stores connection
state and execution session data across tool calls.

Connection-aware tool visibility
--------------------------------

PyMechanical-MCP hides tools tagged with ``REQUIRES_MECHANICAL_TAG`` until you
establish a Mechanical connection. This keeps the visible tool surface relevant to the
current state.

- Before connection: Lifecycle and utility tools are available.
- After connection: Model, script, and result tools become available.
- After disconnect: Connection-dependent tools become unavailable

If you use ``--connect-on-startup``, connection-dependent tools are available
immediately, and PyMechanical-MCP disables the ``launch_mechanical``,
``connect_to_mechanical``, and ``disconnect_from_mechanical`` tools.

Security and transport modes
----------------------------

PyMechanical supports multiple gRPC transport modes for connecting to
Mechanical:

- ``auto`` (default): automatic mode detection based on the environment
- ``insecure``: plaintext gRPC
- ``mtls``: mutual TLS
- ``wnua``: Windows Named User Authentication

This allows local development, secured remote connectivity, and containerized
deployments with consistent MCP semantics.

Typical workflow
----------------

#. Check the installation and status (``check_mechanical_installed``, ``check_mechanical_status``).
#. Connect or launch Mechanical.
#. Import the geometry and set up the analysis with scripting tools.
#. Solve (``solve_analysis``).
#. Inspect and export results (``get_model_info``, ``export_results``, ``screenshot``).
