.. _ref_best_practices:

Best practices
==============

Session management
------------------

Reuse the same Mechanical connection across a workflow whenever possible.
Repeated launch/connect cycles increase runtime and can create confusion in
stateful workflows.

- Call ``check_mechanical_status`` before starting each major step.
- Use its diagnostics when investigating persistent Python startup or connection issues.
- Use ``connect_to_mechanical`` if a compatible instance already exists.
- Use ``disconnect_from_mechanical`` for clean shutdowns.

Scripting strategy
------------------

Use short, focused script calls rather than very large monolithic scripts.
This improves observability and error recovery.

- Use ``run_python_script`` for Mechanical API-heavy commands.
- Use ``run_python_code`` for lightweight Python processing and orchestration.
- Pass ``file_path`` to ``run_python_script`` when a script lives on disk.

For long setup scripts:

- Validate geometry import and named selections early.
- Save checkpoints with ``save_project`` after expensive setup steps.
- Keep scripts idempotent where possible to support reruns.

Model setup quality
-------------------

- Set units explicitly before defining loads and material parameters.
- Verify named selection scopes before applying boundary conditions.
- Check mesh quality and element sizing before solving.
- Confirm material assignment for every relevant body.

Solver and results
------------------

- Solve only after confirming analysis settings and boundary condition completeness.
- Use ``get_model_info`` after setup and after solve to validate state.
- Use ``describe_api`` to confirm API names, values, and units instead
  of guessing them, and ``check_script`` before running a new script.
- Change single properties with ``preview_property_change`` and
  ``apply_property_change`` so that the user sees each change before it is
  applied.
- Export only needed result objects to reduce file churn.
- Capture screenshots at key milestones for traceability.

File transfer hygiene
---------------------

- Use ``upload_file`` for all client-side artifacts (geometry and scripts).
- Keep working directory contents organized (prefix or suffix by workflow).
- Retrieve only required artifacts with ``download_file``.
- Use ``download_project`` when a complete project archive is required.

AI workflow guidance
--------------------

Call ``get_guidelines_for`` once per unfamiliar topic and reuse its guidance for
the same release and scripting engine. It returns bundled, concise API patterns
with official documentation links and MCP execution notes, not solver presets or
an automatically fetched skill. The linked examples may use embedding mode;
pass script bodies rather than client wrappers to the remote script tool.
Use ``describe_api`` for version-matched API metadata and installed documentation.
Read ``collection_info`` before treating a model-summary list as complete, and
prefer filtered ``find_objects`` pages to unlimited large-assembly responses.

Next steps
----------

- See :doc:`tools_and_capabilities` for a complete list of available tools.
- Browse :doc:`/examples/workflows/usage_examples_index` for end-to-end workflow examples.
- See :doc:`configuration` for startup and transport options.
