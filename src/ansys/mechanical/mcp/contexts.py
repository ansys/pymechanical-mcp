# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Mechanical workflow guidance, scripting examples, and MCP execution notes."""

from typing import Literal

from ansys.mechanical.mcp import app

GuidelinesContent = Literal[
    "workflow",
    "geometry",
    "materials",
    "meshing",
    "analysis_setup",
    "boundary_conditions",
    "solution",
    "postprocessing",
    "named_selections",
    "general",
]

_DOCS = "https://mechanical.docs.pyansys.com/version/stable"
_EXAMPLES = _DOCS + "/examples/gallery_examples/01_basic/"
_SCRIPTING = _DOCS + "/user_guide/scripting/overview.html"


def _reference(text: str, example: str | None = None) -> str:
    source = _EXAMPLES + example + ".html" if example else _SCRIPTING
    return text.strip() + (
        "\n\nOfficial reference: " + source + "\n"
        "Patterns use remote Mechanical script bodies. Linked examples may use embedding "
        "or another release; describe_api provides connected-release API help. "
        "References are links; this tool never fetches links."
    )


def get_guidelines_for_workflow_overview() -> str:
    """Return the simulation workflow and Mechanical execution model."""
    return _reference("""# Mechanical Simulation Workflow Overview

## Workflow Steps
1. Preprocessing: inspect or import geometry, assign materials, generate the mesh.
2. Analysis Setup: select the analysis, configure settings, apply scoped loads/supports.
3. Solution: solve and review status, application messages, and solver output.
4. Postprocessing: add or reuse results, evaluate, inspect values, and export.

Existing units, materials, analyses and results provide context for the next step.
check_mechanical_status and get_model_info describe the current session/model.

## PyMechanical Architecture and API Entry Points
PyMechanical supports remote sessions and embedding. This MCP sends script bodies
to the connected Mechanical process through run_python_script. Inside that process:
- ExtAPI: the main API entry point.
- DataModel: Outline objects, CAD and mesh entities.
- Model: the Model object from the Outline.
- Tree: the Outline; Graphics: the 3D graphics engine.

run_python_code runs in separate external CPython, without these Mechanical objects.
Embedding examples using App/globals need adaptation; the underlying model APIs are shared.

## Units and Model Inspection
get_model_info reports unit_system. Quantity("5 [mm]") carries an explicit unit;
ExtAPI.Application.ActiveUnitSystem controls the active display/input unit system.
Confirm the intended units rather than resetting an existing project automatically.

Model-summary lists are previews. find_objects returns object IDs for specific scopes;
set offset to next_offset for more pages and restart if result_fingerprint changes.
Object IDs are valid only while the objects exist.

## Transactions and Checkpoints
Transaction() defers background updates during bulk edits; it is not validation or rollback.
Save checkpoints with save_project before destructive changes or expensive setup steps.
""")


def get_guidelines_for_geometry_import() -> str:
    """Return geometry import and remote-file execution notes."""
    return _reference(
        """# Geometry Import in Mechanical

## Supported Geometry Formats
STEP (.stp/.step), IGES, Parasolid, DesignModeler and native CAD files need an
available reader and the appropriate license.

## Uploading and Importing Geometry
The path must exist on the Mechanical host. upload_file places a local file in the
project directory and reports its file name. Set file_name to that base name, or
to an existing absolute host path, before sending this body to run_python_script:
```python
import os
remote_path = os.path.join(ExtAPI.DataModel.Project.ProjectDirectory, file_name)
geometry_import = Model.GeometryImportGroup.AddGeometryImport()
preferences = Ansys.ACT.Mechanical.Utilities.GeometryImportPreferences()
preferences.ProcessNamedSelections = True
preferences.ProcessCoordinateSystems = True
import_format = Ansys.Mechanical.DataModel.Enums.GeometryImportPreference.Format.Automatic
geometry_import.Import(remote_path, import_format, preferences)
```

## Inspecting Imported Geometry
get_model_info reports recursive body counts/types; find_objects(category="Body")
returns body IDs. Bodies can be nested under Parts, so Geometry.Children is not a body list.
An ID from find_objects is an Outline object ID, not a GeoData face/edge ID.
Named selections or explicitly constructed selection information provide geometry scopes.

Check import messages with get_mechanical_logs and verify bodies, dimensions, named
selections and coordinate systems. Imports can replace geometry and invalidate scopes;
inspect an existing model before reimporting. Large assemblies take longer to import.
""",
        "bolt_pretension",
    )


