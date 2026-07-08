.. _ref_plate_with_hole:

Plate with hole
===============

This example demonstrates a stress concentration workflow for a flat plate
with a central circular hole under uniaxial tension. It shows how to use
PyMechanical-MCP to automate the setup, solve, and postprocess a classic
stress concentration factor problem.

Engineering objective
---------------------

Compute the stress concentration factor for a rectangular plate with a central
circular hole subjected to a uniform tensile load. Compare the maximum principal
stress near the hole to the nominal far-field stress.

Tool workflow
-------------

1. Connect to or launch Mechanical using ``connect_to_mechanical`` or ``launch_mechanical``.
2. Upload the plate geometry using ``upload_file``.
3. Use ``run_python_script`` to assign a structural steel material to the plate.
4. Use ``run_python_script`` to generate a refined mesh around the hole.
5. Apply a fixed support on one face and a pressure load on the opposite face using ``run_python_script``.
6. Run the solver using ``solve_analysis``.
7. Export maximum principal stress and total deformation results using ``export_results``.
8. Capture a contour plot of the stress distribution using ``screenshot``.

Simulation
----------

.. only:: html

    .. raw:: html

       <figure style="text-align:center;">
          <video controls muted loop autoplay style="width:80%;">
             <source src="../_static/videos/plate_with_hole.mp4" type="video/mp4">
             Your browser does not support the video tag.
          </video>
          <figcaption>Plate with hole stress concentration simulation</figcaption>
       </figure>

.. note::
   The simulation video above will be added when available.

