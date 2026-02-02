"""Context tools for PyMechanical MCP Server.

This module defines MCP tools that provide context and guidance for
PyMechanical and Ansys Mechanical workflows. These tools return context
information that can be accessed by the LLM to get help with various
aspects of Mechanical simulations.
"""

# flake8: noqa: E501

from ansys.mechanical.mcp import app


@app.tool()
def get_guidelines_for_workflow_overview() -> str:
    """Get general Mechanical simulation workflow guidelines.

    Use this tool when explaining or generating PyMechanical or Ansys Mechanical workflows.

    Returns
    -------
    str
        Overview of the general simulation process for all Mechanical analysis types.
    """
    return """# Mechanical Simulation Workflow Overview

When explaining or generating PyMechanical or Ansys Mechanical workflows, ALWAYS FOLLOW this general simulation process.

## PyMechanical Architecture

PyMechanical has two interfaces:
1. **Remote Session**: Connect to a running Mechanical gRPC server
2. **Embedded Instance**: Run Mechanical embedded in the Python process

For MCP server, we primarily use the Remote Session interface.

## API Entry Points

When running scripts inside Mechanical, you have access to these entry points:
- `ExtAPI`: Entry point for all APIs
- `DataModel`: Entry point to access CAD, mesh entities, and Outline objects
- `Model`: The Model object from the Outline
- `Tree`: The Outline (tree structure)
- `Graphics`: The 3D graphics engine

## Workflow Steps

1. **Preprocessing**
   - Import geometry (CAD files)
   - Define materials and assign to bodies
   - Set up mesh controls and generate mesh
   - Define analysis settings

2. **Analysis Setup**
   - Create analysis system (Static Structural, Modal, Thermal, etc.)
   - Apply boundary conditions (supports, constraints)
   - Apply loads (forces, pressures, temperatures)

3. **Solution**
   - Configure solver settings
   - Run the solution

4. **Postprocessing**
   - Add result objects (stress, strain, deformation)
   - Evaluate results
   - Export images and data

## Code Execution Pattern

Use `mechanical.run_python_script()` to execute scripts inside Mechanical:

```python
script = '''
# Your Mechanical scripting code here
result = ExtAPI.DataModel.Project.ProductVersion
result
'''
version = mechanical.run_python_script(script)
```

## Transaction Pattern for Performance

When modifying multiple objects, wrap operations in a Transaction:

```python
script = '''
with Transaction():
    for obj in Tree.AllObjects:
        obj.Name = obj.Name + " modified"
'''
mechanical.run_python_script(script)
```
"""


@app.tool()
def get_guidelines_for_geometry_import() -> str:
    """Get geometry import guidelines for Mechanical.

    Use this tool when explaining or generating geometry import operations.

    Returns
    -------
    str
        Guidelines for importing geometry in Mechanical.
    """
    return """# Geometry Import in Mechanical

## Supported Geometry Formats

Mechanical supports various CAD formats:
- ANSYS DesignModeler files (.agdb)
- STEP files (.stp, .step)
- IGES files (.igs, .iges)
- Parasolid files (.x_t, .x_b)
- CATIA files (.CATProduct, .CATPart)
- SolidWorks files (.sldprt, .sldasm)
- NX files (.prt)
- And many more...

## Importing Geometry via Script

```python
script = '''
import os

# Get the geometry import object
geometry_import = Model.GeometryImportGroup.AddGeometryImport()

# Set the geometry file path
geometry_file = r"C:\\path\\to\\your\\geometry.stp"

# Import the geometry
geometry_import.Import(geometry_file)
'''
mechanical.run_python_script(script)
```

## Accessing Geometry Objects

```python
script = '''
# Access the Geometry object
geometry = Model.Geometry

# Get all bodies
bodies = geometry.GetChildren(DataModelObjectCategory.Body, True)

# Iterate through bodies
for body in bodies:
    print(f"Body: {body.Name}, Material: {body.Material}")
'''
mechanical.run_python_script(script)
```

## Key Considerations

- Ensure geometry files are accessible from the Mechanical server
- Use `mechanical.upload()` to transfer files to the server if needed
- Large assemblies may require longer import times
- Check for geometry errors after import
"""