def get_guidelines_for_materials() -> str:
    """Return material availability, assignment, and property checks."""
    return _reference(
        """# Material Definition in Mechanical

## Engineering Data and Custom Materials
Materials come from Engineering Data or imported material files. get_model_info and
find_objects(category="Material") list what exists. "Structural Steel" and "Aluminum
Alloy" are common names, not a guarantee that a material is loaded in this project.
Custom materials must be defined in Engineering Data or imported from a compatible
material file on the Mechanical host. body.Material assigns a material; it does not
create a material or define its properties.

## Assigning Materials to Bodies
Set body_id from find_objects(category="Body") and material_name to an available name:
```python
body = DataModel.GetObjectById(body_id)
if body is None:
    raise ValueError("Body no longer exists")
body.Material = material_name
body.Material
```
For several bodies, resolve the intended IDs and use a Transaction for the assignments.
Assigning every body the same material is appropriate only for an intended uniform model.

## Material Properties
- Linear isotropic elasticity: Young's modulus and Poisson's ratio.
- Inertia, modal or gravity loading: density as well as stiffness properties.
- Thermal conduction: conductivity; transient heat storage also needs density and specific heat.
- Thermal stress: thermal expansion and the appropriate reference temperature.
- Plasticity, anisotropy and other models require their own constitutive data.

Verify assignments and required properties before solving. Yield/ultimate strengths
can support a strength assessment; they do not by themselves define a plastic material law.
""",
        "bolt_pretension",
    )


def get_guidelines_for_meshing() -> str:
    """Return mesh generation, control, and quality-check patterns."""
    return _reference(
        """# Mesh Generation in Mechanical

## Generating the Mesh and Reading Statistics
Inspect existing controls first. The sizes below illustrate syntax, not a sizing rule.
```python
mesh = Model.Mesh
mesh.ElementSize = Quantity("5 [mm]")
mesh.GenerateMesh()
print("Nodes: {0}, Elements: {1}".format(mesh.Nodes, mesh.Elements))
```
Mesh.Nodes and Mesh.Elements are integer counts, not collections requiring .Count.

## Local Sizing
Set selection_id to a confirmed named selection appropriate for the sizing scope:
```python
selection = DataModel.GetObjectById(selection_id)
if selection is None:
    raise ValueError("Selection no longer exists")
sizing = Model.Mesh.AddSizing()
sizing.Location = selection
sizing.ElementSize = Quantity("2 [mm]")
```
Generate the mesh after changing controls. Method controls start from AddAutomaticMethod;
Automatic, Tetrahedrons, Hex Dominant, Sweep and MultiZone suit different geometries.
Check Method enums and scope requirements with describe_api rather than forcing one method.

## Mesh Quality and Convergence
get_model_info reports counts and the active mesh metric without changing it.
mesh.MeshMetric selects the metric; Minimum, Maximum, Average and StandardDeviation
refer to that metric. No selected metric means those statistics may be unavailable.

Start with a manageable mesh and refine around relevant gradients, contacts and thin
features. Solid bending regions need adequate through-thickness resolution; shells
may be more appropriate for thin structures. Review mesh warnings and demonstrate
convergence of the quantities of interest. Universal skewness/aspect-ratio cutoffs
or a particular element count do not establish suitability for every analysis.
""",
        "bolt_pretension",
    )


def get_guidelines_for_analysis_setup() -> str:
    """Return analysis creation, settings, modal, and contact guidance."""
    return _reference(
        """# Analysis Setup in Mechanical

## Analysis Types and Existing Analyses
get_model_info reports existing analyses and zero-based indices.
Model.AddStaticStructuralAnalysis creates a static structural analysis;
AddModalAnalysis, AddHarmonicResponseAnalysis and AddTransientStructuralAnalysis
cover common dynamic workflows. AddSteadyStateThermalAnalysis and
AddTransientThermalAnalysis create thermal analyses.

Example creation (use an existing Model.Analyses[analysis_index] when appropriate):
```python
analysis = Model.AddStaticStructuralAnalysis()
settings = analysis.AnalysisSettings
settings.NumberOfSteps = 1
```

## Solver and Nonlinear Controls
Inspect analysis settings with describe_api before changing them. For a static
analysis, set analysis_index, use_large_deflection (bool) and the substep counts first;
choose positive counts with minimum_substeps <= initial_substeps <= maximum_substeps:
```python
settings = Model.Analyses[analysis_index].AnalysisSettings
settings.LargeDeflection = use_large_deflection
settings.AutomaticTimeStepping = AutomaticTimeStepping.On
settings.DefineBy = TimeStepDefineByType.Substeps
settings.InitialSubsteps = initial_substeps
settings.MinimumSubsteps = minimum_substeps
settings.MaximumSubsteps = maximum_substeps
```
LargeDeflection addresses geometry-dependent stiffness, not a universal strain cutoff.
SolverType.Direct is often robust; iterative solvers can save memory for supported,
well-conditioned problems. Model size alone does not determine the best solver.

## Modal Settings
Set mode_count to the required number of modes, with material stiffness/density and
supports chosen for the intended constrained or free-free model:
```python
modal = Model.AddModalAnalysis()
modal.AnalysisSettings.MaximumModesToFind = mode_count
```
Check extraction settings and the actually extracted modes before creating modal results.

## Contacts
Resolve contact regions under Model.Connections by ID rather than tree position.
ContactType (Bonded, Frictional, Frictionless, NoSeparation), friction, formulation,
initial gaps/penetration and sliding assumptions depend on the physical interface.
Review the contact scopes/status before solving; changing a contact type solely to
obtain convergence can change the physical problem.
""",
        "bolt_pretension",
    )


