# PyMechanical MCP Server

A Model Context Protocol (MCP) server that provides AI assistants with the ability to interact with Ansys Mechanical through PyMechanical. This server enables natural language interaction with Mechanical for structural, thermal, and multiphysics simulations.

## Overview

This MCP server bridges the gap between AI assistants and Ansys Mechanical, allowing you to:

- **Manage Mechanical instances**: Get detailed status information and manage connections
- **Dynamic connection management**: Launch new Mechanical instances, connect to existing ones, or disconnect as needed
- **Execute Mechanical scripts**: Run Python scripts using the Mechanical scripting API
- **Custom Python execution**: Run arbitrary Python and PyMechanical code in a persistent session
- **Advanced visualization**: Create custom matplotlib plots for simulation results
- **Workflow guidance**: Access comprehensive context and best practices for all phases of Mechanical simulations
- **Flexible deployment**: Works with Mechanical running locally, remotely, or in Docker containers

## Features

- **Dynamic Connection Management**: Connect to and disconnect from Mechanical instances on demand, or launch new instances programmatically
- **Flexible Deployment**: Supports Mechanical running locally, remotely, or in Docker containers
- **Type-Safe Context**: Strongly typed application context for reliable operations
- **Comprehensive Tools**: Specialized tools for Mechanical interaction, including enhanced error handling
- **Python Session Support**: Execute custom Python code and create advanced visualizations using a persistent Python session
- **Workflow Guidance**: Built-in context tools provide comprehensive guidelines and best practices for Mechanical workflows
- **Automatic Initialization**: The server automatically provides necessary context for Mechanical/PyMechanical queries on first interaction

## Prerequisites

- Python 3.10 or higher (up to 3.13)
- Ansys Mechanical installation (optional - can connect to remote instances)
- PyMechanical library (ansys-mechanical-core >= 0.12.0)
- FastMCP library (fastmcp >= 0.1.0)
- Ansys Common MCP library (ansys-common-mcp >= 0.1.0)

## Quick Start