@app.tool()
def get_guidelines_for_materials() -> str:
    """Get material definition guidelines for Mechanical.

    Use this tool when explaining or generating material definitions.

    Returns
    -------
    str
        Guidelines for defining and assigning materials in Mechanical.
    """
    return """# Material Definition in Mechanical

## Accessing Engineering Data

Materials in Mechanical come from Engineering Data. The default material library
includes common materials like Structural Steel, Aluminum Alloy, etc.

## Assigning Materials to Bodies

```python
script = '''
# Get geometry
geometry = Model.Geometry

# Get all bodies
bodies = geometry.GetChildren(DataModelObjectCategory.Body, True)

# Assign material to each body
for body in bodies:
    body.Material = "Structural Steel"
'''
mechanical.run_python_script(script)
```

## Available Default Materials

Common materials available by default:
- "Structural Steel"
- "Aluminum Alloy"
- "Copper Alloy"
- "Gray Cast Iron"
- "Titanium Alloy"
- "Stainless Steel"

## Creating Custom Materials

For custom materials, you typically need to define them in Engineering Data
before importing into Mechanical. However, you can also use scripts:

```python
script = '''
# Access Engineering Data through ExtAPI
eng_data = ExtAPI.DataModel.Project.Model.Materials

# Get material assignment for a body
body = Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)[0]
body.Material = "Aluminum Alloy"
'''
mechanical.run_python_script(script)
```

## Material Properties

Key material properties for structural analysis:
- Young's Modulus (EX)
- Poisson's Ratio (PRXY)
- Density (DENS)
- Yield Strength
- Ultimate Tensile Strength

For thermal analysis:
- Thermal Conductivity
- Specific Heat
- Coefficient of Thermal Expansion
"""


@app.tool()
def get_guidelines_for_meshing() -> str:
    """Get mesh generation guidelines for Mechanical.

    Use this tool when explaining or generating mesh operations.

    Returns
    -------
    str
        Guidelines for generating meshes in Mechanical.
    """
    return """# Mesh Generation in Mechanical

## Accessing the Mesh Object

```python
script = '''
# Get the mesh object
mesh = Model.Mesh

# Generate mesh with default settings
mesh.GenerateMesh()

# Get mesh statistics
print(f"Nodes: {mesh.Nodes.Count if mesh.Nodes else 0}")
print(f"Elements: {mesh.Elements.Count if mesh.Elements else 0}")
'''
mechanical.run_python_script(script)
```

## Mesh Controls

### Global Mesh Size

```python
script = '''
mesh = Model.Mesh

# Set global element size
mesh.ElementSize = Quantity("10 mm")
'''
mechanical.run_python_script(script)
```

### Adding Mesh Controls

```python
script = '''
mesh = Model.Mesh

# Add sizing control
sizing = mesh.AddSizing()

# Select geometry for sizing
# sizing.Location = ... (requires Named Selection or geometry reference)

# Set element size
sizing.ElementSize = Quantity("5 mm")

# Generate mesh
mesh.GenerateMesh()
'''
mechanical.run_python_script(script)
```

## Mesh Methods

- **Automatic**: Default method, lets Mechanical choose
- **Tetrahedrons**: For complex 3D geometry
- **Hex Dominant**: Preferred for structural analysis when possible
- **Sweep**: For extruded geometry
- **MultiZone**: Combines structured and unstructured meshing

## Mesh Quality

```python
script = '''
mesh = Model.Mesh

# Check mesh quality metrics
mesh.GenerateMesh()

# Access mesh statistics
stats = mesh.GetMeshStatistics()
'''
mechanical.run_python_script(script)
```

## Best Practices

- Start with coarser mesh for initial analysis
- Refine mesh in areas of high stress gradients
- Use mesh refinement studies for convergence
- Check element quality metrics (aspect ratio, skewness)
"""


