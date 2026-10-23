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

"""Documentation-backed scripting patterns and MCP-specific execution notes."""

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
    """Return workflow context from the official scripting fundamentals."""
    return _reference("""# Mechanical Simulation Workflow Overview
Typical order: Preprocessing (geometry, materials, mesh, analysis settings), scoped
supports and loads, solve, then Postprocessing (evaluate, review, export results).
Existing units, materials and analyses provide context for subsequent changes.
Scripts passed to run_python_script run INSIDE Mechanical with ExtAPI (all APIs),
DataModel (objects, CAD and mesh entities), Model, Tree (Outline) and Graphics.
run_python_code is separate external CPython without these objects.
Use check_mechanical_status and get_model_info for context. Summary lists may be
truncated: filter find_objects by category/name/parent and follow next_offset until
null. Restart enumeration if result_fingerprint changes. Object IDs last only for
the life of the object. get_model_info reports unit_system. Quantity("5 [mm]") carries
its own unit. ExtAPI.Application.ActiveUnitSystem (for example
MechanicalUnitSystem.StandardNMM) controls the active units.
Save before destructive changes; there is no automatic undo.
Transaction() defers background updates for bulk edits; it is not validation or rollback.
""")


def get_guidelines_for_geometry_import() -> str:
    """Return geometry import and remote-file execution notes."""
    return _reference(
        """# Geometry Import in Mechanical
STEP (.stp/.step), IGES, Parasolid, DesignModeler and native CAD files need an
installed, licensed reader. The path must exist on the Mechanical host. upload_file
places a local file in the project directory and returns its file name. Set file_name
to that name (or use an existing absolute host path), then run:
```python
import os
remote_path = os.path.join(ExtAPI.DataModel.Project.ProjectDirectory, file_name)
geometry_import = Model.GeometryImportGroup.AddGeometryImport()
preferences = Ansys.ACT.Mechanical.Utilities.GeometryImportPreferences()
preferences.ProcessNamedSelections = True
preferences.ProcessCoordinateSystems = True
geometry_import.Import(remote_path,
    Ansys.Mechanical.DataModel.Enums.GeometryImportPreference.Format.Automatic,
    preferences)
```
Large assemblies take longer. Check import messages with get_mechanical_logs and
body counts/types with get_model_info; find_objects(category="Body") lists bodies.
Do not reimport into an existing model unnecessarily.
""",
        "bolt_pretension",
    )


def get_guidelines_for_materials() -> str:
    """Return material assignment notes without assuming available libraries."""
    return _reference(
        """# Material Definition in Mechanical
Materials come from Engineering Data or imported material files. get_model_info and
find_objects(category="Material") list what exists; "Structural Steel" is common but
not guaranteed. Assign only an existing material to the intended bodies, not all
bodies by default. Set body_id (from find_objects) and material_name first:
```python
body = DataModel.GetObjectById(body_id)
if body is None:
    raise ValueError("Body no longer exists")
body.Material = material_name
```
Assigning body.Material does not create a material. Check required properties:
structural analyses need Young's modulus and Poisson's ratio, plus density for
inertia or modal; thermal needs conductivity, plus specific heat for transient and
thermal expansion for thermal stress. The reference covers material imports.
""",
        "bolt_pretension",
    )


def get_guidelines_for_meshing() -> str:
    """Return mesh syntax and scoping notes without universal quality cutoffs."""
    return _reference(
        """# Mesh Generation in Mechanical
Inspect Model.Mesh before changing controls. Start coarse, refine where gradients are
high, and check convergence; size from geometry and requirements, not one rule.
```python
mesh = Model.Mesh
mesh.ElementSize = Quantity("5 [mm]")
mesh.GenerateMesh()
```
Mesh.Nodes and Mesh.Elements are integer counts, not collections requiring .Count.
get_model_info reports them and the active metric without changing it; set
mesh.MeshMetric to report another quality metric. Local sizing, after setting
selection_id to a confirmed named selection:
```python
sizing = Model.Mesh.AddSizing()
sizing.Location = DataModel.GetObjectById(selection_id)
sizing.ElementSize = Quantity("2 [mm]")
```
Method controls (Automatic, Tetrahedrons, Hex Dominant, Sweep, MultiZone) start from
Model.Mesh.AddAutomaticMethod(); confirm Method enums with describe_api. Thin bending
regions need several elements through thickness or shell elements. Review mesh
messages; quality thresholds depend on element and analysis type.
""",
        "bolt_pretension",
    )


