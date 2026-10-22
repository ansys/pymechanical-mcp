.. _ref_tools_and_capabilities:

Tools and capabilities
======================

Tool availability model
-----------------------

PyMechanical-MCP uses connection-aware visibility.

- **Offline-capable tools** are available before any Mechanical session.
- **Live-session tools** use ``REQUIRES_MECHANICAL_TAG`` and remain hidden
  until you successfully call ``launch_mechanical`` or ``connect_to_mechanical``.
- If you use ``--connect-on-startup``, live-session tools are available
  immediately, and PyMechanical-MCP locks the connection lifecycle tools.
- If you use ``--static-tools``, all tools (including live-session tools) are
  visible from startup. Calling a live-session tool before connecting returns
  a clear "No Mechanical connection available" message instead of the tool
  being hidden. Use this if your MCP client does not reliably refresh its
  tool list when the server dynamically enables tools. See
  :doc:`configuration` for details.

Always available (before connection)
------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Tool
     - Description
   * - ``check_mechanical_installed``
     - Verify that Mechanical is installed and discoverable.
   * - ``check_mechanical_status``
     - Inspect connection state, ownership, transport, pending operations, and
       persistent Python diagnostics, including when disconnected. Replaces
       ``get_session_diagnostics`` in v0.3.0.
   * - ``list_mechanical_instances``
     - List running Mechanical processes.
   * - ``launch_mechanical``
     - Start a new Mechanical session. GUI is preferred by default, and batch mode remains available.
   * - ``connect_to_mechanical``
     - Attach to an existing Mechanical instance.
   * - ``get_guidelines_for``
     - Return workflow guidance by topic.

Available after connection
--------------------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Tool
     - Description
   * - ``disconnect_from_mechanical``
     - End the session. Closes an instance started by ``launch_mechanical`` and leaves an attached instance running.
   * - ``run_python_code``
     - Execute Python snippets in the persistent session.
   * - ``create_custom_plot``
     - Produce custom plots from analysis data.
   * - ``clear_mechanical``
     - Clear the current model (unsaved work is lost). Mechanical and the connection stay open.
   * - ``run_python_script``
     - Execute a Mechanical script string or read one from a local file with ``file_path``.
   * - ``check_script``
     - Check a script without running it: compile it in the connected
       scripting engine and look up its API names in the live session.
   * - ``find_objects``
     - Find Outline objects by name, category, or parent and return their
       stable object IDs.
   * - ``describe_api``
     - With ``object_id``, return the API properties of an object with current
       values, units, and allowed values for enumerations. With ``query``,
       search the API of the connected release by keyword.
   * - ``preview_property_change``
     - Validate a new property value and show the current and proposed values
       without changing the model. Returns a single-use token.
   * - ``apply_property_change``
     - Apply a previewed change. The change is rejected if the token was
       already used, has expired, or the value changed since the preview.
   * - ``save_project``
     - Save active project.
   * - ``open_project``
     - Open an existing MECHDB project.
   * - ``upload_file``
     - Upload local file to Mechanical working directory.
   * - ``download_file``
     - Download file from Mechanical working directory.
   * - ``download_project``
     - Download all supported project files, optionally filtered by extension.
   * - ``list_files``
     - List files in working directory.
   * - ``solve_analysis``
     - Solve the analysis selected by ``analysis_index``. Set ``wait=False`` to
       return as soon as the solve starts.
   * - ``get_model_info``
     - Return a structured model summary: geometry and mesh counts, active mesh
       metric, named selections, materials, unit system, analyses, and boundary
       conditions.
   * - ``get_results_summary``
     - Return solved result minima, maxima, and averages with units, without
       exporting files.
   * - ``screenshot``
     - Capture the ``model``, ``mesh``, or ``result`` view.
   * - ``get_mechanical_logs``
     - Retrieve Mechanical logs for diagnostics.
   * - ``export_results``
     - Export result objects and artifacts for the analysis selected by
       ``analysis_index``.

.. note::
  When you run with ``--connect-on-startup``, PyMechanical-MCP disables
  the ``launch_mechanical``, ``connect_to_mechanical``, and
  ``disconnect_from_mechanical`` tools by design.

Guideline topics
----------------

``get_guidelines_for`` supports these topic values:

- ``workflow``
- ``geometry``
- ``materials``
- ``meshing``
- ``analysis_setup``
- ``boundary_conditions``
- ``solution``
- ``postprocessing``
- ``named_selections``
- ``general``

Tool set discovery resource
---------------------------

PyMechanical-MCP exposes ``toolsets://definition`` for service-side discovery.
The payload groups tools into:

- lifecycle
- scripting
- project-management
- file-management
- simulation
- inspection
- object-discovery
- property-changes
- results
- guidelines

