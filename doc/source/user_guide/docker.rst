.. _ref_docker:

Docker deployment
=================

PyMechanical-MCP supports containerized deployment with HTTP transport.
The repository provides:

- ``docker/Dockerfile``
- ``docker/docker-compose.yml``
- ``docker/env.example``

Quick start with Docker Compose
-------------------------------

1. Configure environment values:

   .. code-block:: bash

      cd docker
      cp env.example .env

2. Update ``.env`` values for your Mechanical target and license server.

3. Start services:

   .. code-block:: bash

      docker compose up -d --build

4. The MCP server is available at ``http://localhost:8080`` by default.

5. Follow logs:

   .. code-block:: bash

      docker compose logs -f pymechanical-mcp

Important environment variables
-------------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Variable
     - Default
     - Description
   * - ``PYMECHANICAL_IP``
     - ``mechanical``
     - Mechanical host/IP for gRPC connection.
   * - ``PYMECHANICAL_PORT``
     - ``10000``
     - Mechanical gRPC port.
   * - ``HTTP_HOST``
     - ``0.0.0.0``
     - MCP HTTP bind host.
   * - ``HTTP_PORT``
     - ``8080``
     - MCP HTTP port.
   * - ``CONNECT_ON_STARTUP``
     - ``false``
     - Auto-connect to Mechanical when MCP starts.
   * - ``PYMECHANICAL_TRANSPORT_MODE``
     - ``auto``
     - gRPC mode: ``auto``, ``insecure``, ``mtls``, ``wnua``.
   * - ``ANSYS_GRPC_CERTIFICATES``
     - (unset)
     - Path containing ``ca.crt``, ``client.crt``, ``client.key`` for mTLS.

Local Mechanical connectivity notes
-----------------------------------

- On Windows/macOS Docker Desktop, use ``host.docker.internal`` for a host
  Mechanical instance.
- On Linux, prefer host networking or explicit host IP routing.

VS Code MCP client example (HTTP)
---------------------------------

.. code-block:: json

   {
     "servers": {
       "pymechanical-mcp": {
         "type": "http",
         "url": "http://127.0.0.1:8080"
       }
     }
   }

Limitations
-----------

- Containerizing PyMechanical-MCP does not containerize Ansys Mechanical
  licensing requirements.
- Ensure Mechanical gRPC endpoint and license server are reachable from the
  container network.
