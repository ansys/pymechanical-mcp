.. _ref_examples:

Examples
========

.. toctree::
   :maxdepth: 2

   examples_gallery

This repository includes ready-to-run demo workflows under the
``examples/`` directory.

Recommended demos
-----------------

- ``examples/cantilever_beam``: Static structural beam workflow
- ``examples/plate_with_hole``: Stress concentration study
- ``examples/bracket_modal``: Modal analysis with mode-shape visualization

Typical execution pattern
-------------------------

1. Start PyMechanical-MCP and connect/launch Mechanical.
2. Upload STEP geometry with ``upload_file``.
3. Use scripting tools to set up materials, mesh, and loads.
4. Solve with ``solve_analysis``.
5. Capture outputs using ``export_results`` and ``screenshot``.

These examples are designed for live MCP demos and can be adapted into
customer-specific automation prompts.