@app.tool()
def get_guidelines_for_analysis_setup() -> str:
    """Get analysis setup guidelines for Mechanical.

    Use this tool when setting up structural, modal, or thermal analyses.

    Returns
    -------
    str
        Guidelines for setting up analyses in Mechanical.
    """
    return """# Analysis Setup in Mechanical

## Analysis Types

Mechanical supports various analysis types:
- **Static Structural**: Linear and nonlinear static analysis
- **Modal**: Natural frequency and mode shape extraction
- **Harmonic Response**: Frequency response analysis
- **Transient Structural**: Time-dependent structural analysis
- **Steady-State Thermal**: Heat transfer at equilibrium
- **Transient Thermal**: Time-dependent heat transfer
- **Coupled Field**: Thermal-structural coupling

## Adding an Analysis

```python
script = '''
# Add a Static Structural analysis
analysis = Model.AddStaticStructuralAnalysis()

# Or add other analysis types:
# modal_analysis = Model.AddModalAnalysis()
# thermal_analysis = Model.AddSteadyStateThermalAnalysis()
'''
mechanical.run_python_script(script)
```

## Analysis Settings

```python
script = '''
# Get analysis settings
analysis = Model.Analyses[0]
settings = analysis.AnalysisSettings

# For Static Structural - configure step controls
settings.NumberOfSteps = 1

# For large deformation (nonlinear)
settings.LargeDeflection = True
'''
mechanical.run_python_script(script)
```

## Modal Analysis Settings

```python
script = '''
analysis = Model.AddModalAnalysis()
settings = analysis.AnalysisSettings

# Set number of modes to extract
settings.MaximumModesToFind = 10

# Set frequency range if needed
# settings.RangeMinimum = Quantity("0 Hz")
# settings.RangeMaximum = Quantity("1000 Hz")
'''
mechanical.run_python_script(script)
```

## Solver Controls

```python
script = '''
analysis = Model.Analyses[0]
settings = analysis.AnalysisSettings

# Solver type
settings.SolverType = SolverType.Direct  # or Iterative

# For nonlinear analysis
settings.AutomaticTimeStepping = AutomaticTimeStepping.On
'''
mechanical.run_python_script(script)
```
"""


