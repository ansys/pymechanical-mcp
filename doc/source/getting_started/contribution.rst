.. _ref_contributing:

============
Contributing
============

You can contribute to PyMechanical-MCP in several ways:

- Answer discussions on the `GitHub Discussions page <https://github.com/ansys/pymechanical-mcp/discussions>`_
- Report defects or request features on the `GitHub Issues page <https://github.com/ansys/pymechanical-mcp/issues>`_
- Submit pull requests with bug fixes, new features, or documentation updates

Before contributing, review the PyAnsys developer guidance:

- `Contributing <https://dev.docs.pyansys.com/how-to/contributing.html>`_
- `Coding style <https://dev.docs.pyansys.com/coding-style/index.html>`_

Development setup
=================

.. code-block:: bash

   git clone https://github.com/ansys/pymechanical-mcp.git
   cd pymechanical-mcp
   pip install -e ".[dev]"
   pre-commit install

Run tests:

.. code-block:: bash

   pytest -q

Run linters:

.. code-block:: bash

   pre-commit run --all-files

Build docs:

.. code-block:: bash

   python -m sphinx -W -b html doc/source doc/_build/html

Adding a new tool
=================

When adding ``@app.tool(...)`` entries in ``src/ansys/mechanical/mcp/tools.py``:

1. If the tool requires an active Mechanical session, tag it with
   ``REQUIRES_MECHANICAL_TAG``.

   .. code-block:: python

      from ansys.mechanical.mcp.tools import REQUIRES_MECHANICAL_TAG

      @app.tool(tags={REQUIRES_MECHANICAL_TAG})
      def my_new_tool(ctx: Context, ...) -> str:
          ...

2. If the tool must be available before connection, do not tag it with
   ``REQUIRES_MECHANICAL_TAG`` and update the pre-connection visibility tests.

3. Add the tool to ``src/ansys/mechanical/mcp/toolsets.py`` so it appears in
   the ``toolsets://definition`` discovery resource.

4. Document the tool in :doc:`../user_guide/tools_and_capabilities`.

5. If the tool requires Mechanical scripting patterns, update
   ``src/ansys/mechanical/mcp/contexts.py`` guidance where appropriate.