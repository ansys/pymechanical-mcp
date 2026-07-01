Configuration
=============

PyMechanical-MCP can be configured through CLI startup flags and selected
environment variables.

CLI startup flags
-----------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Flag
     - Description
   * - ``--transport stdio|http``
     - MCP transport (default ``stdio``).
   * - ``--http-host`` / ``--http-port``
     - HTTP bind address and port when ``--transport http`` is used.
   * - ``--ip`` / ``--port``
     - Mechanical endpoint used by ``connect_to_mechanical`` or
       ``--connect-on-startup``.
   * - ``--connect-on-startup``
     - Attempts to connect during MCP startup and locks lifecycle tools.
   * - ``--transport-mode``
     - gRPC mode: ``auto``, ``insecure``, ``mtls``, or ``wnua``.
   * - ``--certs-dir``
     - Path to mTLS certificates directory (``ca.crt``, ``client.crt``,
       ``client.key``).
   * - ``--cors-origins``
     - Comma-separated allowed origins for HTTP transport.
   * - ``--on-aali``
     - Enables AALI-specific runtime behavior.

Environment variables
---------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``PYMECHANICAL_TRANSPORT_MODE``
     - Default gRPC mode when ``--transport-mode`` is not passed.
   * - ``ANSYS_GRPC_CERTIFICATES``
     - Default certificate directory when ``--certs-dir`` is not passed.
   * - ``PYMECHANICAL_IP`` / ``PYMECHANICAL_PORT``
     - Preferred endpoint values in containerized deployments.
   * - ``FASTMCP_LOG_LEVEL``
     - Controls MCP server logging verbosity.

Connection-lock behavior
------------------------

When ``--connect-on-startup`` is enabled, the server attempts to connect to
Mechanical during startup and then disables:

- ``launch_mechanical``
- ``connect_to_mechanical``
- ``disconnect_from_mechanical``

This keeps the active session stable for clients that expect a fixed
connection lifecycle.

Next steps
----------

- For install and startup examples, see :doc:`../getting_started/installation`.
- For client setup, see :doc:`../getting_started/ide_configuration`.