@app.tool()
def get_guidelines_for_boundary_conditions() -> str:
    """Get boundary conditions and loads guidelines for Mechanical.

    Use this tool when applying supports, constraints, and loads.

    Returns
    -------
    str
        Guidelines for applying boundary conditions and loads in Mechanical.
    """
    return """# Boundary Conditions and Loads in Mechanical

## Supports (Constraints)

### Fixed Support

```python
script = '''
analysis = Model.Analyses[0]

# Add Fixed Support
fixed_support = analysis.AddFixedSupport()

# Assign to Named Selection (recommended)
# fixed_support.Location = ExtAPI.DataModel.GetObjectsByName("MySelection")[0]

# Or scope to geometry directly through selection
'''
mechanical.run_python_script(script)
```

### Displacement Constraint

```python
script = '''
analysis = Model.Analyses[0]

# Add Displacement
displacement = analysis.AddDisplacement()

# Set displacement values
displacement.XComponent.Output.SetDiscreteValue(0, Quantity("0 mm"))
displacement.YComponent.Output.SetDiscreteValue(0, Quantity("0 mm"))
displacement.ZComponent.Output.SetDiscreteValue(0, Quantity("0 mm"))
'''
mechanical.run_python_script(script)
```

### Frictionless Support

```python
script = '''
analysis = Model.Analyses[0]
frictionless = analysis.AddFrictionlessSupport()
'''
mechanical.run_python_script(script)
```

## Loads

### Force

```python
script = '''
analysis = Model.Analyses[0]

# Add Force
force = analysis.AddForce()

# Define force magnitude and direction
force.DefineBy = LoadDefineBy.Components
force.XComponent.Output.SetDiscreteValue(0, Quantity("0 N"))
force.YComponent.Output.SetDiscreteValue(0, Quantity("-1000 N"))
force.ZComponent.Output.SetDiscreteValue(0, Quantity("0 N"))
'''
mechanical.run_python_script(script)
```

### Pressure

```python
script = '''
analysis = Model.Analyses[0]

# Add Pressure
pressure = analysis.AddPressure()

# Set pressure value
pressure.Magnitude.Output.SetDiscreteValue(0, Quantity("1 MPa"))
'''
mechanical.run_python_script(script)
```

### Remote Force

```python
script = '''
analysis = Model.Analyses[0]

# Add Remote Force
remote_force = analysis.AddRemoteForce()

# Set location and magnitude
remote_force.XComponent.Output.SetDiscreteValue(0, Quantity("100 N"))
'''
mechanical.run_python_script(script)
```

## Thermal Loads

### Temperature

```python
script = '''
analysis = Model.Analyses[0]

# Add Temperature
temp = analysis.AddTemperature()
temp.Magnitude.Output.SetDiscreteValue(0, Quantity("100 C"))
'''
mechanical.run_python_script(script)
```

### Convection

```python
script = '''
analysis = Model.Analyses[0]

# Add Convection
convection = analysis.AddConvection()
convection.FilmCoefficient.Output.SetDiscreteValue(0, Quantity("10 W/m^2/C"))
convection.AmbientTemperature.Output.SetDiscreteValue(0, Quantity("22 C"))
'''
mechanical.run_python_script(script)
```

## Using Named Selections

Named Selections are the preferred way to scope loads and supports:

```python
script = '''
# Get Named Selection by name
ns = ExtAPI.DataModel.GetObjectsByName("FixedFace")[0]

# Apply to boundary condition
fixed_support = analysis.AddFixedSupport()
fixed_support.Location = ns
'''
mechanical.run_python_script(script)
```
"""


@app.tool()
def get_guidelines_for_solution() -> str:
    """Get solution phase guidelines for Mechanical.

    Use this tool when running solutions in Mechanical.

    Returns
    -------
    str
        Guidelines for solving analyses in Mechanical.
    """
    return """# Solution Phase in Mechanical

## Running the Solution

```python
script = '''
# Get the analysis
analysis = Model.Analyses[0]

# Solve
analysis.Solve()

# Check solution status
solution = analysis.Solution
print(f"Status: {solution.Status}")
'''
mechanical.run_python_script(script)
```

## Solution Object

```python
script = '''
solution = Model.Analyses[0].Solution

# Get solution information
print(f"Solver Type: {solution.SolverType}")
print(f"Status: {solution.Status}")
'''
mechanical.run_python_script(script)
```

## Handling Long Solutions

For long-running solutions, consider:

```python
script = '''
analysis = Model.Analyses[0]

# Start solve (returns immediately for monitoring)
analysis.Solve(True)  # True for background solve

# Check status
while analysis.Solution.Status == SolutionStatusType.Solving:
    # Wait and check periodically
    pass
'''
mechanical.run_python_script(script)
```

## Solution Output Controls

```python
script = '''
analysis = Model.Analyses[0]
settings = analysis.AnalysisSettings

# Control result output frequency
settings.ResultFileSettings.SaveResultsAtAllTimePoints = True
'''
mechanical.run_python_script(script)
```

## Convergence Issues

If the solution doesn't converge:
1. Check mesh quality
2. Verify boundary conditions (no rigid body motion)
3. Review load magnitudes
4. Enable large deflection for geometric nonlinearity
5. Adjust solver settings (substeps, convergence criteria)

## Error Handling

```python
script = '''
try:
    analysis = Model.Analyses[0]
    analysis.Solve()
    
    if analysis.Solution.Status == SolutionStatusType.Done:
        print("Solution completed successfully")
    else:
        print(f"Solution status: {analysis.Solution.Status}")
except Exception as e:
    print(f"Solution error: {e}")
'''
mechanical.run_python_script(script)
```
"""