def get_guidelines_for_boundary_conditions() -> str:
    """Return scoped structural and thermal load examples."""
    return _reference(
        """# Boundary Conditions and Loads in Mechanical

## Scoping
Use get_model_info and find_objects for analysis indices and intended scopes.
Named selections make scope reusable, but names can duplicate and IDs can become stale.
Set analysis_index, support_id and load_id to verified structural-analysis/scope IDs:
```python
analysis = Model.Analyses[analysis_index]
support_scope = DataModel.GetObjectById(support_id)
load_scope = DataModel.GetObjectById(load_id)
if support_scope is None or load_scope is None:
    raise ValueError("A selection no longer exists")
```
The following are separate examples, not a prescription to apply every condition.
Confirm the selected entities are nonempty and appropriate for each condition.

## Fixed Support and Pressure
```python
support = analysis.AddFixedSupport()
support.Location = support_scope
pressure = analysis.AddPressure()
pressure.Location = load_scope
pressure.Magnitude.Output.DiscreteValues = [Quantity("1 [MPa]")]
```

## Force Components
Components are fields, not assignable numeric properties. Set Output.DiscreteValues:
```python
force = analysis.AddForce()
force.Location = load_scope
force.DefineBy = LoadDefineBy.Components
force.XComponent.Output.DiscreteValues = [Quantity("0 [N]")]
force.YComponent.Output.DiscreteValues = [Quantity("-1000 [N]")]
force.ZComponent.Output.DiscreteValues = [Quantity("0 [N]")]
```
These values illustrate syntax; coordinate system, direction and magnitude come from the load case.

## Partial Displacement and Other Supports
```python
displacement = analysis.AddDisplacement()
displacement.Location = support_scope
displacement.XComponent.Output.DiscreteValues = [Quantity("0 [mm]")]
displacement.YComponent.Output.DiscreteValues = [Quantity("0 [mm]")]
```
Check which components are free versus prescribed in the Details view.
AddFrictionlessSupport and AddRemoteForce provide other condition types; their
scope and coupling options differ, so inspect their properties with describe_api.

## Thermal Loads
For a thermal analysis, set thermal_index and thermal_scope_id to an intended face scope:
```python
thermal = Model.Analyses[thermal_index]
thermal_scope = DataModel.GetObjectById(thermal_scope_id)
if thermal_scope is None:
    raise ValueError("Thermal selection no longer exists")
convection = thermal.AddConvection()
convection.Location = thermal_scope
convection.FilmCoefficient.Output.DiscreteValues = [Quantity("10 [W m^-2 C^-1]")]
convection.AmbientTemperature.Output.DiscreteValues = [Quantity("22 [C]")]
```
A prescribed temperature is a separate option, using an appropriate thermal scope:
```python
temperature = thermal.AddTemperature()
temperature.Location = thermal_scope
temperature.Magnitude.Output.DiscreteValues = [Quantity("100 [C]")]
```
Time-dependent input/output tables need matching lengths and compatible time/field units.
Static structural models normally need supports/contacts that remove rigid-body motion;
free-free modal analysis is a valid exception. Overconstraint can be as harmful as missing supports.
""",
        "valve",
    )