This resource is read-only metadata. It does not modify runtime behavior.

Object discovery and safe changes
---------------------------------

These tools read the connected session, so their results match the installed
Mechanical release, including releases newer than the bundled API reference.

- ``find_objects`` returns stable object IDs. Use IDs rather than names, which
  can repeat, or positions, which change when objects are added.
  Results are in Outline order. ``offset`` skips filtered matches, not arbitrary
  tree nodes. Follow ``next_offset`` until null with unchanged filters to retrieve
  more than 1000 objects. Restart if ``result_fingerprint`` changes: pagination is
  not a transactional snapshot of an editable model.
- ``describe_api`` with ``object_id`` lists properties shown in the Details
  view by default. Set ``details_only=False`` for every public API property.
- ``describe_api`` with ``query`` searches API types, properties, methods, and
  enumeration members by keyword, such as ``"element size"``. A query that names
  a type, such as ``"FixedSupport"``, also lists all its members. Use it to find
  real API names before writing a script.
  Search results include concise summaries from XML documentation beside the
  reflected assemblies, where available. Exact ``Type.Member`` queries such as
  ``"Analysis.Solve"`` return parameters, remarks and examples with source and
  truncation metadata. Documentation is read on the Mechanical host, requires no
  internet access and matches that installation. Missing or boilerplate XML does
  not prevent reflection; the response reports its availability. A connection is
  still required. No newest-installed stubs or online ``latest`` docs are substituted.
- ``preview_property_change`` checks values strictly against the property type.
  Booleans must be ``true`` or ``false``, integers must fit the property range,
  enumeration values must be exact member names, and quantities must be strings such
  as ``"10 [mm]"`` whose unit is compatible with the current value.
- ``apply_property_change`` applies only a matching, unused, unexpired preview
  whose current value has not changed, and then reads the value back.

A preview is not a sandbox. Applied changes are not undone automatically, so
save the project first if you need a restore point. Properties of other types,
such as geometry scoping or tabular data, still require ``run_python_script``.

``check_script`` compiles a script in the connected scripting engine without
running it. Remote Mechanical sessions, including 2026 R1 and 2027 R1, run
IronPython 2.7, so syntax such as f-strings is reported. It then looks up names
such as ``Model.Mesh.ElementSize`` in the live session to find misspelled or
nonexistent members. The check reads properties but never calls methods. A passing
check does not validate argument types, values, or the model state at run time.

Large-model summaries
---------------------

``get_model_info`` defaults to ``max_items=50`` entries per named-selection,
material, analysis and boundary-condition list. Existing list formats remain;
``collection_info`` reports total counts, returned counts and truncation.
``max_items=0`` returns counts without those lists; ``max_items=None`` explicitly
returns all entries and can produce a very large response. Use filtered
``find_objects`` pages for large models instead of repeatedly loading all names.
Geometry remains counts-only, including ``body_counts_by_type`` and
``suppression_counts``. Line bodies are reported as Line, not assumed to be beams.
Object counts and fingerprints are discovery aids, not engineering validation.

Example workflows
-----------------

Static structural run
~~~~~~~~~~~~~~~~~~~~~

#. ``check_mechanical_status``
#. ``launch_mechanical`` or ``connect_to_mechanical``
#. ``upload_file`` (geometry)
#. ``run_python_script`` (import geometry, assign material, and mesh)
#. ``run_python_script`` (apply boundary conditions and loads)
#. ``solve_analysis``
#. ``export_results`` and ``screenshot``

Modal analysis
~~~~~~~~~~~~~~

#. Connect to Mechanical.
#. Import the model and define fixed supports.
#. Create modal analysis settings with script tools.
#. Run ``solve_analysis``.
#. Use ``create_custom_plot`` for mode-shape reporting.

Change a setting with a preview
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. ``find_objects`` with ``category="Mesh"`` to get the mesh object ID
#. ``describe_api`` with the object ID to read ``ElementSize`` and its unit
#. ``preview_property_change`` with ``value="2 [mm]"``
#. Confirm the preview with the user
#. ``apply_property_change`` with the returned ``preview_token``

Checks after solving
~~~~~~~~~~~~~~~~~~~~~

#. ``get_model_info`` for verifying solved state
#. ``get_mechanical_logs`` for warnings and errors
#. ``run_python_code`` for custom data extraction
#. ``export_results`` for report artifacts

Feature reference
-----------------

For complete parameter signatures and return values for all tools, see
:doc:`/api/index`.

Next steps
----------

- See :doc:`best_practices` for recommendations on using the tools effectively.
- Explore :doc:`/examples/workflows/usage_examples_index` for end-to-end workflow examples.
- For startup and environment options, see :doc:`configuration`.