@app.tool()
def get_guidelines_for_postprocessing() -> str:
    """Get postprocessing guidelines for Mechanical.

    Use this tool when extracting and visualizing results.

    Returns
    -------
    str
        Guidelines for postprocessing in Mechanical.
    """
    return """# Postprocessing in Mechanical

## Adding Result Objects

### Deformation Results

```python
script = '''
solution = Model.Analyses[0].Solution

# Total Deformation
total_deform = solution.AddTotalDeformation()

# Directional Deformation
dir_deform = solution.AddDirectionalDeformation()
dir_deform.NormalOrientation = NormalOrientationType.YAxis

# Evaluate results
total_deform.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```

### Stress Results

```python
script = '''
solution = Model.Analyses[0].Solution

# Equivalent (von-Mises) Stress
equiv_stress = solution.AddEquivalentStress()

# Normal Stress
normal_stress = solution.AddNormalStress()
normal_stress.NormalOrientation = NormalOrientationType.XAxis

# Maximum Principal Stress
max_principal = solution.AddMaximumPrincipalStress()

# Evaluate
equiv_stress.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```

### Strain Results

```python
script = '''
solution = Model.Analyses[0].Solution

# Equivalent Strain
equiv_strain = solution.AddEquivalentElasticStrain()

# Evaluate
equiv_strain.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```

## Reading Result Values

```python
script = '''
solution = Model.Analyses[0].Solution

# Get stress result
stress = solution.AddEquivalentStress()
stress.EvaluateAllResults()

# Get min and max values
print(f"Maximum Stress: {stress.Maximum}")
print(f"Minimum Stress: {stress.Minimum}")
print(f"Average Stress: {stress.Average}")
'''
mechanical.run_python_script(script)
```

## Modal Analysis Results

```python
script = '''
solution = Model.Analyses[0].Solution

# Add Total Deformation for each mode
for i in range(1, 11):  # First 10 modes
    deform = solution.AddTotalDeformation()
    deform.Mode = i
    deform.EvaluateAllResults()
    print(f"Mode {i} Frequency: {deform.ReportedFrequency}")
'''
mechanical.run_python_script(script)
```

## Exporting Results

### Export to Image

```python
script = '''
# Get result object
stress = Model.Analyses[0].Solution.Children[0]

# Export image
Graphics.ExportImage(r"C:\\temp\\stress_result.png", GraphicsImageExportFormat.PNG)
'''
mechanical.run_python_script(script)
```

### Export Data to File

```python
script = '''
result = Model.Analyses[0].Solution.Children[0]

# Export to text file
result.ExportToTextFile(r"C:\\temp\\results.txt")
'''
mechanical.run_python_script(script)
```

## Result Scoping

```python
script = '''
solution = Model.Analyses[0].Solution

# Add result scoped to specific geometry
stress = solution.AddEquivalentStress()

# Scope to Named Selection
ns = ExtAPI.DataModel.GetObjectsByName("CriticalRegion")[0]
stress.Location = ns

stress.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```
"""