def get_guidelines_for_analysis_setup() -> str:
    """Return analysis and settings discovery guidance."""
    return _reference(
        """# Analysis Setup in Mechanical
get_model_info reports existing analyses and zero-based indices. Creators include
Model.AddStaticStructuralAnalysis, AddModalAnalysis, AddSteadyStateThermalAnalysis,
AddTransientThermalAnalysis, AddTransientStructuralAnalysis and
AddHarmonicResponseAnalysis.
```python
analysis = Model.AddStaticStructuralAnalysis()
settings = analysis.AnalysisSettings
settings.NumberOfSteps = 1
```
Use Model.Analyses[analysis_index] for an existing analysis. Inspect settings with
find_objects and describe_api(object_id=...), including editable properties/enums.
Common settings: LargeDeflection, SolverType, automatic time stepping/substeps and,
for modal, MaximumModesToFind. Direct solvers are generally robust; iterative can
reduce memory for large, well-conditioned models. Enable LargeDeflection when
deformation changes stiffness, not from a fixed strain cutoff. Contact regions under
Model.Connections expose ContactType (Bonded, Frictional, Frictionless,
NoSeparation) and ContactFormulation; choose from the physical joint.
""",
        "bolt_pretension",
    )


def get_guidelines_for_boundary_conditions() -> str:
    """Return scoped boundary-condition and tabular-value patterns."""
    return _reference(
        """# Boundary Conditions and Loads
Confirm analysis_index and scopes using get_model_info and find_objects. Named
selections make scopes explicit, but names can duplicate: resolve the intended IDs.
GetObjectById returns None for a deleted ID; an empty or wrong scope is invalid.
Set analysis_index, support_id and load_id first:
```python
analysis = Model.Analyses[analysis_index]
support = analysis.AddFixedSupport()
support.Location = DataModel.GetObjectById(support_id)
pressure = analysis.AddPressure()
pressure.Location = DataModel.GetObjectById(load_id)
pressure.Magnitude.Output.DiscreteValues = [Quantity("1 [MPa]")]
```
Other creators: AddDisplacement (set only constrained components; unset ones stay
free), AddFrictionlessSupport, AddForce, AddRemoteForce, and thermal AddTemperature
or AddConvection (FilmCoefficient, AmbientTemperature). For forces, set
DefineBy = LoadDefineBy.Components; use each component's .Output.DiscreteValues,
not assignment to the component object. Time-dependent input/output tables need
matching lengths. Static structural models must prevent rigid-body motion with
supports or contacts, or the solve fails (free modal analyses are a valid exception);
choose constraints from the physics, not by fixing everything. Confirm thermal units
with describe_api.
""",
        "valve",
    )


def get_guidelines_for_solution() -> str:
    """Return solve, status and log guidance without blocking polling loops."""
    return _reference(
        """# Solution Phase in Mechanical
Use solve_analysis(analysis_index=..., wait=True) to wait, or wait=False to start
asynchronously. A successful start is not a completed solve. Read the selected
analysis's Solution.Status in later calls; never poll inside a Mechanical loop.
```python
str(Model.Analyses[analysis_index].Solution.Status)
```
Confirm analysis_index first; success is SolutionStatusType.Done. Direct API
analysis.Solve(True) waits; Solve(False) does not.
Review get_mechanical_logs(source="messages") and source="solve_log", with bounded
tail_lines/max_chars and the analysis_index. AnalysisSettings.StoreResultsAt controls
saved time points. If a solve fails, diagnose before changing physics: missing mesh or
material properties, rigid-body motion from insufficient supports, poor elements,
contact gaps or penetration, load steps too large (ramp with substeps), or large
deformation needing LargeDeflection. Change one cause at a time and recheck logs.
""",
        "valve",
    )


