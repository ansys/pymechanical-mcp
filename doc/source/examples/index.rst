.. _ref_examples:

========
Examples
========


.. grid:: 2 2 3 3
    :gutter: 1 2 3 3
    :padding: 1 2 3 3

    .. grid-item-card:: Cantilever beam
        :link: cantilever_beam
        :link-type: doc

        Static structural beam workflow

    .. grid-item-card:: Plate with hole
        :link: plate_with_hole
        :link-type: doc

        Stress concentration study

    .. grid-item-card:: Bracket modal analysis
        :link: bracket_modal
        :link-type: doc

        Modal analysis with mode-shape visualization


Typical execution pattern:

1. Start PyMechanical-MCP and connect/launch Mechanical.
2. Upload STEP geometry with ``upload_file``.
3. Use scripting tools to set up materials, mesh, and loads.
4. Solve with ``solve_analysis``.
5. Capture outputs using ``export_results`` and ``screenshot``.

These examples are designed for live MCP demos and can be adapted into
customer-specific automation prompts.

.. toctree::
   :hidden:

   cantilever_beam
   plate_with_hole
   bracket_modal
