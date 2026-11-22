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

Activity tracking and conflicting submissions
---------------------------------------------

Mechanical can be busy with work that PyMechanical's client-side ``busy`` flag
does not cover, such as GUI operations or a solve that continues after
``solve_analysis(wait=False)`` has returned. To avoid conflicting work:

- One mutating MCP operation is allowed at a time across all connected clients.
  The tools ``run_python_script``, ``solve_analysis``, ``export_results``,
  ``save_project``, ``open_project``, ``clear_mechanical``, and
  ``apply_property_change`` return an ``operation_in_progress`` error when
  another one is still active. The error names the active operation and tells
  you to poll ``check_mechanical_status``.
- ``check_mechanical_status`` returns an additional ``activity`` block with
  ``state`` (``idle``, ``busy``, ``unknown``, or ``disconnected``), the ``source``
  of that observation, the active operation's identity (``operation_id``,
  ``kind``, elapsed time, and requesting client), the last completed operation
  and its result, and actionable ``guidance``. Existing status fields are
  unchanged.
- When activity is ``busy`` or ``unknown``, status checks stay responsive: the
  tool returns the activity block without running detailed model-info scripts
  inside Mechanical.
- ``unknown`` is deliberately distinct from ``idle``. If an activity probe
  times out or is unavailable, the server never assumes the application is
  idle, and it never automatically repeats a mutation after an uncertain
  outcome. Completed operation results are retained for a bounded history so a
  client that timed out or disconnected can recover them.
- The optional ``DS.Script.progressBarIsInUse()`` probe is off by default.
  Enable it with ``PYMECHANICAL_MCP_PROGRESS_PROBE=1`` only after validating it
  on your Mechanical release and launch mode. Live checks on the tested 2026 R1
  installation returned a usable ``False`` at idle but did **not** report a
  manually started JScript progress bar as busy, so the probe is not relied on
  for conflict detection. Unsupported releases and headless sessions report
  ``unsupported`` or ``unknown`` without breaking execution.

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
       persistent Python diagnostics, including when disconnected. Also reports
       the activity state, active and last operation identity, and polling
       guidance. Replaces ``get_session_diagnostics`` in v0.3.0.
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
       conditions. Lists are limited previews with total counts and truncation
       information.
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
  To retrieve more matches, set ``offset`` to the returned ``next_offset`` until
  it is null. Keep filters unchanged and restart if ``result_fingerprint`` changes.
  Each page scans the current Outline tree; paging is not a saved model snapshot.
- ``describe_api`` with ``object_id`` lists properties shown in the Details
  view by default. Set ``details_only=False`` for every public API property.
- ``describe_api`` with ``query`` searches API types, properties, methods, and
  enumeration members by keyword, such as ``"element size"``. A query that names
  a type, such as ``"FixedSupport"``, also lists all its members. Use it to find
  real API names before writing a script.
  Results include installed API documentation where available. An exact query,
  such as ``"Analysis.Solve"``, includes available parameter descriptions, remarks,
  and examples, with source and truncation information. Help comes from the
  connected Mechanical installation without internet access. If documentation is
  unavailable, API names and signatures are still returned.
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
material, analysis and boundary-condition list. Check ``collection_info`` for
total counts, returned counts, truncation, and read errors. A null total means
the collection could not be counted.

- Set ``max_items=0`` for counts without list entries.
- Increase ``max_items`` for a larger preview, up to 1000 entries per list.
- Set ``max_items=None`` (``null`` in MCP arguments) for full lists; responses
  can be large.
- Use filtered ``find_objects`` pages to locate objects in large models.

Geometry is reported as counts by body type (``body_counts_by_type``) and
suppression state (``suppression_counts``), without listing body names.
These counts describe the model; they do not validate its engineering setup.

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
#. Import the model and set materials and supports for the intended analysis.
#. Create a modal analysis and configure mode extraction with script tools.
#. Run ``solve_analysis``.
#. Add and evaluate modal results with ``run_python_script``.
#. Use ``screenshot`` or ``export_results`` to report mode shapes.

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
#. ``get_results_summary`` for result values and units
#. ``run_python_code`` for processing exported data
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
