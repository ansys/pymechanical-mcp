"""End-to-end test for PyMechanical MCP Server."""

from ansys.mechanical.core import connect_to_mechanical

print("=" * 60)
print("PyMechanical MCP Server - End-to-End Test")
print("=" * 60)

# Connect to local Mechanical
print("\n1. Connecting to Mechanical on port 10000...")
m = connect_to_mechanical(port=10000)
print(f"   Connected to Mechanical version: {m.version}")
print(f"   Is alive: {m.is_alive}")
print(f"   Project directory: {m.project_directory}")

# Run a simple script
print("\n2. Running a simple script...")
result = m.run_python_script("print('Hello from PyMechanical MCP!')")
print(f"   Script result: '{result}'")

# Get product info
print("\n3. Getting product info...")
info = m.get_product_info()
print(f"   Product info: {info[:100]}..." if len(info) > 100 else f"   Product info: {info}")

# Run a more complex script
print("\n4. Running a model info script...")
script = """
import json
model_info = {}
project = ExtAPI.DataModel.Project
model_info['product_version'] = project.ProductVersion
model = Model
model_info['model_name'] = model.Name if hasattr(model, 'Name') else 'N/A'
json.dumps(model_info)
"""
result = m.run_python_script(script)
print(f"   Model info: {result}")

print("\n" + "=" * 60)
print("End-to-End Test PASSED!")
print("=" * 60)