@app.tool()
def get_guidelines_for_named_selections() -> str:
    """Get Named Selection guidelines for Mechanical.

    Use this tool when working with Named Selections.

    Returns
    -------
    str
        Guidelines for creating and using Named Selections in Mechanical.
    """
    return """# Named Selections in Mechanical

Named Selections are the preferred way to define geometry scopes for loads,
supports, and results in Mechanical scripting.

## Creating Named Selections

### From Script

```python
script = '''
# Add a Named Selection
ns = Model.AddNamedSelection()
ns.Name = "MySelection"

# The selection needs to be defined through geometry picking or criteria
'''
mechanical.run_python_script(script)
```

### Accessing Existing Named Selections

```python
script = '''
# Get all Named Selections
named_selections = Model.NamedSelections.GetChildren(
    DataModelObjectCategory.NamedSelection, True
)

for ns in named_selections:
    print(f"Named Selection: {ns.Name}")
'''
mechanical.run_python_script(script)
```

### Getting Named Selection by Name

```python
script = '''
# Get specific Named Selection
ns = ExtAPI.DataModel.GetObjectsByName("FixedSupport")[0]
print(f"Found: {ns.Name}")
'''
mechanical.run_python_script(script)
```

## Using Named Selections

### With Boundary Conditions

```python
script = '''
analysis = Model.Analyses[0]

# Add fixed support
fixed = analysis.AddFixedSupport()

# Assign Named Selection
ns = ExtAPI.DataModel.GetObjectsByName("FixedFace")[0]
fixed.Location = ns
'''
mechanical.run_python_script(script)
```

### With Results

```python
script = '''
solution = Model.Analyses[0].Solution

# Add stress result scoped to Named Selection
stress = solution.AddEquivalentStress()
ns = ExtAPI.DataModel.GetObjectsByName("CriticalArea")[0]
stress.Location = ns

stress.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```

## Best Practices

1. Create Named Selections for frequently used geometry scopes
2. Use descriptive names (e.g., "FixedSupport_Bottom", "Load_TopFace")
3. Named Selections persist across geometry updates (when possible)
4. Use Named Selections for parameterization and automation
"""


@app.tool()
def get_guidelines_for_general_rules() -> str:
    """Get general rules and best practices for Mechanical workflows.

    Use this tool when working with Mechanical simulations.

    Returns
    -------
    str
        General rules and best practices for Mechanical simulations.
    """
    return """# General Rules and Best Practices for PyMechanical

## Script Execution Pattern

Always use `mechanical.run_python_script()` to execute Mechanical scripts:

```python
script = '''
# Your Mechanical scripting code
result = ExtAPI.DataModel.Project.ProductVersion
result
'''
output = mechanical.run_python_script(script)
```

## Return Values

The script returns the string value of the last executed statement:

```python
# Returns '5'
mechanical.run_python_script("2 + 3")

# Returns product version string
mechanical.run_python_script("ExtAPI.DataModel.Project.ProductVersion")

# Returns empty string for assignments
mechanical.run_python_script("x = 10")
```

## Using Quantities

Mechanical uses the Quantity class for values with units:

```python
script = '''
# Force in Newtons
force = Quantity("1000 N")

# Length in millimeters
length = Quantity("100 mm")

# Pressure in MPa
pressure = Quantity("1 MPa")

# Temperature in Celsius
temp = Quantity("100 C")
'''
mechanical.run_python_script(script)
```

## Transaction for Performance

Wrap multiple modifications in a Transaction:

```python
script = '''
with Transaction():
    # Multiple operations here
    for obj in Tree.AllObjects:
        if hasattr(obj, 'Name'):
            obj.Name = obj.Name + "_modified"
'''
mechanical.run_python_script(script)
```

## Error Handling

```python
try:
    result = mechanical.run_python_script(script)
except grpc.RpcError as error:
    print(f"Script error: {error.details()}")
```

## File Transfers

Use upload/download for file operations:

```python
# Upload file to Mechanical
mechanical.upload("local_file.stp")

# Download results
mechanical.download("results.txt", target_dir="./output")

# Download entire project
mechanical.download_project(target_dir="./project_backup")
```

## Common Pitfalls

1. **Not checking connection status** before running scripts
2. **Missing mesh generation** before solving
3. **No boundary conditions** causing rigid body motion
4. **Forgetting to evaluate results** after adding result objects
5. **Path issues** - use raw strings (r"path") or forward slashes

## Verification Steps

1. Check model setup: geometry, materials, mesh
2. Verify boundary conditions prevent rigid body motion
3. Review solver messages for warnings
4. Validate results against expected behavior
5. Check mesh convergence for critical results
"""
