.. _ref_cantilever_beam:

Cantilever beam
===============

This example demonstrates a static structural analysis of a cantilever beam
using PyMechanical-MCP. The geometry is a 200 mm x 20 mm x 10 mm rectangular beam.

Engineering objective
---------------------

Determine the maximum deformation and equivalent stress distribution in a cantilever
beam clamped at one end and loaded at the free end with a transverse pressure.
Confirm that the maximum deformation occurs at the free end and stress concentrates
at the fixed support.

Geometry
--------

- **File**: `beam.step`
- **Dimensions**: 200 mm x 20 mm x 10 mm rectangular beam

Setup requirements
------------------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Setting
     - Value
   * - Material
     - Structural Steel (default)
   * - Mesh
     - Default mesh, element size 5 mm
   * - Fixed support
     - YZ face at X = -100 mm
   * - Pressure load
     - 1,000,000 pascals on the top face (XY face at Z = +5 mm)

Tool workflow
-------------

1. Connect to or launch Mechanical using `connect_to_mechanical` or `launch_mechanical`.
2. Upload `beam.step` using `upload_file`.
3. Assign Structural Steel using `run_python_script`.
4. Generate a 5 mm element size mesh using `run_python_script`.
5. Apply a fixed support at the clamped face using `run_python_script`.
6. Apply a 1,000,000 pascal pressure on the top face using `run_python_script`.
7. Run the solver using `solve_analysis`.
8. Add Total Deformation and Equivalent Stress results using `run_python_script`.
9. Capture a screenshot of the equivalent stress contour using `screenshot`.

Expected outcome
----------------

- Maximum deformation at the free end of the beam.
- Stress concentration at the fixed support.
- Stress gradient from low (blue) at the free end to high (red) at the fixed support.

Prompt example
--------------

The following prompt drives the complete workflow end-to-end:

.. code-block:: text

   Perform a static structural analysis of a cantilever beam.
   Upload the geometry file beam.step.

   - Material: Structural Steel (default)
   - Mesh: default mesh with element size 5 mm
   - Fixed support on the YZ face at X = -100 mm
  - Pressure load of 1,000,000 pascals on the top face (XY face at Z = +5 mm)
  - Results: Total Deformation and equivalent stress
  - Take a screenshot of the equivalent stress result
