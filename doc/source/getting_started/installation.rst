.. _ref_installation:

Installation
============

PyMechanical-MCP supports Python 3.10 through 3.13.

Prerequisites
-------------

- Ansys Mechanical installation (local or remote) with an available gRPC endpoint
- Python 3.10+
- Network access between MCP server and Mechanical server

Install from PyPI
-----------------

Install ``ansys-mechanical-mcp`` using ``pip``:

.. code-block:: bash

   pip install ansys-mechanical-mcp

Install from source
-------------------

Clone and install in editable mode:

.. code-block:: bash

   git clone https://github.com/ansys/pymechanical-mcp
   cd pymechanical-mcp
   pip install -e ".[dev]"

Run the server
--------------

STDIO transport (default, for MCP clients such as VS Code and Claude Code):

.. code-block:: bash

   ansys-mechanical-mcp

HTTP transport (for remote/server-style deployments):

.. code-block:: bash

   ansys-mechanical-mcp --transport http --http-host 127.0.0.1 --http-port 8080

Connect on startup (optional)
-----------------------------

To auto-connect to a running Mechanical instance at startup:

.. code-block:: bash

   ansys-mechanical-mcp --connect-on-startup --ip 127.0.0.1 --port 10000

.. warning::
   When ``--connect-on-startup`` is used, the connection is locked and
   ``launch_mechanical``, ``connect_to_mechanical``, and
   ``disconnect_from_mechanical`` are disabled.

Transport security mode
-----------------------

Select gRPC transport behavior with ``--transport-mode``:

- ``auto``: Detect based on platform/certificates.
- ``insecure``: plain text gRPC.
- ``mtls``: Mutual TLS (requires certificates).
- ``wnua``: Windows Named User Authentication.

Example:

.. code-block:: bash

   ansys-mechanical-mcp --transport-mode mtls --certs-dir /path/to/certs

The same values can be supplied with environment variables:

- ``PYMECHANICAL_TRANSPORT_MODE``
- ``ANSYS_GRPC_CERTIFICATES``