def get_guidelines_for_solution() -> str:
    """Return solve, status, output-control, and convergence guidance."""
    return _reference(
        """# Solution Phase in Mechanical

## Running the Solution
solve_analysis(analysis_index=..., wait=True) waits for the selected analysis.
wait=False starts asynchronously; a successful start is not a completed solve.
The direct scripting pattern, after confirming analysis_index, is:
```python
analysis = Model.Analyses[analysis_index]
analysis.Solve(True)
str(analysis.Solution.Status)
```
Solve(False) returns before completion. Read Solution.Status in later calls rather
than polling in a loop inside Mechanical. SolutionStatusType.Done indicates completion;
it does not establish engineering validity or absence of warnings.

## Output Controls and Logs
AnalysisSettings.StoreResultsAt controls saved result time points, not solve convergence.
Review get_mechanical_logs(source="messages") for application messages and
source="solve_log" with analysis_index for solve.out. tail_lines and max_chars limit output.
Errors from run_python_script include the Mechanical exception message.

## Diagnosing Convergence
- Confirm mesh generation, material properties, load units and analysis settings.
- Check supports/contacts for rigid-body motion or overconstraint.
- Inspect mesh quality and contact gaps, penetration, sliding and status.
- Consider load ramping and substeps when increments are too large.
- Consider LargeDeflection when deformation changes the stiffness/geometry.
- Review solver messages before changing solver type or the physical model.

Change one suspected cause at a time and compare results and diagnostics. A completed
solve still needs checks against expected behavior, equilibrium and mesh convergence.
""",
        "valve",
    )


def get_guidelines_for_postprocessing() -> str:
    """Return result creation, evaluation, scoping, modal, and export patterns."""
    return _reference(
        """# Postprocessing in Mechanical

## Adding and Evaluating Results
get_results_summary reports solved extrema with units and omits stale values.
Inspect existing results before adding duplicates. For missing structural results,
confirm analysis_index and use these creators as appropriate:
```python
solution = Model.Analyses[analysis_index].Solution
deformation = solution.AddTotalDeformation()
stress = solution.AddEquivalentStress()
strain = solution.AddEquivalentElasticStrain()
solution.EvaluateAllResults()
print("Stress min/max/average: {0}, {1}, {2}".format(
    stress.Minimum, stress.Maximum, stress.Average))
```
The analysis must have solution data. Unsolved, obsolete or failed results are not
valid values; check state and evaluation messages. Other creators include
AddNormalStress, AddMaximumPrincipalStress and AddDirectionalDeformation;
NormalOrientation selects the direction for directional results.

## Scoped Results
With solution from the selected analysis and selection_id for a confirmed named selection:
```python
selection = DataModel.GetObjectById(selection_id)
if selection is None:
    raise ValueError("Selection no longer exists")
scoped_stress = solution.AddEquivalentStress()
scoped_stress.Location = selection
scoped_stress.EvaluateAllResults()
```

## Modal Results
Set modal_index to a solved modal analysis and mode_number to an actually extracted mode:
```python
modal_solution = Model.Analyses[modal_index].Solution
mode_shape = modal_solution.AddTotalDeformation()
mode_shape.Mode = mode_number
mode_shape.EvaluateAllResults()
mode_shape.ReportedFrequency
```
ReportedFrequency is the mode frequency. Modal amplitudes are normalized shapes,
not displacements under a particular service load. Do not assume ten modes were extracted.

## Images and Data Export
screenshot captures the selected view; export_results exports PNG/TXT/both for an
analysis. download_file retrieves files from the Mechanical host.
For direct API export, resolve result_id to an intended evaluated result and set
image_path/text_path to host paths in an existing output directory:
```python
result = DataModel.GetObjectById(result_id)
if result is None:
    raise ValueError("Result no longer exists")
result.Activate()
Graphics.ExportImage(image_path, GraphicsImageExportFormat.PNG)
result.ExportToTextFile(text_path)
```
Always activate the intended result before image export. Solution.Children[0] may
be Solution Information or another non-result object. Assess results against the
physical problem; stress singularities and mesh dependence can distort extrema.
""",
        "valve",
    )