def get_guidelines_for_postprocessing() -> str:
    """Return result evaluation and scoped export guidance."""
    return _reference(
        """# Postprocessing in Mechanical
Use get_results_summary after a successful solve for extrema and units. Unsolved
or obsolete results are not valid values. Inspect existing results before creating
duplicates. For a missing result, confirm analysis_index then use this API pattern:
```python
solution = Model.Analyses[analysis_index].Solution
stress = solution.AddEquivalentStress()
solution.EvaluateAllResults()
stress.Maximum
```
Other creators: AddTotalDeformation, AddDirectionalDeformation (set
NormalOrientation), AddNormalStress, AddMaximumPrincipalStress and
AddEquivalentElasticStrain; results also expose Minimum and Average. Set Location
before evaluating a scoped result. For modal deformation, set Mode to an extracted
mode; ReportedFrequency gives its frequency. Do not hardcode ten modes. Use screenshot
for images, export_results for PNG/TXT/both on the selected analysis, and download_file
to retrieve files. Direct API: result.ExportToTextFile(path); for
Graphics.ExportImage(path, GraphicsImageExportFormat.PNG), activate the intended result
first. Solution.Children[0] may not be a result.
""",
        "valve",
    )


def get_guidelines_for_named_selections() -> str:
    """Return named-selection discovery and worksheet syntax."""
    return _reference(
        """# Named Selections in Mechanical
Find existing scopes with find_objects(category="NamedSelection", name_contains=...).
Follow next_offset until null; previews are not complete lists. Resolve IDs with
DataModel.GetObjectById; duplicate names make GetObjectsByName()[0] unsafe. Use
descriptive names; recheck scope after geometry changes. Worksheet pattern (example values):
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
Entity types include GeoFace, GeoEdge, GeoVertex and GeoBody; criteria include
LocationX/Y/Z, Size, Type and Name. Confirm enums with describe_api and inspect the
result before assigning Location.
""",
        "topology_optimization_cantilever_beam",
    )


def get_guidelines_for_general_rules() -> str:
    """Return MCP execution facts with official scripting references."""
    return _reference("""# General Rules for MCP Scripts
Pass only the script body to run_python_script, not a mechanical.run_python_script
wrapper. Remote 2026/2027 R1 uses IronPython 2.7: .format(), not f-strings, annotations,
walrus expressions or pathlib (use os.path). check_script reports the connected engine
and catches some syntax/API-name errors, not all argument/runtime errors; it does not
run the script. Use Quantity("5 [mm]") with square-bracket, compatible units; inspect
rather than silently change the unit system. Use raw strings or forward slashes for
Windows paths. run_python_script returns the last expression as text; assignments
return empty text. For structured results, end with json.dumps(payload,
ensure_ascii=False); keep payloads bounded and avoid IronPython str() on non-ASCII
names. Script globals persist between calls.
Transaction() batches updates, not undo. Preview/apply property changes only after
agreement; save_project is the restore point. File tools transfer files, while script
paths are on the Mechanical host. run_python_code/create_custom_plot use external
CPython without ExtAPI. describe_api reads installed API documentation offline.
Common misses: mesh not generated, rigid-body motion, results not evaluated. Errors
return Mechanical's message; get_mechanical_logs shows application and solver output.
Check results against expectations and mesh convergence before relying on them.
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
    """Get concise, documentation-backed patterns and MCP execution notes.

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
        Concise patterns, prerequisites and source links, not engineering presets.
    """
    return _CONTENT_MAP[content]()
