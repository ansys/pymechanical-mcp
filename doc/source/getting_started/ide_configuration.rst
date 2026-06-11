.. _ref_ide_configuration:

IDE and client configuration
============================

PyMechanical-MCP works with any MCP-compatible client. This page covers
common integrations: Claude Code, Visual Studio Code, and Claude Desktop.

Claude Code
-----------

Project-scoped configuration (recommended):

.. code-block:: bash

   cd my-project
   claude mcp add --transport stdio pymechanical-mcp -- \
     uvx --index-strategy unsafe-best-match \
     --from git+https://github.com/ansys/pymechanical-mcp \
     ansys-mechanical-mcp

Global configuration:

.. code-block:: bash

   claude mcp add --transport stdio --scope user pymechanical-mcp -- \
     uvx --index-strategy unsafe-best-match \
     --from git+https://github.com/ansys/pymechanical-mcp \
     ansys-mechanical-mcp

Visual Studio Code
------------------

Add this to ``.vscode/mcp.json``:

.. code-block:: json

   {
     "servers": {
       "pymechanical-mcp": {
         "type": "stdio",
         "command": "uvx",
         "args": [
           "--index-strategy", "unsafe-best-match",
           "--from", "git+https://github.com/ansys/pymechanical-mcp",
           "ansys-mechanical-mcp"
         ]
       }
     }
   }

Local development install:

.. code-block:: json

   {
     "servers": {
       "pymechanical-mcp": {
         "type": "stdio",
         "command": ".venv/Scripts/python",
         "args": ["-m", "ansys.mechanical.mcp"],
         "env": {
           "FASTMCP_LOG_LEVEL": "DEBUG"
         }
       }
     }
   }

Use ``.venv/bin/python`` on Linux/macOS.

HTTP transport configuration:

.. code-block:: json

   {
     "servers": {
       "pymechanical-mcp": {
         "type": "http",
         "url": "http://127.0.0.1:8080"
       }
     }
   }

Start the server separately for HTTP mode:

.. code-block:: bash

   ansys-mechanical-mcp --transport http --http-host 127.0.0.1 --http-port 8080

Claude Desktop
--------------

Edit ``claude_desktop_config.json``:

.. code-block:: json

   {
     "mcpServers": {
       "pymechanical-mcp": {
         "command": "uvx",
         "args": [
           "--index-strategy", "unsafe-best-match",
           "--from", "git+https://github.com/ansys/pymechanical-mcp",
           "ansys-mechanical-mcp"
         ]
       }
     }
   }

Advanced startup options
------------------------

Auto-connect on startup:

.. code-block:: json

   {
     "servers": {
       "pymechanical-mcp": {
         "type": "stdio",
         "command": "uvx",
         "args": [
           "--index-strategy", "unsafe-best-match",
           "--from", "git+https://github.com/ansys/pymechanical-mcp",
           "ansys-mechanical-mcp",
           "--connect-on-startup",
           "--ip", "127.0.0.1",
           "--port", "10000"
         ]
       }
     }
   }

Set gRPC transport mode:

.. code-block:: bash

   ansys-mechanical-mcp --transport-mode auto

Enable debug logging:

.. code-block:: bash

   FASTMCP_LOG_LEVEL=DEBUG ansys-mechanical-mcp

Next steps
----------

- Review available capabilities in :doc:`../user_guide/tools_and_capabilities`.
- Follow workflow recommendations in :doc:`../user_guide/best_practices`.
- For containerized deployment, see :doc:`../user_guide/docker`.