The quickest way to run the MCP server is to use [`uv`](https://docs.astral.sh/uv/) in your desired software:

### VS Code integration

You should add the following to your `.vscode/mcp.json` file in your project directory:

```json
{
	"servers": {
		"pymechanical": {
			"type": "stdio",
			"command": "uvx",
      		"args": [
				"--index-strategy", "unsafe-best-match",
				"--from", "git+https://github.com/ansys/pymechanical-mcp", "ansys-mechanical-mcp"
			]
		}
	}
}
```

> **Note**: The `--index-strategy unsafe-best-match` flag ensures proper dependency resolution when you have internal PyPI indexes configured.

For more information visit [Use MCP servers in VS Code](https://code.visualstudio.com/docs/copilot/customization/mcp-servers). In this page, you can find information about adding an MCP server globally to the user.

Make sure you enabled the access to MCPs in your VS Code settings as presented here:
![VS Code settings](enable_mcp.png)

### Claude Desktop

Edit the file `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pymechanical": {
      "command": "uvx",
      "args": ["--index-strategy", "unsafe-best-match", "--from", "git+https://github.com/ansys/pymechanical-mcp", "ansys-mechanical-mcp"],
      "description": "A simple MCP server to talk to Ansys Mechanical",
      "version": "0.1.0",
      "language": "python"
    }
  }
}
```

For more information, visit [Testing your server with Claude for Desktop](https://modelcontextprotocol.io/docs/develop/build-server#testing-your-server-with-claude-for-desktop).

### Claude Code

You can add PyMechanical-MCP server to the project in a specific directory with the following commands:

```bash
cd my-project
claude mcp add --transport stdio pymechanical -- uvx --index-strategy unsafe-best-match --from git+https://github.com/ansys/pymechanical-mcp ansys-mechanical-mcp
```

If you want to add the MCP-server globally on your user, use the following command:

```bash
claude mcp add --transport stdio --scope user pymechanical -- uvx --index-strategy unsafe-best-match --from git+https://github.com/ansys/pymechanical-mcp ansys-mechanical-mcp
```

For more information, visit [Claude Code Docs-Installing MCP servers](https://code.claude.com/docs/en/mcp#installing-mcp-servers)

### As a standalone Application

You can start the PyMechanical MCP server as a standalone Python application using `uvx`:

```console
uvx --index-strategy unsafe-best-match --from git+https://github.com/ansys/pymechanical-mcp ansys-mechanical-mcp
```

You can also use your python virtual environment if you have pip installed PyMechanical MCP server:

```console
./.venv/bin/python -m ansys.mechanical.mcp
```

## Transport Options

PyMechanical MCP server supports two transport protocols:

### STDIO Transport (Default)

STDIO transport is the default and recommended for local MCP client integration. It communicates via standard input/output streams.

**VS Code Configuration** (`.vscode/mcp.json`):
```json
{
  "servers": {
    "pymechanical": {
      "type": "stdio",
      "command": ".venv\\Scripts\\python.exe",
      "args": ["-m", "ansys.mechanical.mcp"],
      "env": {
        "FASTMCP_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

**Command Line**:
```console
python -m ansys.mechanical.mcp --transport stdio
```

### HTTP Transport (Streamable HTTP with SSE)

HTTP transport enables remote access to the MCP server over HTTP with Server-Sent Events (SSE), allowing web-based clients and remote integrations.

> [!NOTE]
> **Note**: When using HTTP transport, you must start the MCP server separately before configuring your client. Unlike STDIO transport (which auto-starts the server), HTTP transport requires the server to be running independently.

**VS Code Configuration** (`.vscode/mcp.json`):
```json
{
  "servers": {
    "pymechanical": {
      "type": "http",
      "url": "http://127.0.0.1:8080"
    }
  }
}
```

**Starting the Server**:

First, start the MCP server in a separate terminal:

```console
# Basic HTTP server (localhost:8080)
python -m ansys.mechanical.mcp --transport http

# Custom host and port
python -m ansys.mechanical.mcp --transport http --http-host 0.0.0.0 --http-port 9000

# With CORS origins for web clients
python -m ansys.mechanical.mcp --transport http --cors-origins "http://localhost:3000,https://example.com"
```

**Command Line Options**:
- `--http-host`: HTTP server host address (default: `127.0.0.1`)
- `--http-port`: HTTP server port (default: `8080`, range: 1-65535)
- `--cors-origins`: Comma-separated list of allowed CORS origins (optional)

After starting the server, configure your MCP client to connect to the specified URL (e.g., `http://127.0.0.1:8080`).

### Command Line Arguments

#### Transport Options

- `--transport {stdio,http}`: Transport type. Default: `stdio`

#### Mechanical Connection Options (Works with Both Transports)

The following Mechanical connection arguments work with both STDIO and HTTP transports:

```console
# Connect to Mechanical on startup
python -m ansys.mechanical.mcp --connect-on-startup --ip 192.168.1.100 --port 10000

# With HTTP transport
python -m ansys.mechanical.mcp --transport http --connect-on-startup --ip 192.168.1.100 --port 10000
```

**Options**:
- `--ip`: Mechanical IP address or hostname (default: `127.0.0.1`)
- `--port`: Mechanical gRPC port (default: `10000`, range: 1-65535)
- `--connect-on-startup`: Automatically connect to Mechanical when the server starts

> [!WARNING]
> When `--connect-on-startup` is used, the connection is locked and the following tools are disabled: `launch_mechanical`, `connect_to_mechanical`, and `disconnect_from_mechanical`.

#### HTTP Transport Options

- `--http-host`: HTTP server host address (default: `127.0.0.1`)
- `--http-port`: HTTP server port (default: `8080`, range: 1-65535)
- `--cors-origins`: Comma-separated list of allowed CORS origins (optional)

#### gRPC Transport Mode Options

- `--transport-mode {auto,insecure,mtls,wnua}`: gRPC transport mode for Mechanical connections. Default: auto-detect.
- `--certs-dir`: Path to directory containing mTLS certificate files (`ca.crt`, `client.crt`, `client.key`)

The gRPC transport mode determines how the MCP server authenticates with the Mechanical gRPC server:

| Mode | Description | Platform | Requires Certs? |
|------|-------------|----------|----------------|
| `auto` | Auto-detect based on platform and certificate availability (default) | All | No |
| `insecure` | Plaintext gRPC without encryption | All | No |
| `mtls` | Mutual TLS with certificate-based authentication | All | Yes |
| `wnua` | Windows Named User Authentication | Windows only | No |

**Auto-detection behavior** (when `--transport-mode` is not specified):
- **Windows**: Defers to PyMechanical's default (`wnua`)
- **Linux/Docker**: Uses `mtls` if certificate files are found; otherwise uses `insecure`

The transport mode can also be set via the `PYMECHANICAL_TRANSPORT_MODE` environment variable.
The certificate directory can also be set via the `ANSYS_GRPC_CERTIFICATES` environment variable.

> [!IMPORTANT]
> The client transport mode **must match** the mode the Mechanical server was started with. There is no auto-negotiation.

#### Special Environment Options

- `--on-aali`: Specify that the MCP server is running on an AALI environment. This disables certain tools that are not compatible with AALI

## Usage

### Starting a Mechanical Instance

You have several options to start and connect to Mechanical:

#### Option 1: Launch Mechanical through MCP (Recommended for new instances)

Use the `launch_mechanical` tool to start a new Mechanical instance that will be automatically connected:

Through your AI assistant:

> "Launch a new Mechanical instance"

or with specific options:

> "Launch Mechanical with batch mode enabled"

This flexible approach allows you to:
- Start new Mechanical instances on-demand
- Specify custom settings (batch mode, version, etc.)
- Automatically establish connection to the launched instance

#### Option 2: Connect to an existing Mechanical instance

Use the `connect_to_mechanical` tool to establish connections dynamically:

Through your AI assistant:

> "Connect to Mechanical on localhost port 10000"

or

> "Connect to Mechanical on 192.168.1.100 port 10001"

This flexible approach allows you to:

- Connect to different Mechanical instances during a session
- Work with multiple Mechanical servers without restarting the MCP server

#### Option 3: Auto-connect on MCP startup

Use the `--connect-on-startup` flag to automatically connect when the MCP server starts:

```console
python -m ansys.mechanical.mcp --connect-on-startup --ip 127.0.0.1 --port 10000
```

> [!WARNING]
> When using `--connect-on-startup`, the connection is locked and you cannot use `launch_mechanical`, `connect_to_mechanical`, or `disconnect_from_mechanical` tools.

By default, the server connects to Mechanical on `localhost:10000` when using Option 2 or 3.

### Run Mechanical Scripts

Use `run_python_script` tool to run Mechanical Python scripts. For instance:

> Run a script to get the current model's geometry information.

For running multiple scripts efficiently, use `run_multiple_scripts` tool:

> Run these scripts to set up a structural analysis with material properties and boundary conditions.

This tool runs scripts sequentially, which is useful for multi-step workflows.

### Custom Python Code Execution

Use `run_python_code` tool to execute custom Python and PyMechanical code:

> Execute this Python code: model = ExtAPI.DataModel.Project.Model; print(f"Model has {model.Geometry.Children.Count} geometry objects")

This is useful for:
- Custom data processing and analysis
- Advanced visualizations
- NumPy/Pandas data manipulation
- Complex computations not available through direct Mechanical scripting

### Creating Custom Plots

Use `create_custom_plot` tool to create custom matplotlib plots:

> Create a matplotlib plot showing stress distribution from the analysis results

This tool is specifically for custom plots using Python visualization libraries.


## Available Tools

### Mechanical Connection and Instance Management

#### `launch_mechanical`

Launch a new Mechanical instance and automatically connect to it.

**Parameters**:
- `exec_file` (string, optional): Path to the Mechanical executable. If None, PyMechanical will find it automatically
- `port` (int, optional): gRPC port for Mechanical to listen on. If None, defaults to 10000
- `batch` (bool, optional): Whether to launch in batch mode. Default: True
- `version` (string, optional): Mechanical version to run (e.g., "252" for 2025 R2). If None, uses latest installed

**Returns**: Launch status message with Mechanical version and connection information

> [!NOTE]
> This tool is disabled when `--connect-on-startup` is used or when running on AALI environments.

#### `connect_to_mechanical`

Connect to an existing Mechanical instance.

**Parameters**:
- `ip` (string, optional): IP address where Mechanical is running. Default: "127.0.0.1"
- `port` (int, optional): gRPC port where Mechanical is listening. Default: 10000

**Returns**: Connection status with Mechanical version information

> [!NOTE]
> This tool is disabled when `--connect-on-startup` is used or when running on AALI environments.

#### `disconnect_from_mechanical`

Disconnect from the currently connected Mechanical instance.

**Returns**: Disconnection status message

> [!NOTE]
> This tool is disabled when `--connect-on-startup` is used or when running on AALI environments.

#### `list_mechanical_instances`

List all Mechanical instances running on the local machine by scanning for active gRPC servers.
Inside a Docker container, process scanning is limited to the container, so the tool returns
a message directing users to `connect_to_mechanical` instead.

**Returns**: Formatted table of instances, or a Docker-aware message.

### Mechanical Status and Information

#### `check_mechanical_status`

Check the status and comprehensive information of the connected Mechanical instance.

**Returns**: JSON string containing comprehensive Mechanical status information including:
- Connection details (version, IP, port, project directory)
- Product information (version, build date)
- Model information (name, product version)

#### `check_mechanical_installed`

Check if Mechanical is installed on the system.
Inside a Docker container, reports the configured connection target instead
(Mechanical is expected on the host, not in the container).

**Returns**: Installation status, or configured host target when in Docker.

> [!NOTE]
> This tool is disabled when running on AALI environments.

#### `get_model_info`

Get detailed information about the current model in Mechanical.

**Returns**: JSON string containing model information including:
- Project info (name, product version)
- Model info (name)
- Geometry info (body count)
- Mesh info (node count, element count)
- Analysis count

#### `get_project_directory`

Get the project directory of the Mechanical instance.

**Returns**: The project directory path

#### `screenshot`

Capture a screenshot of the current Mechanical view.

**Parameters**:
- `view_type` (string, optional): Type of view to capture: "model", "mesh", or "result". Default: "model"

**Returns**: List containing:
- TextContent with the screenshot file path
- ImageContent with the base64-encoded image data (if successful)

### File Operations

#### `list_files`

List files in the Mechanical working directory.

**Returns**: List of files in the working directory

#### `upload_file`

Upload a file to the Mechanical instance's working directory.

**Parameters**:
- `file_path` (string): Path to the local file to upload

**Returns**: Upload status message

#### `download_file`

Download a file from the Mechanical instance's working directory.

**Parameters**:
- `file_name` (string): Name of the file to download
- `target_dir` (string, optional): Local directory to save the file. If None, uses current directory

**Returns**: Download status message with local file path

#### `clear_mechanical`

Clear the Mechanical database, providing a fresh start for a new analysis.

**Returns**: Clear status message

### Mechanical Script Execution

#### `run_python_script`

Execute a Python script inside Mechanical using the Mechanical scripting API (IronPython). The script has access to Mechanical's ExtAPI, DataModel, Model, Tree, and Graphics entry points.

**Parameters**:
- `script` (string): The Python script to execute inside Mechanical

**Returns**: Script execution result with the string value of the last executed statement

#### `run_python_script_from_file`

Execute a Python script file inside Mechanical.

**Parameters**:
- `file_path` (string): Path to the Python script file to execute

**Returns**: Script execution result

#### `run_multiple_scripts`

Execute multiple Mechanical Python scripts in sequence.

**Parameters**:
- `scripts` (list of strings): List of Mechanical Python scripts to execute

**Returns**: Execution result with summary of scripts executed

> [!NOTE]
> This tool runs scripts sequentially, useful for multi-step workflows. This tool is disabled when running on AALI environments.

### Python Session and Custom Processing

#### `run_python_code`

Execute arbitrary Python and PyMechanical code in a persistent Python session.

**Parameters**:
- `code` (string): The Python code to execute
- `timeout` (int, optional): Maximum time in seconds to allow for code execution. Default: 60 seconds

**Returns**: JSON string with execution result containing:
- `success` (boolean): Whether execution succeeded
- `stdout` (string): Standard output from the code
- `stderr` (string): Standard error output
- `message` or `error` (string): Status message or error details

**Use cases**:
- Custom data processing and analysis
- Advanced visualizations
- NumPy/Pandas data manipulation
- Custom matplotlib plots

#### `create_custom_plot`

Create custom plots using matplotlib in the persistent Python session.

**Parameters**:
- `plot_code` (string): Python code to create the plot. Should use matplotlib.pyplot
- `plot_type` (string, optional): Type of plot: "matplotlib". Default: "matplotlib"
- `timeout` (int, optional): Maximum time in seconds for plot generation. Default: 60 seconds

**Returns**: List containing:
- TextContent with the plot creation status message
- ImageContent with the base64-encoded image data (if successful)

**Pre-configured helpers in persistent session**:
- `save_matplotlib_plot(filename, dpi)`: Save matplotlib plots

> [!IMPORTANT]
> This tool is specifically designed for custom plots using Python visualization libraries. This tool is disabled when running on AALI environments.

### Workflow Context and Guidance

The following context tools provide comprehensive guidelines and best practices for Mechanical workflows. These tools are disabled when running on AALI environments.

#### `get_guidelines_for_workflow_overview`

Get general Mechanical simulation workflow overview context covering the complete simulation process, PyMechanical architecture, API entry points, and code execution patterns.

#### `get_guidelines_for_geometry_import`

Get geometry import and preparation guidelines for Mechanical preprocessing.

#### `get_guidelines_for_materials`

Get material model definition guidelines with default assumptions for structural and thermal analyses.

#### `get_guidelines_for_meshing`

Get mesh generation guidelines including quality considerations and best practices for Mechanical.

#### `get_guidelines_for_analysis_setup`

Get analysis setup guidelines including analysis type selection and configuration.

#### `get_guidelines_for_boundary_conditions`

Get boundary conditions and loads application guidelines for different analysis types in Mechanical.

#### `get_guidelines_for_solution`

Get solution phase guidelines including solver configuration and convergence monitoring.

#### `get_guidelines_for_postprocessing`

Get postprocessing phase guidelines for extracting and visualizing results in Mechanical.

#### `get_guidelines_for_named_selections`

Get guidelines for creating and using named selections in Mechanical.

#### `get_guidelines_for_general_rules`

Get general rules and best practices for Mechanical simulations including accuracy factors, verification steps, and common pitfalls to avoid.

## Development

### Installation From Source

1. Clone the repository:

```bash
git clone https://github.com/ansys/pymechanical-mcp.git
cd pymechanical-mcp
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

3. Install the package:

```bash
pip install -e .
```

This will install the package in editable mode along with all dependencies defined in `pyproject.toml`.

### Development Installation

For development with additional tools (pytest, black, mypy, pre-commit, etc.):

```bash
pip install -e ".[dev]"
```

After installing development dependencies, set up pre-commit hooks:

```bash
pre-commit install
```

This will automatically run code quality checks (black, isort, flake8, mypy, etc.) before each commit.

### Integrating with AI Assistants

This MCP server can be integrated with MCP-compatible AI assistants (like Claude Desktop, etc.). Add the server configuration to your MCP settings file:


#### From PyPI (Coming Soon)

> **⚠️ Note:** The PyPI installation method described below is not yet available. This package has not been published to PyPI. For now, use the development installation methods shown in the sections below.

Once published to PyPI, you'll be able to run the server directly using `uvx`:

<details>
<summary><b>VS Code integration</b></summary>

```json
{
  "servers": {
    "pymechanical": {
      "type": "stdio",
      "command": "uvx",
      "args": ["ansys-mechanical-mcp"]
    }
  }
}
```

</details>

<details>
<summary><b>Other tools like Claude Code</b></summary>

```json
{
  "mcpServers": {
    "pymechanical": {
      "command": "uvx",
      "args": ["ansys-mechanical-mcp"]
    }
  }
}
```

</details>

#### From local installation

If you are doing development, you can use the server as it is in the GitHub repository.
To do that, you should clone to a directory.

<details>
<summary><b>VS Code integration</b></summary>

You should add the following to your `.vscode/mcp.json` file:

```json
{
  "servers": {
    "pymechanical": {
      "type": "stdio",
      "command": "./.venv/bin/python",
      "args": ["-m", "ansys.mechanical.mcp"]
		}
	}
}
```

If you prefer `uv`:

```json
{
  "servers": {
    "pymechanical": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "-m", "ansys.mechanical.mcp"]
    }
  }
}
```

</details>


<details>
<summary><b>Other tools like Claude Code</b></summary>

```json
{
  "mcpServers": {
    "pymechanical": {
      "command": "/path/to/venv/python",
      "args": ["-m", "ansys.mechanical.mcp"],
    }
  }
}
```
The Python virtual environment should have `pymechanical-mcp` installed.

Or if you prefer `uv`:
```json
{
  "mcpServers": {
    "pymechanical": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/pymechanical-mcp", "python", "-m", "ansys.mechanical.mcp"]
    }
  }
}
```

</details>

## Testing

The project includes a comprehensive pytest-based testing suite covering all functionality.

### Quick set up

Run unit tests (fast, no Mechanical required):

```bash
pytest -m "not integration"
```

Run all tests with coverage:

```bash
pytest --cov=ansys.mechanical.mcp --cov-report=html
```

Run integration tests (requires Mechanical on localhost:10000):

```bash
pytest -m integration
```

### Test Commands Reference

```bash
# Run specific test file
pytest tests/test_tools.py

# Run with verbose output
pytest -v

# Generate HTML coverage report
pytest --cov=ansys.mechanical.mcp --cov-report=html
# Open htmlcov/index.html to view

# Run specific test
pytest tests/test_tools.py::TestRunMechanicalScript::test_run_script_success
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Install development dependencies: `pip install -e ".[dev]"`
4. Install pre-commit hooks: `pre-commit install`
5. Make your changes
6. Add tests for new functionality (aim for >80% coverage)
7. Run tests: `pytest -m "not integration"`
8. Commit (pre-commit hooks will run automatically)
9. Push and submit a pull request

The pre-commit hooks and CI will ensure code quality. If hooks fail, review the changes, stage them with `git add .`, and commit again.
pre-commit run --all-files

### Adding a New Tool

`pymechanical-mcp` uses connection-aware tool visibility: tools that need a
live Mechanical session are hidden until `launch_mechanical` or
`connect_to_mechanical` succeeds. This is enforced via tool **tags**.

When you add a new `@app.tool(...)` to `src/ansys/mechanical/mcp/tools.py`:

- **Default case: the tool needs a Mechanical connection.** Tag it with
  `REQUIRES_MECHANICAL_TAG` (defined at the top of `tools.py`):

  ```python
  @app.tool(tags={REQUIRES_MECHANICAL_TAG})
  def my_new_tool(ctx: Context, ...) -> str:
      ...
  ```

  The server disables it until a session exists, then unlocks it via
  `enable_components(tags={REQUIRES_MECHANICAL_TAG})`.

- **Special case: the tool is genuinely usable BEFORE any Mechanical
  session** (e.g. an installation check). Do NOT add the tag, and add the
  tool's name to the `ALWAYS_AVAILABLE_TOOLS` allowlist in
  `tests/test_tools.py::TestRequiresMechanicalVisibility::test_no_tool_surface_drift`.

The `test_no_tool_surface_drift` test will fail if a new tool is neither
tagged nor on the allowlist. This is intentional: it forces every
contributor to make an explicit decision about pre-connection visibility.


## Architecture

The server uses the PyAnsysBaseMCP framework (built on FastMCP) with lifespan management:

```mermaid
flowchart TB
    subgraph Client["AI Client (Claude, VS Code Copilot, etc.)"]
        LLM[Large Language Model]
    end

    subgraph MCP["PyMechanical MCP Server"]
        direction TB
        Transport["Transport Layer<br/>(STDIO / HTTP+SSE)"]
        Server["PyMechanicalMCP<br/>(FastMCP Server)"]
        Context["PyMechanicalAppContext"]

        subgraph Tools["MCP Tools"]
            direction LR
            ConnTools["Connection Tools<br/>• launch_mechanical<br/>• connect_to_mechanical<br/>• disconnect_from_mechanical"]
            ExecTools["Execution Tools<br/>• run_python_script<br/>• run_multiple_scripts<br/>• check_mechanical_status"]
            PyTools["Python Session Tools<br/>• run_python_code<br/>• create_custom_plot"]
        end

        subgraph ContextTools["Context Tools (Workflow Guidance)"]
            Guidelines["• Geometry Import<br/>• Material Assignment<br/>• Mesh Generation<br/>• Boundary Conditions<br/>• Analysis Setup<br/>• Results Processing"]
        end

        PythonSession["Persistent Python Session<br/>(matplotlib, numpy, pandas)"]
    end

    subgraph Mechanical["Ansys Mechanical"]
        direction TB
        MechInstance["Mechanical Instance<br/>(Local/Remote/Docker)"]
        gRPC["gRPC Server<br/>(Port 10000)"]
        Scripting["IronPython Scripting<br/>• ExtAPI<br/>• Model<br/>• DataModel<br/>• Graphics"]
    end

    LLM <-->|"MCP Protocol"| Transport
    Transport <--> Server
    Server --> Context
    Context --> Tools
    Context --> ContextTools
    Context --> PythonSession

    ExecTools <-->|"PyMechanical<br/>run_python_script()"| gRPC
    ConnTools <-->|"connect_to_mechanical()<br/>launch_mechanical()"| gRPC
    gRPC <--> MechInstance
    MechInstance --> Scripting

    style Client fill:#e1f5fe
    style MCP fill:#fff3e0
    style Mechanical fill:#e8f5e9
    style Tools fill:#fce4ec
    style ContextTools fill:#f3e5f5
```

### Workflow Overview

1. **Startup**:
   - Initializes a persistent Python session for custom code execution
   - Optionally connects to an existing Mechanical instance (if `--connect-on-startup` is used)
   - Otherwise, waits for dynamic connection through tools
2. **Runtime**:
   - Exposes tools for Mechanical interaction
   - Manages dynamic Mechanical connections
   - Executes scripts in both Mechanical and Python sessions
   - Provides workflow guidance through context tools
3. **Shutdown**:
   - Gracefully disconnects from Mechanical
   - Cleans up persistent Python session resources

### Application Context

The server uses a strongly-typed `PyMechanicalAppContext` that includes:
- Mechanical instance connection
- Persistent Python session for custom code
- Transport configuration (STDIO or HTTP)
- Connection settings (IP, port, auto-connect options)

### Adding New Tools

To add new Mechanical tools, edit `src/ansys/mechanical/mcp/tools.py` and use the `@app.tool()` decorator:

```python
@app.tool()
def your_new_tool(ctx: Context, param: str) -> str:
    """Description of your tool."""
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return "No Mechanical connection available. Use connect_to_mechanical to establish a connection."

    # Your Mechanical operations here
    result = mechanical.run_python_script("your_script_here")

    return f"Result: {result}"
```

### Adding Context Tools

To add workflow guidance tools, edit `src/ansys/mechanical/mcp/contexts.py` and use the `@app.tool()` decorator:

```python
@app.tool()
def get_guidelines_for_your_topic() -> str:
    """Get guidance for your specific topic.

    Returns
    -------
    str
        Detailed guidelines and best practices.
    """
    return """# Your Topic Guidelines

    Your comprehensive guidance here...
    """
```

### Tool Enabling/Disabling

Tools can be conditionally enabled or disabled based on server configuration:

```python
# Disable tool when connection is locked or on AALI
@app.tool(enabled=not (session.locked_connection or session.on_aali))
def connect_to_mechanical(ctx: Context, port: int = 10000, ip: str = "127.0.0.1") -> str:
    # Tool implementation
    pass
```


## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Resources

- [PyMechanical Documentation](https://mechanical.docs.pyansys.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Ansys Mechanical](https://www.ansys.com/products/structures/ansys-mechanical)

## Docker Deployment

Deploy PyMechanical MCP Server as a containerized application with HTTP transport for remote access. The server can connect to either a containerized Mechanical instance or a local Mechanical installation.

> [!WARNING]
> The HTTP transport is not encrypted. Use only in trusted networks or with a reverse proxy (Nginx, HAProxy) providing TLS/SSL.

### Quick Start with Docker Compose

The easiest way to run both Mechanical and the MCP server is using Docker Compose.

**1. Configure environment:**

```bash
# Copy and edit the environment file
cp env.example .env
```

Edit `.env` with your settings:
- `PYMECHANICAL_IP`: Set to `mechanical` (container), `host.docker.internal` (local Windows/Mac), or IP address (remote)
- `ANSYSLMD_LICENSE_FILE`: Your ANSYS license server
- `CONNECT_ON_STARTUP`: Set to `true` to auto-connect, `false` (default) for dynamic connection

**2. Start services:**

```bash
# Start Mechanical container and MCP server
docker compose up

# Or run in detached mode
docker compose up -d
```

The MCP server will be available at `http://localhost:8080`.

### Docker Compose Configuration

The `docker-compose.yml` includes two services:

- **pymechanical-mcp**: MCP server with HTTP transport
- **mechanical**: ANSYS Mechanical container (optional, can connect to local instance instead)

To connect to a local Mechanical instance instead of the container:
1. Remove or comment out the `mechanical` service and `depends_on` in `docker-compose.yml`
2. Set `PYMECHANICAL_IP=host.docker.internal` (Windows/Mac)
3. Start Mechanical locally with gRPC server enabled

### Building Standalone Image

The MCP server depends on `ansys-common-mcp`, which is hosted on a **private PyPI feed**.
You must set the `PYANSYS_PYPI_PRIVATE_PAT` environment variable to a Personal Access Token
(PAT) with read access to the [PyAnsys Azure DevOps feed](https://dev.azure.com/pyansys/_packaging/pyansys/pypi/simple/)
before building the image.

> [!NOTE]
> `PYANSYS_PYPI_PRIVATE_PAT` must be set on the machine that runs `docker build`.
> The token is only used at build time and is **not** baked into the final image.

#### On Linux / macOS

From the repository root:

```bash
export PYANSYS_PYPI_PRIVATE_PAT="your_pat_here"

DOCKER_BUILDKIT=1 docker build \
  --build-arg PYANSYS_PYPI_INDEX_URL="https://${PYANSYS_PYPI_PRIVATE_PAT}@pkgs.dev.azure.com/pyansys/_packaging/pyansys/pypi/simple/" \
  -f docker/Dockerfile -t pymechanical-mcp .
```

#### On Windows (PowerShell)

From the repository root:

```pwsh
$env:PYANSYS_PYPI_PRIVATE_PAT = "your_pat_here"

docker build `
  --build-arg PYANSYS_PYPI_INDEX_URL="https://$($env:PYANSYS_PYPI_PRIVATE_PAT)@pkgs.dev.azure.com/pyansys/_packaging/pyansys/pypi/simple/" `
  -f docker\Dockerfile -t pymechanical-mcp .
```

### Running Standalone Container

By default, the container starts **without** an active Mechanical connection. Use the `connect_to_mechanical` tool from your MCP client to connect dynamically.

**Basic (auto-detect transport mode, recommended):**
```bash
# The server auto-detects: no certs mounted → insecure gRPC
docker run -p 8080:8080 -e PYMECHANICAL_IP=host.docker.internal pymechanical-mcp
```

**With mTLS certificates (secure connection):**
```bash
# Mount your certificate directory → auto-detects mtls
docker run -p 8080:8080 \
  -e PYMECHANICAL_IP=host.docker.internal \
  -v /path/to/certs:/app/certs:ro \
  pymechanical-mcp
```

The certificate directory must contain `ca.crt`, `client.crt`, and `client.key`.

**With auto-connect on startup (locked connection):**
```bash
docker run -p 8080:8080 \
  -e PYMECHANICAL_IP=host.docker.internal \
  -e CONNECT_ON_STARTUP=true \
  pymechanical-mcp
```

**Connect to remote Mechanical:**
```bash
docker run -p 8080:8080 \
  -e PYMECHANICAL_IP=192.168.1.100 \
  -e PYMECHANICAL_PORT=10001 \
  pymechanical-mcp
```

**Explicit transport mode override:**
```bash
docker run -p 8080:8080 \
  -e PYMECHANICAL_IP=host.docker.internal \
  -e PYMECHANICAL_TRANSPORT_MODE=insecure \
  pymechanical-mcp
```

### gRPC Transport Mode in Docker

When the MCP server runs inside a Docker container (Linux), the gRPC transport mode is **auto-detected** by default:

| Scenario | Certs mounted? | Auto-detected mode | Secure? |
|----------|---------------|-------------------|---------|
| No certs, no env var | No | `insecure` | ❌ |
| Certs at `/app/certs` | Yes | `mtls` | ✅ |
| `PYMECHANICAL_TRANSPORT_MODE=insecure` | N/A | `insecure` | ❌ |
| `PYMECHANICAL_TRANSPORT_MODE=mtls` | Yes | `mtls` | ✅ |

> [!IMPORTANT]
> The client transport mode **must match** the mode the Mechanical server was started with. If your Mechanical instance was started with the default Windows mode (`wnua`), you need to restart it with `--transport-mode insecure` or `--transport-mode mtls` to allow cross-platform connections from Docker.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYMECHANICAL_IP` | `host.docker.internal` | Mechanical IP/hostname |
| `PYMECHANICAL_PORT` | `10000` | Mechanical gRPC port |
| `HTTP_HOST` | `0.0.0.0` | HTTP server host |
| `HTTP_PORT` | `8080` | HTTP server port |
| `PYMECHANICAL_TRANSPORT_MODE` | *(auto)* | gRPC transport mode: `auto`, `insecure`, `mtls`, `wnua` |
| `ANSYS_GRPC_CERTIFICATES` | - | Path to mTLS certificate directory inside the container |
| `CONNECT_ON_STARTUP` | `false` | Whether to connect to Mechanical on startup (`true`/`false`) |
| `ANSYSLMD_LICENSE_FILE` | - | License server (format: `port@server`) |

### MCP Client Configuration

Configure your MCP client to connect to the HTTP server:

**VS Code** (`.vscode/mcp.json`):
```json
{
  "servers": {
    "pymechanical": {
      "type": "http",
      "url": "http://localhost:8080"
    }
  }
}
```

## Support

For issues and questions:

- Open an issue on GitHub
- Consult the PyMechanical documentation
- Check the Ansys Developer Portal

## Acknowledgments

Built with:

- [PyMechanical](https://github.com/ansys/pymechanical) - Python interface for Ansys Mechanical
- [FastMCP](https://github.com/jlowin/fastmcp) - Fast Model Context Protocol implementation
- [Ansys Mechanical](https://www.ansys.com/) - Finite element analysis software
