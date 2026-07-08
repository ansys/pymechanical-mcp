.. _ref_bracket_modal:

Bracket modal analysis
======================

This example demonstrates a modal analysis workflow for a mechanical bracket.
It shows how to use PyMechanical-MCP to set up and solve a free-vibration
problem and extract the natural frequencies and mode shapes.

Engineering objective
---------------------

Determine the first six natural frequencies and corresponding mode shapes of a
bracket assembly. Identify potential resonance risks and visualize dominant
deformation patterns for each mode.

Tool workflow
-------------

1. Connect to or launch Mechanical using ``connect_to_mechanical`` or ``launch_mechanical``.
2. Upload the bracket assembly geometry using ``upload_file``.
3. Use ``run_python_script`` to assign material properties to all bodies.
4. Use ``run_python_script`` to insert a Modal analysis system and set the number of modes to extract.
5. Apply fixed supports to the bolt-hole faces using ``run_python_script``.
6. Generate a mesh and run the solver using ``solve_analysis``.
7. Export natural frequencies and mode-shape images using ``export_results``.
8. Capture screenshots of selected mode shapes using ``screenshot``.

Simulation
----------

.. only:: html

    .. raw:: html

       <figure style="text-align:center;">
          <video controls muted loop autoplay style="width:80%;">
             <source src="../_static/videos/bracket_modal.mp4" type="video/mp4">
             Your browser does not support the video tag.
          </video>
          <figcaption>Bracket modal analysis mode-shape visualization</figcaption>
       </figure>

.. note::
   The simulation video is added when available.