def get_guidelines_for_named_selections() -> str:
    """Return named-selection discovery and worksheet syntax."""
    return _reference(
        """# Named Selections in Mechanical

## Discovering Existing Selections
Find existing scopes with find_objects(category="NamedSelection", name_contains=...).
Set offset to the returned next_offset until null for more matches; previews are
not complete lists. Resolve IDs with DataModel.GetObjectById.

When a name is the only available identifier, verify it is unique:
```python
matches = list(DataModel.GetObjectsByName(selection_name))
if len(matches) != 1:
    raise ValueError("Expected one object named {0}".format(selection_name))
selection = matches[0]
```
Confirm the object is the intended named selection and its entities are nonempty.
Names can duplicate; GetObjectsByName()[0] alone does not establish the intended scope.

## Worksheet-Based Creation
This example finds faces at X = 0; adjust the entity, coordinate and tolerance to the geometry:
```python
selection = Model.AddNamedSelection()
selection.ScopingMethod = GeometryDefineByType.Worksheet
criterion = Ansys.ACT.Automation.Mechanical.NamedSelectionCriterion()
criterion.Active = True
criterion.Action = SelectionActionType.Add
criterion.EntityType = SelectionType.GeoFace
criterion.Criterion = SelectionCriterionType.LocationX
criterion.Operator = SelectionOperatorType.Equal
criterion.Value = Quantity("0 [mm]")
selection.GenerationCriteria.Add(criterion)
selection.Generate()
selection.Name = "FixedEnd"
```

## Criteria and Reuse
SelectionType.GeoFace/GeoEdge/GeoVertex/GeoBody select entity types;
SelectionCriterionType.LocationX/Y/Z, Size, Type and Name provide common filters.
Check supported criterion/entity/operator combinations and units with describe_api.
Generated scopes can be assigned to loads, supports, sizing controls and results
through Location when the receiving object supports that scope.

Use descriptive names and regenerate/check scopes after geometry changes. Worksheet
criteria can survive updates, but a persistent name does not guarantee the same
entities remain selected. Duplicate names and empty selections require resolution.
""",
        "topology_optimization_cantilever_beam",
    )


def get_guidelines_for_general_rules() -> str:
    """Return scripting compatibility, units, transactions, and validation guidance."""
    return _reference("""# General Rules for MCP Scripts

## Script Execution and Return Values
Pass the script body to run_python_script, not a mechanical.run_python_script wrapper.
The last expression is returned as text; an assignment returns empty text.
Script globals persist between calls. For structured output:
```python
import json
payload = {'version': ExtAPI.DataModel.Project.ProductVersion,
           'mesh_nodes': Model.Mesh.Nodes, 'mesh_elements': Model.Mesh.Elements}
json.dumps(payload, ensure_ascii=False)
```
ensure_ascii=False preserves non-ASCII names in IronPython. Keep output bounded and
avoid IronPython str() on non-ASCII names.

## Engine Compatibility and Units
Remote 2026/2027 R1 sessions use IronPython 2.7: use .format(), not f-strings,
annotations or walrus expressions; use os.path instead of pathlib. check_script
checks syntax in the connected engine and some API names without executing the script;
it does not validate all arguments or runtime state. describe_api provides installed API help.

Use compatible, explicit Quantity units, such as "5 [mm]", "100 [N]", "1 [MPa]" or
"22 [C]". Confirm the unit system rather than changing an existing model implicitly.
Use raw strings or forward slashes for Windows paths.

## Transactions for Bulk Edits
For intended body_ids from find_objects(category="Body") and an available material_name:
```python
bodies = [DataModel.GetObjectById(body_id) for body_id in body_ids]
if any(body is None for body in bodies):
    raise ValueError("A body no longer exists")
with Transaction():
    for body in bodies:
        body.Material = material_name
```
Transaction() batches updates, not undo or rollback. Preview/apply supports individual
property changes with validation and readback; save_project provides a restore point.

## Files, Errors and Verification
upload_file sends local files to Mechanical; download_file retrieves files/patterns;
download_project retrieves project files; list_files shows available files.
Script paths are on the Mechanical host. run_python_code/create_custom_plot use
external CPython without ExtAPI and need data transferred/exported from Mechanical.

Errors include Mechanical's message; get_mechanical_logs reads application and solver output.
Check connection, scopes, mesh generation, materials and loads before solving. Evaluate
results before reading them, review warnings, and verify expected behavior, equilibrium
and mesh convergence. A successful API call is not engineering validation.
""")


_CONTENT_MAP = {
    "workflow": get_guidelines_for_workflow_overview,
    "geometry": get_guidelines_for_geometry_import,
    "materials": get_guidelines_for_materials,
    "meshing": get_guidelines_for_meshing,
    "analysis_setup": get_guidelines_for_analysis_setup,
    "boundary_conditions": get_guidelines_for_boundary_conditions,
    "solution": get_guidelines_for_solution,
    "postprocessing": get_guidelines_for_postprocessing,
    "named_selections": get_guidelines_for_named_selections,
    "general": get_guidelines_for_general_rules,
}


@app.tool()
def get_guidelines_for(content: GuidelinesContent) -> str:
    """Get Mechanical workflow guidance, scripting examples, and execution notes.

    Topics:
    workflow, geometry, materials, meshing, analysis_setup, boundary_conditions,
    solution, postprocessing, named_selections, general. Bundled text with official
    reference links; no network requests. Use describe_api for version-matched help.

    Parameters
    ----------
    content : str
        Topic from the list above.

    Returns
    -------
    str
        Practical examples, prerequisites, technical checks, and reference links.
    """
    return _CONTENT_MAP[content]()
