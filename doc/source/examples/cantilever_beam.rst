.. _ref_cantilever_beam:

Cantilever beam
===============

This example demonstrates a static structural workflow for a cantilever beam
subjected to a transverse end load. It covers geometry import, material
assignment, mesh generation, boundary condition setup, solver execution,
and deformation result extraction using PyMechanical-MCP.

Engineering objective
---------------------

Determine the maximum deformation and equivalent stress distribution in a
cantilever beam that is clamped at one end and loaded at the free end with a
transverse point force.

Tool workflow
-------------

1. Connect to or launch Mechanical using ``connect_to_mechanical`` or ``launch_mechanical``.
2. Upload the STEP geometry file using ``upload_file``.
3. Use ``run_python_script`` to assign a structural steel material to the body.
4. Use ``run_python_script`` to generate a mesh with a suitable element size.
5. Apply a fixed support at the clamped end and a force load at the free end using ``run_python_script``.
6. Run the solver using ``solve_analysis``.
7. Export deformation and stress results using ``export_results``.
8. Capture a screenshot of the deformation contour using ``screenshot``.

Simulation
----------

.. only:: html

    .. raw:: html

       <figure style="text-align:center;">
          <video controls muted loop autoplay style="width:80%;">
             <source src="../_static/videos/cantilever_beam.mp4" type="video/mp4">
             Your browser does not support the video tag.
          </video>
          <figcaption>Cantilever beam deformation and stress simulation</figcaption>
       </figure>

.. note::
   The simulation video is added when available.

