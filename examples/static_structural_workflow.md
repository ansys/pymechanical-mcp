# Static Structural Analysis Workflow

This example demonstrates a complete Mechanical FEA workflow using the
pymechanical-mcp tools. All steps were validated live against
ANSYS Mechanical 2025 R2.

## 1. Check Mechanical Installation

**Tool:** `check_mechanical_installed`

```
Response: Mechanical is installed on this system.
```

## 2. Launch Mechanical

**Tool:** `launch_mechanical`

```
Response:
  Successfully launched Mechanical
  Version: 252
  Project Directory: C:\Users\...\Project_Mech_Files\
```

## 3. Check Connection Status

**Tool:** `check_mechanical_status`

```json
{
  "connection": {
    "version": "252",
    "is_alive": true,
    "busy": false
  },
  "product_info": {
    "raw": "Ansys Mechanical [Ansys Mechanical Enterprise]\nProduct Version:252"
  },
  "model": {
    "model_name": "Model",
    "product_version": "2025 R2"
  }
}
```

## 4. Create Analysis

**Tool:** `run_python_script`

```python
analysis = Model.AddStaticStructuralAnalysis()
"Static Structural analysis added: {0}".format(analysis.Name)
```

```
Response: Static Structural analysis added: Static Structural
```

## 5. Import Geometry

**Tool:** `run_python_script`

```python
geometry_import = Model.GeometryImportGroup.AddGeometryImport()
geometry_file = r"C:\path\to\your\model.step"
geometry_import_format = Ansys.Mechanical.DataModel.Enums.GeometryImportPreference.Format.Automatic
geometry_import_prefs = Ansys.ACT.Mechanical.Utilities.GeometryImportPreferences()
geometry_import_prefs.ProcessNamedSelections = True
geometry_import.Import(geometry_file, geometry_import_format, geometry_import_prefs)
"Geometry imported: {0} bodies".format(
    Model.Geometry.GetChildren(DataModelObjectCategory.Body, True).Count
)
```

```
Response: Geometry imported: 3 bodies
```

## 6. Generate Mesh

**Tool:** `run_python_script`

```python
mesh = Model.Mesh
mesh.GenerateMesh()
"Mesh generated. Nodes: {0}, Elements: {1}".format(mesh.Nodes, mesh.Elements)
```

```
Response: Mesh generated. Nodes: 1381, Elements: 352
```

## 7. Get Model Info

**Tool:** `get_model_info`

```json
{
  "geometry": { "body_count": 3 },
  "mesh": { "node_count": 1381, "element_count": 352 },
  "analyses_count": 1,
  "project": { "product_version": "2025 R2", "name": "Project" },
  "model": { "name": "Model" }
}
```

## 8. Apply Boundary Conditions

**Tool:** `run_python_script`

```python
analysis = Model.Analyses[0]

# Add force
force = analysis.AddForce()
force.DefineBy = LoadDefineBy.Components

# Add fixed support
fixed = analysis.AddFixedSupport()

"BCs added: {0}, {1}".format(force.Name, fixed.Name)
```

> **Note:** For proper results, scope loads and supports to Named Selections.
> Use `run_python_script` with worksheet-based Named Selections or directly
> assign geometry via `ns.Location`.

## 9. Add Result Objects

**Tool:** `run_python_script`

```python
solution = Model.Analyses[0].Solution

# Add result objects
total_deform = solution.AddTotalDeformation()
equiv_stress = solution.AddEquivalentStress()

"Results added: {0}, {1}".format(total_deform.Name, equiv_stress.Name)
```

```
Response: Results added: Total Deformation, Equivalent Stress
```

## 10. Solve

**Tool:** `run_python_script`

```python
analysis = Model.Analyses[0]
analysis.Solve()
"Solve initiated"
```

## 11. Evaluate Results

**Tool:** `run_python_script`

```python
solution = Model.Analyses[0].Solution
solution.EvaluateAllResults()

# Children[0] = SolutionInformation, [1] = TotalDeformation, [2] = EquivalentStress
total_deform = solution.Children[1]
equiv_stress = solution.Children[2]

"Deformation Max: {0}, Stress Max: {1}".format(
    total_deform.Maximum, equiv_stress.Maximum
)
```

## 12. Screenshot

**Tool:** `screenshot`

Returns a PNG image of the Mechanical viewport.

## 13. Get Project Directory

**Tool:** `get_project_directory`

```
Response: Project directory: C:\Users\...\Project_Mech_Files\
```

## 14. Clear and Disconnect

**Tool:** `clear_mechanical`

```
Response: Mechanical database cleared successfully.
```

**Tool:** `disconnect_from_mechanical`

```
Response: Successfully disconnected from Mechanical
```

---

## Important Notes

1. **Use `.format()` instead of f-strings** — Mechanical 2025 R2 uses IronPython 2.7
   which does not support f-string syntax.
2. **Use `run_python_script`** for Mechanical API scripting (ExtAPI, Model, etc.).
   Use `run_python_code` only for external Python calculations (NumPy, Pandas, etc.).
3. **Units:** `Quantity("value unit")` syntax works for many contexts. Some unit strings
   may require the Mechanical-specific unit format.
4. **Scoping:** Always prefer Named Selections for boundary conditions and results
   to ensure geometry is properly targeted.
