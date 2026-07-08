.. _ref_contributing:

==========
Contribute
==========

You can contribute to PyMechanical-MCP in several ways:

- Answer discussions on the `GitHub Discussions page <https://github.com/ansys/pymechanical-mcp/discussions>`_
- Report defects or request features on the `GitHub Issues page <https://github.com/ansys/pymechanical-mcp/issues>`_
- Submit pull requests with bug fixes, new features, or documentation updates

Before contributing, review the `PyAnsys developer's guide <https://dev.docs.pyansys.com/>`_, paying
particular attention to the guidance on these pages:

- `Contributing <https://dev.docs.pyansys.com/how-to/contributing.html>`_
- `Coding style <https://dev.docs.pyansys.com/coding-style/index.html>`_
- `Branch-naming conventions <https://dev.docs.pyansys.com/how-to/contributing.html#branch-naming-conventions>`_

Development setup
=================

Clone and install in editable mode with development dependencies:

.. code-block:: bash

   git clone https://github.com/ansys/pymechanical-mcp.git
   cd pymechanical-mcp
   pip install -e ".[dev]"
   pre-commit install

Run tests:

.. code-block:: bash

   # Fast unit tests (default CI matrix path)
   pytest -m "not integration"

   # Integration tests (requires Mechanical)
   pytest -m integration

Run linters:

.. code-block:: bash

   pre-commit run --all-files

Build documentation:

.. code-block:: bash

   python -m sphinx -W -b html doc/source doc/_build/html

Next steps
==========

- To implement a custom tool, see :doc:`/examples/implementing_a_tool`.
- For an overview of available tools, see :doc:`/user_guide/tools_and_capabilities`.
- For the complete API reference, see :doc:`/api/index`.
