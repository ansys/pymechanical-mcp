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

"""List of tools in PyMechanical-MCP."""

import asyncio
import base64
import inspect
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import tempfile
import time
from typing import Any, cast
import uuid
import warnings

# Import Mechanical at module level to avoid import during tool execution
# The import happens during server startup, before STDIO transport is active
from ansys.common.mcp.tools import execute_python_code
import ansys.tools.common.path as atp  # pyright: ignore[reportMissingTypeStubs]
from fastmcp.server import Context
from fastmcp.server.server import get_logger

from ansys.mechanical import core as pymechanical  # pyright: ignore[reportMissingTypeStubs]
from ansys.mechanical.mcp import app, introspection
from ansys.mechanical.mcp.errors import (
    InvalidArgumentsError,
    MechanicalMCPError,
    NotConnectedError,
    StalePreviewError,
    UpstreamError,
)
from ansys.mechanical.mcp.helpers import (
    _is_docker,
    _probe_grpc_endpoint,
    get_info,
    launched_mechanical_processes,
    list_instances,
    resolve_transport_mode,
    server_child_pids,
    stop_processes,
)
from ansys.mechanical.mcp.server import session
from mcp.types import ImageContent, TextContent, ToolAnnotations

logger = get_logger(__name__)


# Tag applied to all tools that require an active Mechanical connection.
# These tools are disabled at startup (before Mechanical is connected) and enabled
# once a connection is established via connect_to_mechanical or launch_mechanical.
REQUIRES_MECHANICAL_TAG = "requires_mechanical"

#: Views that ``screenshot`` can activate before exporting the image.
_SCREENSHOT_VIEW_TYPES = ("model", "mesh", "result")

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Helpers prepended to the introspection scripts that run inside Mechanical.
# Remote Mechanical sessions run IronPython 2.7 (including 2026 R1 and 2027 R1),
# so this stays f-string free and
# every accessor is guarded: a missing property must degrade, never raise.
_SCRIPT_HELPERS = """
import json


def _quantity(value):
    # Normalize a Mechanical Quantity to value/unit, tolerating plain numbers.
    if value is None:
        return None
    try:
        return {'value': float(value.Value), 'unit': str(value.Unit)}
    except:
        pass
    try:
        return {'value': float(value), 'unit': None}
    except:
        return {'display': str(value)}


def _category(obj):
    # Return the Mechanical object category, for example EquivalentStress.
    try:
        return str(obj.DataModelObjectCategory)
    except:
        return 'Unknown'

"""


def _structured_error(error: MechanicalMCPError) -> str:
    """Serialize a known tool error for clients that can handle structured results."""
    logger.info("%s: %s", error.error_code, error.message)
    return json.dumps(error.to_dict(), ensure_ascii=False)


def _mechanical_or_error(ctx: Context) -> tuple[Any | None, str | None]:
    """Return the active Mechanical session or a consistent structured error."""
    mechanical = ctx.request_context.lifespan_context.mechanical
    if mechanical is None:
        return None, _structured_error(
            NotConnectedError(
                "No Mechanical connection available. Use connect_to_mechanical "
                "to establish a connection."
            )
        )
    return mechanical, None


def _python_session_status(python_session: Any | None) -> dict[str, Any]:
    """Return safe persistent-session state without allowing diagnostics to fail."""
    if python_session is None:
        return {"available": False, "running": False, "python_executable": None}

    try:
        running = bool(python_session.is_running())
    except Exception as exc:
        return {
            "available": True,
            "running": False,
            "python_executable": getattr(python_session, "python_executable", None),
            "error": str(exc),
        }

    return {
        "available": True,
        "running": running,
        "python_executable": getattr(python_session, "python_executable", None),
    }


async def _resolve_launch_batch_mode(ctx: Context, batch: bool | None) -> bool:
    """Resolve the Mechanical launch mode.

    When the caller omits ``batch``, try to elicit a GUI-vs-batch choice from
    the MCP client. If elicitation is unavailable or the user declines, default
    to GUI mode for interactive workflows.
    """
    if batch is not None:
        return bool(batch)

    elicit = getattr(ctx, "elicit", None)
    if elicit is None or not inspect.iscoroutinefunction(elicit):
        return False

    try:
        result = await elicit(
            (
                "Choose how to launch Mechanical. GUI mode opens a visible "
                "Mechanical window and is recommended for interactive MCP "
                "workflows. Batch mode runs in the background without a visible UI."
            ),
            {
                "gui": {"title": "GUI (recommended)"},
                "batch": {"title": "Batch / background"},
            },
            response_title="Launch mode",
            response_description="Select how the Mechanical gRPC session should be started.",
        )
    except Exception as exc:
        logger.info(
            "Launch-mode elicitation unavailable; defaulting to GUI mode: %s",
            exc,
        )
        return False

    if result.action == "accept":
        selection = str(result.data)
        return selection == "batch"

    return False


#: Accepted spellings of a Mechanical release: ``261``, ``v261``, ``26.1``, and ``2026 R1``.
_VERSION_PATTERNS = (
    re.compile(r"v?(\d{2})(\d)"),
    re.compile(r"(\d{2})\.(\d)"),
    re.compile(r"20(\d{2})r(\d)"),
)

#: Seconds to wait for a liveness probe before treating a slow session as alive and busy.
_LIVENESS_TIMEOUT = 10.0

_ALREADY_CONNECTED_MESSAGE = (
    "Already connected to a Mechanical instance. "
    "Disconnect first using disconnect_from_mechanical tool."
)

#: PyMechanical's timeouts for starting and for connecting to Mechanical, in seconds.
_LAUNCH_START_TIMEOUT = 300
_CONNECT_TIMEOUT = 120

#: Grace period after PyMechanical's own timeout before an operation is abandoned.
_SESSION_DEADLINE_MARGIN = 60.0

_START_INSTANCE_ENV = "PYMECHANICAL_START_INSTANCE"


def _start_instance_refusal() -> str | None:
    """Return why launching is disabled by ``PYMECHANICAL_START_INSTANCE``, if it is.

    The variable is unset by default, which allows launching. PyMechanical itself reads
    it, so only the exact values ``true`` and ``false`` (any case) are valid.
    """
    value = os.environ.get(_START_INSTANCE_ENV)
    if value is None or value.lower() == "true":
        return None
    if value.lower() == "false":
        return (
            f"Starting Mechanical is disabled because the environment variable "
            f"{_START_INSTANCE_ENV} is set to '{value}' for this MCP server. Remove it or "
            "set it to 'true' to allow launch_mechanical, or use connect_to_mechanical "
            "to attach to a Mechanical instance that is already running."
        )
    return (
        f"The environment variable {_START_INSTANCE_ENV} has the invalid value {value!r}. "
        "Set it to 'true' or 'false', or remove it."
    )


class _SessionJob:
    """A launch or connect that runs in a worker thread and outlives the request that started it.

    The result is recorded in the context even if the requesting client cancels. An
    abandoned job's late result is discarded, and only the Mechanical processes that a
    launch started are ever stopped.
    """

    def __init__(
        self,
        kind: str,
        context: Any,
        future: "asyncio.Future[Any]",
        timeout: float,
        baseline: frozenset[int] | None,
    ) -> None:
        self.kind = kind
        self.context = context
        self.future = future
        self.started = time.monotonic()
        self.deadline = self.started + timeout
        self.baseline = baseline
        self.abandoned = False
        self.abandoned_event = asyncio.Event()
        future.add_done_callback(self._finished)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def abandon(self) -> list[Any]:
        """Give up on the operation and return the processes it started, to be stopped."""
        self.abandoned = True
        self.abandoned_event.set()
        if self.context.session_job is self:
            self.context.session_job = None
        return self._own_processes()

    def _own_processes(self) -> list[Any]:
        # Only one job exists at a time, so new -grpc children belong to this launch.
        if self.baseline is None:
            return []
        return launched_mechanical_processes(self.baseline)

    def _finished(self, future: "asyncio.Future[Any]") -> None:
        if future.cancelled():
            return
        if self.abandoned:
            # A launch abandoned before its process existed can still start one later.
            if self.kind == "launch" and future.exception() is None:
                mechanical, _ = future.result()
                asyncio.get_running_loop().run_in_executor(None, _close_quietly, mechanical)
            return
        if self.context.session_job is self:
            self.context.session_job = None
        if future.exception() is not None:
            processes = self._own_processes()
            if processes:
                logger.warning("Stopping Mechanical processes left by a failed launch.")
                asyncio.get_running_loop().run_in_executor(None, stop_processes, processes)
            return
        mechanical, _ = future.result()
        self.context.mechanical = mechanical
        self.context.owns_mechanical = self.kind == "launch"
        app.enable(tags={REQUIRES_MECHANICAL_TAG})


def _pending_job(context: Any) -> _SessionJob | None:
    """Return the launch or connect operation in progress, if any."""
    job = getattr(context, "session_job", None)
    return job if isinstance(job, _SessionJob) else None


def _start_session_job(
    context: Any, kind: str, worker: Any, timeout: float, baseline: frozenset[int] | None
) -> _SessionJob:
    """Start ``worker`` in a thread and register it as the context's operation in progress."""
    future = asyncio.get_running_loop().run_in_executor(None, worker)
    job = _SessionJob(kind, context, future, timeout + _SESSION_DEADLINE_MARGIN, baseline)
    context.session_job = job
    return job


async def _busy_message(context: Any) -> str | None:
    """Return why a new launch or connect cannot start now, or ``None`` if it can.

    An operation past its deadline is treated as stuck: it is abandoned and the
    Mechanical processes it started are stopped, so a retry can start cleanly.
    """
    job = _pending_job(context)
    if job is not None:
        if job.remaining > 0:
            return (
                f"A Mechanical {job.kind} started {job.elapsed:.0f} s ago is still in "
                f"progress. It is recorded when it finishes, or stopped if it has not "
                f"finished within {job.remaining:.0f} s. Call check_mechanical_status "
                "to see when it is ready."
            )
        logger.warning("Abandoning a Mechanical %s that did not finish in time.", job.kind)
        await asyncio.to_thread(stop_processes, job.abandon())
    return await _reject_if_connected(context)


async def _await_session_job(job: _SessionJob) -> tuple[Any, dict[str, str]]:
    """Wait for ``job``; on deadline, abandon it and stop the processes it started.

    Cancelling the waiting request does not cancel the job itself.
    """
    abandoned = asyncio.ensure_future(job.abandoned_event.wait())
    try:
        done, _ = await asyncio.wait(
            {job.future, abandoned},
            timeout=job.remaining,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        abandoned.cancel()
    if job.abandoned:
        raise RuntimeError(f"The Mechanical {job.kind} was cancelled before it finished.")
    if job.future not in done:
        await asyncio.to_thread(stop_processes, job.abandon())
        raise TimeoutError(
            f"The Mechanical {job.kind} did not finish within "
            f"{job.deadline - job.started:.0f} s and was stopped. You can retry."
        )
    return cast(tuple[Any, dict[str, str]], job.future.result())


def _close_quietly(mechanical: Any) -> None:
    """Close a Mechanical instance this server launched, logging instead of raising."""
    try:
        mechanical.exit(force=True)
    except Exception as exc:
        logger.info("Could not close the launched Mechanical instance: %s", exc)


def _launch_worker(kwargs: dict[str, Any], requested: int | None) -> tuple[Any, dict[str, str]]:
    """Launch Mechanical and confirm it runs the requested release."""
    mechanical = pymechanical.launch_mechanical(**kwargs)
    try:
        version = str(mechanical.version)
        if requested is not None:
            try:
                actual: int | None = _normalize_mechanical_version(version)
            except ValueError:
                actual = None
            if actual is not None and actual != requested:
                raise RuntimeError(
                    f"Mechanical {actual} started, but {requested} was requested. "
                    "The instance was closed."
                )
        info = {"version": version, "project_directory": str(mechanical.project_directory)}
    except Exception:
        _close_quietly(mechanical)
        raise
    return mechanical, info


def _connect_worker(kwargs: dict[str, Any]) -> tuple[Any, dict[str, str]]:
    """Connect to a running Mechanical instance."""
    mechanical = pymechanical.connect_to_mechanical(**kwargs)
    return mechanical, {"version": str(mechanical.version)}


def _normalize_mechanical_version(version: str | int | float) -> int:
    """Convert a Mechanical release such as ``"26.1"`` or ``"2026 R1"`` to ``261``."""
    text = str(version).strip().lower().replace(" ", "")
    for pattern in _VERSION_PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return int(match.group(1)) * 10 + int(match.group(2))
    raise ValueError(
        f"Unrecognized Mechanical version {version!r}. Use the three-digit release "
        "number, for example '261' for 2026 R1."
    )


def _pypim_configured() -> bool:
    """Return whether PyPIM remote launching is configured; PyPIM honors ``version`` itself."""
    try:
        import ansys.platform.instancemanagement as pypim  # pyright: ignore
    except ImportError:
        return False
    try:
        return bool(pypim.is_configured())
    except Exception:
        return False


def _installed_mechanical_versions() -> list[int]:
    """Return the installed Ansys releases, newest first."""
    try:
        installations = atp.get_available_ansys_installations()
    except Exception:
        return []
    return sorted((release for release in installations if release > 0), reverse=True)


def _resolve_launch_executable(
    version: str | None, exec_file: str | None
) -> tuple[str | None, str | None]:
    """Return ``(exec_file, error)`` for a launch that honors the requested version.

    PyMechanical ignores ``version`` for local launches and starts the saved or newest
    installation, so the executable for the requested release is resolved here.
    """
    if version is None:
        return exec_file, None

    try:
        requested = _normalize_mechanical_version(version)
    except ValueError as exc:
        return None, str(exc)

    if exec_file is not None:
        try:
            actual = atp.version_from_path("mechanical", exec_file)
        except Exception:
            # Custom install layouts do not always encode the release in the path.
            return exec_file, None
        if actual != requested:
            return None, (
                f"exec_file is Mechanical {actual}, but version {requested} was requested. "
                "Pass a matching exec_file or omit one of the two parameters."
            )
        return exec_file, None

    if _pypim_configured():
        return None, None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            resolved = atp.get_mechanical_path(allow_input=False, version=requested)
        except Exception as exc:
            logger.info("Could not resolve Mechanical %s: %s", requested, exc)
            resolved = None
    if resolved:
        return str(resolved), None

    installed = _installed_mechanical_versions()
    available = ", ".join(str(release) for release in installed) or "none found"
    return None, (
        f"Mechanical {requested} was not found. Installed releases: {available}. "
        "Pass exec_file to launch a specific Mechanical executable."
    )


async def _session_is_alive(mechanical: Any) -> bool:
    """Return whether a Mechanical session still responds.

    A probe that does not answer within ``_LIVENESS_TIMEOUT`` is treated as a busy,
    live session so that a running solve is never mistaken for a dead connection.
    """
    try:
        if getattr(mechanical, "exited", False) is True:
            return False
    except Exception:
        return False

    def _probe() -> bool:
        try:
            return bool(mechanical.is_alive)
        except Exception:
            return False

    try:
        return await asyncio.wait_for(asyncio.to_thread(_probe), timeout=_LIVENESS_TIMEOUT)
    except TimeoutError:
        return True


async def _reject_if_connected(context: Any) -> str | None:
    """Return an error while a live session exists; drop a dead one so a new one can start."""
    if context.mechanical is None:
        return None
    if await _session_is_alive(context.mechanical):
        return _ALREADY_CONNECTED_MESSAGE
    logger.warning("Dropping a Mechanical session that no longer responds.")
    context.mechanical = None
    context.owns_mechanical = False
    context.change_previews.clear()
    return None


async def _set_mechanical_tools_visible(ctx: Context, visible: bool) -> None:
    """Show or hide the tools that need a Mechanical connection.

    The connection is shared by every client session, so the server-level rule is
    authoritative: session-scoped rules alone do not persist across requests with
    FastMCP 4. The session call is kept because it notifies the client that the
    tool list changed.
    """
    if visible:
        app.enable(tags={REQUIRES_MECHANICAL_TAG})
        await ctx.enable_components(tags={REQUIRES_MECHANICAL_TAG})
    elif not ctx.request_context.lifespan_context.static_tools:
        app.disable(tags={REQUIRES_MECHANICAL_TAG})
        await ctx.disable_components(tags={REQUIRES_MECHANICAL_TAG})


# Access type-safe lifespan context in tools
@app.tool()  # I would have expected the tag ``lifecycle`` to be added here and not only in toolset
def check_mechanical_status(ctx: Context) -> str:
    """Check the status of Mechanical initialization.

    This tool retrieves comprehensive information from the connected Mechanical
    instance including version, project directory, and connection status.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        JSON string containing comprehensive Mechanical status information including:

        - connection: Basic connection information (version, project_directory, is_alive)
        - product_info: Product version and build information

        Returns an error message if Mechanical is not available or has exited.
    """
    job = _pending_job(ctx.request_context.lifespan_context)
    if job is not None and ctx.request_context.lifespan_context.mechanical is None:
        return json.dumps(
            {
                "success": False,
                "in_progress": job.kind,
                "elapsed_seconds": round(job.elapsed),
                "error": (
                    f"A Mechanical {job.kind} is still in progress. Call "
                    "check_mechanical_status again shortly."
                ),
            }
        )

    mechanical, error = _mechanical_or_error(ctx)
    if error is not None:
        return error
    mechanical = cast(Any, mechanical)

    try:
        # Check if Mechanical has exited
        if hasattr(mechanical, "exited") and mechanical.exited:
            return "Mechanical instance has exited. Reconnect or launch a new instance."

        info = get_info(mechanical)
        python_session = ctx.request_context.lifespan_context.python_session
        info["python_session"] = _python_session_status(python_session)

        # Return as formatted JSON
        return json.dumps(info, indent=2, default=str)

    except Exception as e:
        error_msg = f"Error checking Mechanical status: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool()
def get_session_diagnostics(ctx: Context) -> str:
    """Return safe connection and persistent-Python-session diagnostics.

    This tool intentionally excludes environment variables, command histories,
    tokens, and certificate paths. Use it when diagnosing an MCP setup issue
    before sharing logs with a maintainer.
    """
    context = ctx.request_context.lifespan_context
    python_session = context.python_session
    mechanical = context.mechanical
    job = _pending_job(context)
    return json.dumps(
        {
            "mechanical_connected": mechanical is not None,
            "mechanical_alive": (
                bool(getattr(mechanical, "is_alive", False)) if mechanical is not None else False
            ),
            "mechanical_launched_by_server": (
                bool(context.owns_mechanical) if mechanical is not None else False
            ),
            "operation_in_progress": (
                {"kind": job.kind, "elapsed_seconds": round(job.elapsed)}
                if job is not None
                else None
            ),
            "grpc_transport_mode": context.grpc_transport_mode,
            "persistent_python": _python_session_status(python_session),
        },
        indent=2,
    )


@app.tool(tags={"aali"})
def check_mechanical_installed(ctx: Context) -> str:
    """Check if Mechanical is installed on the system.

    This tool checks whether Ansys Mechanical is properly installed and
    available on the system by inspecting standard installation paths.

    .. note::

       When PyMechanical-MCP runs inside a Docker container, the host
       filesystem is not accessible.  In this case, the tool probes the
       configured gRPC endpoint instead and reports whether a Mechanical
       server is reachable.

    Returns
    -------
    str
        Status message indicating whether Mechanical is installed or reachable.
    """
    logger.info("Checking if Mechanical is installed...")

    # Inside Docker we can't inspect the host filesystem, but we can probe
    # the configured gRPC endpoint to see if Mechanical is reachable.
    # NOTE: We prefer the env var over the context value because the CLI
    # ``--ip`` flag defaults to ``127.0.0.1`` which is wrong inside a
    # container (it would probe the container itself, not the host).
    if _is_docker():
        ip = os.environ.get(
            "PYMECHANICAL_IP",
            ctx.request_context.lifespan_context.mechanical_ip or "host.docker.internal",
        )
        port = int(
            os.environ.get(
                "PYMECHANICAL_PORT",
                str(ctx.request_context.lifespan_context.mechanical_port or 10000),
            )
        )
        logger.info("Running inside Docker; probing %s:%s", ip, port)
        probe = _probe_grpc_endpoint(ip, port)
        if probe["reachable"]:
            return (
                f"Running inside a Docker container: local installation "
                f"check is not available.\n"
                f"However, a Mechanical gRPC server is reachable at "
                f"{ip}:{port}.\n"
                f"Use 'connect_to_mechanical' to establish a session."
            )
        return (
            f"Running inside a Docker container: local installation "
            f"check is not available.\n"
            f"No Mechanical gRPC server detected at {ip}:{port} "
            f"(error: {probe['error']}).\n"
            f"Start Mechanical on the host machine with gRPC "
            f"enabled on port {port}, then retry."
        )

    try:
        from ansys.mechanical.core.mechanical import check_valid_mechanical

        is_installed = check_valid_mechanical()

        if is_installed:
            logger.info("Mechanical installation found")
            return "Mechanical is installed on this system."
        else:
            logger.info("Mechanical installation not found")
            return (
                "Mechanical is not installed on this system or cannot be found in the "
                "standard locations. Ensure Ansys Mechanical is properly installed "
                "and the installation path is correct."
            )

    except Exception as e:
        error_msg = f"Error checking Mechanical installation: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def run_python_script(
    ctx: Context,
    script: str | None = None,
    file_path: str | None = None,
) -> str:
    """Execute a Python script inside Mechanical.

    This tool runs a Python script block inside the connected Mechanical instance
    using Mechanical's scripting API. The script has access to Mechanical's
    ``ExtAPI``, ``DataModel``, ``Model``, ``Tree``, and ``Graphics`` entry points.

    Provide either an inline ``script`` string or a ``file_path`` pointing to a
    local Python file. When ``file_path`` is given, its contents are read and
    executed inside Mechanical.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    script : str, optional
        The Python script to execute inside Mechanical. Required when
        ``file_path`` is not provided.
    file_path : str, optional
        Path to a local Python script file whose contents are executed inside
        Mechanical. Takes precedence over ``script`` when both are provided.

    Returns
    -------
    str
        Script execution result. Returns the string value of the last executed
        statement, or an empty string if the value cannot be returned as a string.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if file_path is not None:
        path = Path(file_path)
        if not path.exists():
            return f"Script file not found: {file_path}"
        try:
            script = path.read_text(encoding="utf-8")
        except Exception as e:
            error_msg = f"Error reading script file '{file_path}': {str(e)}"
            logger.error(error_msg)
            return error_msg

    if script is None:
        return "Provide either a 'script' string or a 'file_path' to execute."

    try:
        # Warn about f-strings: remote Mechanical sessions run IronPython 2.7.
        if re.search(r'\bf["\']', script):
            logger.warning(
                "Detected f-string syntax in script. Remote Mechanical sessions run "
                "IronPython 2.7, which does not support f-strings. If execution fails, "
                "rewrite using .format() instead."
            )

        result = mechanical.run_python_script(script)
        return f"Script executed successfully. Result: {result}"
    except Exception as e:
        error_msg = f"Error executing script: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali", "locked_connection"})
async def launch_mechanical(
    ctx: Context,
    exec_file: str | None = None,
    port: int | None = None,
    batch: bool | None = None,
    version: str | None = None,
    transport_mode: str | None = None,
) -> str:
    """Launch a new Mechanical instance.

    This tool starts a new Mechanical instance using PyMechanical's ``launch_mechanical``
    function. The launched instance will be automatically connected and stored in
    the context for subsequent operations. Once connected, additional tools become
    available to interact with it (including ``run_python_script``, ``screenshot``,
    and ``save_project``).

    It always starts a new process; use ``connect_to_mechanical`` to attach to a
    running instance. Launching is refused when the server's environment sets
    ``PYMECHANICAL_START_INSTANCE=false``. If the request is cancelled, the launch
    continues and is recorded when it finishes; a launch that does not finish within
    the start timeout plus a grace period is stopped.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    exec_file : str, default: None
        path to the Mechanical executable. If ``None``, the executable matching
        ``version`` is used, or PyMechanical's default installation when
        ``version`` is also ``None``.
    port : int, default: None
        gRPC port for Mechanical to listen on. If ``None``, ``10000`` is used.
    batch : bool | None, default: None
        Whether to launch Mechanical in batch mode. When omitted, PyMechanical-MCP
        tries to ask the client to choose between GUI and batch mode and falls back
        to GUI mode if elicitation is unavailable.
    version : str, default: None
        Mechanical release to run, such as ``"261"``, ``"26.1"``, or ``"2026 R1"``.
        The launch fails with the list of installed releases when the requested
        release is not installed. If ``None``, PyMechanical's default installation
        (the saved path or the newest installed release) is used.
    transport_mode : str, default: None
        gRPC transport mode for the launched instance. Options are ``auto``,
        ``insecure``, ``mtls``, and ``wnua``. When ``None`` or ``auto``,
        PyMechanical applies the platform default.

    Returns
    -------
    str
        Launch status message with Mechanical version and connection information.
    """
    logger.info("Launching new Mechanical instance...")

    try:
        if _is_docker():
            target_port = int(os.environ.get("PYMECHANICAL_PORT", "10000"))
            return (
                "Launching Mechanical from inside a Docker container is not "
                "supported: the MCP server cannot start host processes.\n"
                f"Start Mechanical on the host machine with gRPC "
                f"enabled on port {target_port}, then use "
                f"'connect_to_mechanical' to establish a session."
            )

        # PyPIM launches remotely and does not read PYMECHANICAL_START_INSTANCE.
        if not (exec_file is None and _pypim_configured()):
            refusal = _start_instance_refusal()
            if refusal is not None:
                logger.error("Failed to launch Mechanical: %s", refusal)
                return f"Failed to launch Mechanical: {refusal}"

        context = ctx.request_context.lifespan_context
        # Answer before asking the user for a launch mode when nothing can start.
        if _pending_job(context) is not None or context.mechanical is not None:
            async with context.lifecycle_lock:
                busy = await _busy_message(context)
            if busy is not None:
                return busy

        # Merge: tool parameter > CLI/env config > auto
        effective_mode = transport_mode
        if effective_mode is None:
            effective_mode = context.grpc_transport_mode

        resolved_mode, resolved_certs = resolve_transport_mode(
            transport_mode=effective_mode,
            certs_dir=context.certs_dir,
        )

        resolved_exec_file, version_error = _resolve_launch_executable(version, exec_file)
        if version_error is not None:
            logger.error("Failed to launch Mechanical: %s", version_error)
            return f"Failed to launch Mechanical: {version_error}"

        requested = _normalize_mechanical_version(version) if version is not None else None

        resolved_batch = await _resolve_launch_batch_mode(ctx, batch)

        kwargs: dict[str, Any] = {
            "batch": resolved_batch,
            "loglevel": "INFO",
            "cleanup_on_exit": True,
            "start_timeout": _LAUNCH_START_TIMEOUT,
            # Never prompt on stdin: in stdio mode it is the MCP protocol stream.
            "allow_input": False,
            # Always start a new process; attaching is connect_to_mechanical's job.
            "start_instance": True,
        }

        if resolved_exec_file is not None:
            kwargs["exec_file"] = resolved_exec_file

        if port is not None:
            kwargs["port"] = port

        if requested is not None:
            kwargs["version"] = str(requested)

        if resolved_mode is not None:
            kwargs["transport_mode"] = resolved_mode

        if resolved_certs is not None:
            kwargs["certs_dir"] = resolved_certs

        async with context.lifecycle_lock:
            busy = await _busy_message(context)
            if busy is not None:
                return busy
            job = _start_session_job(
                context,
                "launch",
                lambda: _launch_worker(kwargs, requested),
                _LAUNCH_START_TIMEOUT,
                server_child_pids(),
            )

        _, info = await _await_session_job(job)

        await _set_mechanical_tools_visible(ctx, True)
        logger.info("Mechanical launched successfully!")
        executable_line = (
            f"Executable: {resolved_exec_file}\n" if resolved_exec_file is not None else ""
        )
        return (
            f"Successfully launched Mechanical\n"
            f"Version: {info['version']}\n"
            f"{executable_line}"
            f"Project Directory: {info['project_directory']}\n"
        )

    except Exception as e:
        error_msg = f"Failed to launch Mechanical: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali", "locked_connection"})
async def connect_to_mechanical(
    ctx: Context,
    port: int = 10000,
    ip: str = "127.0.0.1",
    transport_mode: str | None = None,
) -> str:
    """Connect to an existing Mechanical instance.

    This tool establishes a connection to a running Mechanical instance using the
    provided port and IP address. The connection is stored for subsequent
    operations and can be closed using the ``disconnect_from_mechanical`` tool. Once
    connected, additional tools become available to interact with it
    (including ``run_python_script``, ``screenshot``, and ``save_project``).

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    port : int, default: 10000
        gRPC port where Mechanical is listening.
    ip : str, default: "127.0.0.1"
        IP address where Mechanical is running.
    transport_mode : str, default: None
        gRPC transport mode. Options are ``"auto"``, ``"insecure"``, ``"mtls"``,
        and ``"wnua"``. When ``None`` or ``"auto"``, the mode is determined automatically.
        On Windows, it defers to PyMechanical's default ( ``"wnua"``). On Linux/Docker,
        it uses ``"mtls"`` if certificates are found. Otherwise it uses ``"insecure"``.

    Returns
    -------
    str
        Connection status message with Mechanical version information.
    """
    # When running in Docker the function parameter defaults (127.0.0.1 /
    # 10000) point at the container itself, not the host.  Prefer the
    # environment variables which are pre-configured in the Dockerfile.

    if _is_docker():
        if ip == "127.0.0.1":
            ip = os.environ.get("PYMECHANICAL_IP", ip)
        if port == 10000:
            port = int(os.environ.get("PYMECHANICAL_PORT", str(port)))

    logger.info(f"Connecting to Mechanical instance at {ip}:{port}...")

    try:
        context = ctx.request_context.lifespan_context

        # Merge: tool parameter > CLI/env config > auto
        effective_mode = transport_mode
        if effective_mode is None:
            effective_mode = context.grpc_transport_mode

        resolved_mode, resolved_certs = resolve_transport_mode(
            transport_mode=effective_mode,
            certs_dir=context.certs_dir,
        )

        logger.info(
            f"Resolved gRPC transport: mode={resolved_mode!r}, certs_dir={resolved_certs!r}"
        )

        connect_kwargs: dict[str, Any] = {
            "ip": ip,
            "port": port,
            "cleanup_on_exit": False,
        }
        if resolved_mode is not None:
            connect_kwargs["transport_mode"] = resolved_mode
        if resolved_certs is not None:
            connect_kwargs["certs_dir"] = resolved_certs

        async with context.lifecycle_lock:
            busy = await _busy_message(context)
            if busy is not None:
                return busy
            job = _start_session_job(
                context,
                "connection",
                lambda: _connect_worker(connect_kwargs),
                _CONNECT_TIMEOUT,
                None,
            )

        _, info = await _await_session_job(job)

        await _set_mechanical_tools_visible(ctx, True)
        logger.info(f"Connected to Mechanical successfully at {ip}:{port}!")
        return (
            f"Successfully connected to Mechanical at {ip}:{port}\n"
            f"Version: {info['version']}\n"
            f"Transport mode: {resolved_mode or 'default'}\n"
        )

    except Exception as e:
        error_msg = f"Failed to connect to Mechanical at {ip}:{port}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali", "locked_connection", REQUIRES_MECHANICAL_TAG})
async def disconnect_from_mechanical(ctx: Context) -> str:
    """Disconnect from the connected Mechanical instance.

    An instance started by ``launch_mechanical`` is shut down. An instance attached
    with ``connect_to_mechanical`` (or ``--connect-on-startup``) is only released and
    keeps running, so a user's own Mechanical session and its unsaved work are kept.
    A launch or connection that is still in progress is cancelled; a launch's own
    Mechanical process is stopped.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        Disconnection status message.
    """
    context = ctx.request_context.lifespan_context

    async with context.lifecycle_lock:
        job = _pending_job(context)
        if job is not None:
            await asyncio.to_thread(stop_processes, job.abandon())
            return f"Cancelled the Mechanical {job.kind} that was still in progress."

        mechanical = context.mechanical
        if mechanical is None:
            return "No Mechanical connection to disconnect."

        try:
            if context.owns_mechanical:
                logger.info("Shutting down the Mechanical instance launched by this server...")
                await asyncio.to_thread(mechanical.exit)
                message = (
                    "Successfully disconnected from Mechanical and closed the instance "
                    "launched by this server."
                )
            else:
                logger.info("Releasing the attached Mechanical instance; it is left running.")
                message = (
                    "Successfully disconnected from Mechanical. The instance was not "
                    "launched by this server, so it was left running."
                )
        except Exception as e:
            message = f"Error during disconnect: {str(e)}"
            logger.error(message)
        finally:
            context.mechanical = None
            context.owns_mechanical = False
            context.change_previews.clear()

        await _set_mechanical_tools_visible(ctx, False)
        return message


@app.tool()
def list_mechanical_instances() -> str:
    """List all Mechanical instances running on the local machine.

    This tool discovers Mechanical instances running on the machine by
    scanning for active gRPC servers and their associated metadata.

    .. note::

       When the MCP server runs inside a Docker container, host process
       scanning is not available.  In this case, the tool probes the
       configured gRPC endpoint and reports its reachability.

    Returns
    -------
    str
        Formatted table of Mechanical instances, or reachability status
        when running in Docker.
    """
    logger.info("Searching for Mechanical instances...")

    if _is_docker():
        # Can't scan host processes from Docker; probe the configured endpoint.
        ip = os.environ.get("PYMECHANICAL_IP", "host.docker.internal")
        port = int(os.environ.get("PYMECHANICAL_PORT", "10000"))
        probe = _probe_grpc_endpoint(ip, port)
        if probe["reachable"]:
            return (
                f"Running inside a Docker container: host process "
                f"scanning is not available.\n"
                f"Mechanical gRPC endpoint at {ip}:{port} is REACHABLE.\n"
                f"Use 'connect_to_mechanical' to establish a session."
            )
        return (
            f"Running inside a Docker container: host process "
            f"scanning is not available.\n"
            f"Mechanical gRPC endpoint at {ip}:{port} is "
            f"NOT REACHABLE (error: {probe['error']}).\n"
            f"Start Mechanical on the host machine with gRPC "
            f"enabled on port {port}, then retry."
        )

    return list_instances(long=True, instances=True)


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def list_files(ctx: Context) -> str:
    """List files in the Mechanical working directory.

    This tool lists all files in the working directory of the connected
    Mechanical instance.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        List of files in the working directory.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        files = mechanical.list_files()
        if not files:
            return "No files found in the working directory."

        file_list = "\n".join(f"  - {f}" for f in files)
        return f"Files in working directory:\n{file_list}"
    except Exception as e:
        error_msg = f"Error listing files: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def upload_file(ctx: Context, file_path: str) -> str:
    """Upload a file to the Mechanical instance.

    This tool uploads a local file to the Mechanical instance's working directory.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    file_path : str
        Path to the local file to upload.

    Returns
    -------
    str
        Upload status message.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if not Path(file_path).exists():
        return f"File not found: {file_path}"

    try:
        result = mechanical.upload(file_path, progress_bar=False)
        return f"Successfully uploaded file: {result}"
    except Exception as e:
        error_msg = f"Error uploading file: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def download_file(ctx: Context, file_name: str, target_dir: str | None = None) -> str:
    """Download a file from the Mechanical instance.

    This tool downloads a file from the Mechanical instance's working directory
    to the local filesystem.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    file_name : str
        Name of the file to download from the Mechanical working directory. A
        bare file name (for example ``"beam.step"``) is matched by its base
        name. Glob patterns (for example ``"*.png"``) and full paths returned
        by ``list_files`` are also accepted.
    target_dir : str, optional
        Local directory to save the downloaded file. If ``None``, the current directory is used.

    Returns
    -------
    str
        Download status message with local file path.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        # PyMechanical's download() matches `file_name` either exactly against
        # the full paths returned by list_files(), or as a glob pattern
        # containing "*". A bare base name (the common case) matches neither,
        # so resolve it to the corresponding full remote path first.
        resolved_name = file_name
        if "*" not in file_name:
            try:
                remote_files = mechanical.list_files()
            except Exception:
                remote_files = []
            if file_name not in remote_files:
                matches = [f for f in remote_files if PureWindowsPath(f).name == file_name]
                if len(matches) == 1:
                    resolved_name = matches[0]
                elif len(matches) > 1:
                    candidates = "\n".join(f"  - {m}" for m in matches)
                    return (
                        f"Multiple files named '{file_name}' exist in the working "
                        f"directory. Specify the full path:\n{candidates}"
                    )

        local_paths = mechanical.download(
            resolved_name,
            target_dir=target_dir,
            progress_bar=False,
        )
        if local_paths:
            return f"Successfully downloaded file(s): {', '.join(local_paths)}"
        else:
            return f"No files matching '{file_name}' found to download."
    except Exception as e:
        error_msg = f"Error downloading file: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def download_project(
    ctx: Context,
    extensions: list[str] | None = None,
    target_dir: str | None = None,
) -> str:
    """Download the connected Mechanical project's files as one operation.

    Parameters
    ----------
    ctx : Context
        MCP context containing the connected Mechanical instance.
    extensions : list[str] | None, optional
        Optional file extensions to include, such as ``["mechdb", "png"]``.
        When omitted, downloads all project files supported by PyMechanical.
    target_dir : str | None, optional
        Local directory to receive the downloaded files. Uses the current
        directory when omitted.

    Returns
    -------
    str
        JSON result containing the downloaded local paths or a structured error.
    """
    mechanical, error = _mechanical_or_error(ctx)
    if error is not None:
        return error
    mechanical = cast(Any, mechanical)

    if extensions is not None and any(not extension.strip() for extension in extensions):
        return _structured_error(
            InvalidArgumentsError("extensions must contain non-empty file-extension strings.")
        )

    # Unlike Mechanical.download(), Mechanical.download_project() calls
    # target_dir.rstrip(...) unconditionally and raises AttributeError when
    # target_dir is None. Default to the current working directory to match
    # the documented "uses the current directory when omitted" behavior.
    resolved_target_dir = target_dir if target_dir is not None else str(Path.cwd())

    try:
        paths = mechanical.download_project(
            extensions=extensions or [], target_dir=resolved_target_dir, progress_bar=False
        )
        return json.dumps(
            {
                "success": True,
                "downloaded_files": [str(path) for path in paths],
                "file_count": len(paths),
            },
            indent=2,
        )
    except Exception as exc:
        return _structured_error(UpstreamError(f"Error downloading project: {exc}"))


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def clear_mechanical(ctx: Context) -> str:
    """Clear the Mechanical database.

    This tool clears the current database in the Mechanical instance,
    providing a fresh start for a new analysis. All unsaved model data is lost.
    The Mechanical process and the connection stay open; use
    ``disconnect_from_mechanical`` to end the session.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        Clear status message.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        mechanical.clear()
        return "Mechanical database cleared successfully."
    except Exception as e:
        error_msg = f"Error clearing database: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.resource("files://mechanical/working_directory")
def mechanical_working_directory() -> str:
    """Return the working directory of the connected Mechanical instance.

    This resource provides the absolute path to the active project directory
    used by the connected Mechanical instance. The value is resolved lazily
    each time the resource is read.

    Returns
    -------
    str
        Absolute path to the Mechanical project directory, or a message
        indicating that Mechanical is not connected.
    """
    mechanical = getattr(getattr(app, "context", None), "mechanical", None)

    if mechanical is None:
        return "Mechanical is not connected. Use connect_to_mechanical or launch_mechanical."

    try:
        return str(mechanical.project_directory)
    except Exception as e:
        return f"Could not retrieve project directory: {e}"


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def get_model_info(ctx: Context) -> str:
    """Get information about the current model in Mechanical.

    This tool retrieves information about the current model including
    geometry, mesh, and analysis settings by executing a script inside
    Mechanical.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        JSON string containing model information. Includes ``project``,
        ``model``, ``geometry``, ``mesh`` (counts plus the active mesh metric),
        ``analyses_count``, ``named_selections``, ``materials``, ``unit_system``,
        ``analyses``, and ``boundary_conditions``.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        # Script to gather model information
        script = (
            _SCRIPT_HELPERS
            + """
model_info = {}

# Get Project info
project = ExtAPI.DataModel.Project
model_info['project'] = {
    'product_version': project.ProductVersion,
    'name': project.Name if hasattr(project, 'Name') else 'N/A',
}

# Get Model info
model = Model
model_info['model'] = {
    'name': model.Name if hasattr(model, 'Name') else 'N/A',
}

# Get Geometry info
if hasattr(model, 'Geometry') and model.Geometry is not None:
    geom = model.Geometry
    try:
        body_count = geom.GetChildren(DataModelObjectCategory.Body, True).Count
    except:
        body_count = 0
    model_info['geometry'] = {
        'body_count': body_count,
    }
else:
    model_info['geometry'] = {'body_count': 0}

# Get Mesh info
if hasattr(model, 'Mesh') and model.Mesh is not None:
    mesh = model.Mesh
    nodes = mesh.Nodes
    elements = mesh.Elements
    node_count = nodes.Count if hasattr(nodes, 'Count') else (
        nodes if isinstance(nodes, int) else 0
    )
    element_count = elements.Count if hasattr(elements, 'Count') else (
        elements if isinstance(elements, int) else 0
    )
    model_info['mesh'] = {
        'node_count': node_count,
        'element_count': element_count,
    }
else:
    model_info['mesh'] = {'node_count': 0, 'element_count': 0}

# Get Analysis count
if hasattr(model, 'Analyses') and model.Analyses is not None:
    model_info['analyses_count'] = model.Analyses.Count
else:
    model_info['analyses_count'] = 0

# Active mesh metric. Read-only: the metric is not changed, so a model that has
# no metric selected reports None rather than being mutated by an info call.
try:
    metric_name = str(mesh.MeshMetric)
    if metric_name and metric_name.lower() != 'none':
        model_info['mesh']['metric'] = {
            'name': metric_name,
            'minimum': _quantity(mesh.Minimum),
            'maximum': _quantity(mesh.Maximum),
            'average': _quantity(mesh.Average),
            'standard_deviation': _quantity(mesh.StandardDeviation),
        }
    else:
        model_info['mesh']['metric'] = None
except:
    model_info['mesh']['metric'] = None

# Named selections are the recommended scoping target, so expose their names.
try:
    model_info['named_selections'] = [
        child.Name for child in Model.NamedSelections.Children
    ]
except:
    model_info['named_selections'] = []

try:
    model_info['materials'] = [child.Name for child in Model.Materials.Children]
except:
    model_info['materials'] = []

try:
    model_info['unit_system'] = str(ExtAPI.Application.ActiveUnitSystem)
except:
    model_info['unit_system'] = None

# Per-analysis detail, including everything scoped under each analysis that is
# not an analysis-settings or solution folder (loads, supports, conditions).
analyses = []
boundary_conditions = []
try:
    for analysis_idx in range(Model.Analyses.Count):
        analysis = Model.Analyses[analysis_idx]
        try:
            solution_status = str(analysis.Solution.Status)
        except:
            solution_status = 'Unknown'
        analyses.append({
            'index': analysis_idx,
            'name': analysis.Name,
            'type': str(analysis.AnalysisType),
            'solution_status': solution_status,
        })
        for child_idx in range(analysis.Children.Count):
            child = analysis.Children[child_idx]
            category = _category(child)
            # Analysis settings report a solver-specific category, such as
            # ANSYSAnalysisSettings, so match the suffix.
            if category == 'Solution' or category.endswith('AnalysisSettings'):
                continue
            boundary_conditions.append({
                'analysis_index': analysis_idx,
                'name': child.Name,
                'type': category,
            })
except:
    pass

model_info['analyses'] = analyses
model_info['boundary_conditions'] = boundary_conditions

json.dumps(model_info, ensure_ascii=False)
"""
        )
        result = mechanical.run_python_script(script)
        return str(result) if result else json.dumps({"error": "Could not retrieve model info"})
    except Exception as e:
        error_msg = f"Error getting model info: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def screenshot(
    ctx: Context,
    view_type: str = "model",
) -> list[TextContent | ImageContent]:
    """Capture a screenshot of the current Mechanical view.

    This tool captures the current graphics view from Mechanical as an image.
    It can capture model views, mesh views, or result contour plots.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    view_type : str, default: ``"model"``
        View to activate before capturing. Options are ``"model"`` (geometry),
        ``"mesh"``, and ``"result"`` (the first evaluated result object). If the
        requested view cannot be activated, the current view is captured instead.

    Returns
    -------
    list[TextContent | ImageContent]
        A list containing:

        - TextContent with the screenshot file path
        - ImageContent with the base64-encoded image data
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return [
            TextContent(
                type="text",
                text=(
                    "No Mechanical connection available. "
                    "Use connect_to_mechanical tool to establish a connection."
                ),
            )
        ]

    if view_type not in _SCREENSHOT_VIEW_TYPES:
        return [
            TextContent(
                type="text",
                text=(
                    f"Invalid view_type '{view_type}'. "
                    f"Choose one of: {', '.join(_SCREENSHOT_VIEW_TYPES)}."
                ),
            )
        ]

    # The image is written next to the project on the Mechanical host and transferred over
    # gRPC, so capture works whether Mechanical runs locally, remotely, or in a container.
    remote_name = f"mcp_screenshot_{uuid.uuid4().hex}.png"
    remote_path: str | None = None
    local_dir: str | None = None

    try:
        logger.info(f"Capturing Mechanical screenshot (type: {view_type})...")

        # Script to capture screenshot using Mechanical's Graphics API
        script = f"""
import json
import os

requested_view = {json.dumps(view_type)}
activated = "current"

# Activate the requested view so the export reflects view_type.
try:
    if requested_view == "mesh":
        Model.Mesh.Activate()
        activated = "mesh"
    elif requested_view == "result":
        for _ai in range(Model.Analyses.Count):
            _solution = Model.Analyses[_ai].Solution
            for _ci in range(_solution.Children.Count):
                _child = _solution.Children[_ci]
                if hasattr(_child, 'Maximum'):
                    _child.Activate()
                    activated = "result"
                    break
            if activated == "result":
                break
    else:
        Model.Geometry.Activate()
        activated = "model"
except:
    activated = "current"

image_path = os.path.join(ExtAPI.DataModel.Project.ProjectDirectory, {json.dumps(remote_name)})

# Get the Graphics object
graphics = ExtAPI.Graphics

# Try different export approaches for version compatibility
try:
    # Approach 1: Use GraphicsImageExportFormat enum when available.
    settings = Ansys.Mechanical.Graphics.GraphicsImageExportSettings()
    settings.Resolution = GraphicsResolutionType.EnhancedResolution
    settings.Width = 1920
    settings.Height = 1080
    graphics.ExportImage(image_path, GraphicsImageExportFormat.PNG, settings)
except:
    # Approach 2: Simpler export (older versions)
    graphics.ExportImage(image_path)

json.dumps({{"path": image_path, "activated": activated}}, ensure_ascii=False)
"""
        try:
            result = mechanical.run_python_script(script)
            logger.info(f"Screenshot script result: {result}")
        except Exception as e:
            logger.warning(f"Graphics export failed: {e}")
            return [TextContent(type="text", text=f"Screenshot capture failed: {str(e)}")]

        try:
            script_result = json.loads(str(result))
            remote_path = str(script_result["path"])
        except (ValueError, TypeError, KeyError):
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Screenshot capture failed: unexpected response from Mechanical: {result}"
                    ),
                )
            ]

        # The script reports the view it managed to activate, which can differ from
        # view_type when the requested object is unavailable (for example, no results yet).
        activated_view = str(script_result.get("activated", view_type))

        local_dir = tempfile.mkdtemp(prefix="mechanical_screenshot_")
        local_paths = mechanical.download(remote_path, target_dir=local_dir, progress_bar=False)
        if not local_paths:
            return [
                TextContent(
                    type="text",
                    text=f"Screenshot capture failed: Mechanical did not create {remote_path}.",
                )
            ]

        image_data = Path(local_paths[0]).read_bytes()
        if not image_data.startswith(_PNG_SIGNATURE):
            return [
                TextContent(
                    type="text",
                    text="Screenshot capture failed: Mechanical did not produce a PNG image.",
                )
            ]

        base64_data = base64.b64encode(image_data).decode("utf-8")
        logger.info(f"Screenshot captured successfully ({len(image_data)} bytes).")

        return [
            TextContent(
                type="text", text=f"Screenshot captured successfully (view: {activated_view})."
            ),
            ImageContent(type="image", data=base64_data, mimeType="image/png"),
        ]

    except Exception as e:
        error_msg = f"Failed to capture screenshot: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]

    finally:
        if local_dir is not None:
            shutil.rmtree(local_dir, ignore_errors=True)
        if remote_path is not None:
            _delete_remote_file(mechanical, remote_path)


def _delete_remote_file(mechanical: Any, remote_path: str) -> None:
    """Delete a temporary file on the Mechanical host, ignoring failures."""
    path_literal = json.dumps(remote_path)
    script = f"import os\nif os.path.isfile({path_literal}):\n    os.remove({path_literal})\n"
    try:
        mechanical.run_python_script(script)
    except Exception as exc:
        logger.info("Could not delete %s on the Mechanical host: %s", remote_path, exc)


####################################################################################################
# Tools that use the PersistentPythonSession


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
async def run_python_code(
    ctx: Context,
    code: str,
    timeout: int = 60,
) -> str:
    """Execute Python code in the persistent Python session for data processing.

    **IMPORTANT:** This tool runs in a separate Python process and does NOT have access
    to the Mechanical gRPC connection. Use this tool for:

    - Custom data processing and analysis (NumPy, Pandas, and SciPy)
    - Creating Matplotlib plots and visualizations
    - Postprocessing results exported from Mechanical
    - General Python computations

    For code that needs to run inside Mechanical (such as IronPython with ``ExtAPI`` or ``Model``),
    use the 'run_python_script' tool instead.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    code : str
        Python code to execute. You should use standard Python libraries.
        This tool does NOT have access to Mechanical's ``ExtAPI``, ``Model``,
        or other internal objects.
    timeout : int, default: 60
        Maximum time in seconds to allow for code execution.

    Returns
    -------
    str
        Execution result or error message. Returns JSON for structured output.
    """
    return await execute_python_code(ctx=ctx, code=code, timeout=timeout)  # type: ignore[no-any-return]


@app.tool(tags={"aali", REQUIRES_MECHANICAL_TAG})
def create_custom_plot(
    ctx: Context,
    plot_code: str,
    plot_type: str = "matplotlib",
    timeout: int = 60,
) -> list[TextContent | ImageContent] | str:
    """Create a custom plot using Matplotlib in the persistent Python session.

    IMPORTANT: This tool runs in a separate Python process and does not have access
    to the Mechanical gRPC connection. Use this to:

    - Visualize data that was exported/saved from Mechanical.
    - Create plots from result files (such as CSV and TXT).
    - Perform postprocessing visualizations.

    For plots that need data directly from Mechanical, first use ``run_python_script``
    to export the data to a file. Then use this tool to create the visualization.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    plot_code : str
        Python code to create the plot. You should use ``matplotlib.pyplot``.
        For Matplotlib, the code should create the figure or plot but not call ``plt.show()``.
        Use the ``save_matplotlib_plot()`` helper function to return the plot.
    plot_type : str, default:``"matplotlib"``
        Type of plot. Options are ``"matplotlib"`` and ``"pyvista"``.
    timeout : int, default: 60
        Maximum time in seconds for plot generation.

    Returns
    -------
    list[TextContent | ImageContent]
        A list containing:

        - TextContent with the plot creation status message
        - ImageContent with the base64-encoded image data if successful

        Or, a JSON string with error details if failed.
    """
    session = ctx.request_context.lifespan_context.python_session

    if session is None:
        return [
            TextContent(
                type="text",
                text=(
                    "No Python session available. "
                    "The persistent Python session was not initialized."
                ),
            )
        ]

    try:
        logger.info(f"Creating custom {plot_type} plot in persistent session")

        # Sanitize the plot code
        sanitized_plot_code = _sanitize_output(plot_code)

        # Execute the plot code
        execution_kwargs: dict[str, Any] = {"timeout": timeout}
        if "no_output_timeout" in inspect.signature(session.execute).parameters:
            execution_kwargs["no_output_timeout"] = None
        result = session.execute(sanitized_plot_code, **execution_kwargs)

        # Parse the result
        if isinstance(result, dict):
            stdout = _sanitize_output(result.get("stdout", ""))
            stderr = _sanitize_output(result.get("stderr", ""))

            if result.get("success"):
                # Try to extract plot data from stdout
                plot_data = stdout.strip()

                # Check if the output contains a base64 data URI
                if "data:image/png;base64," in plot_data:
                    # Extract the base64 part
                    base64_data = plot_data.split("data:image/png;base64,")[1].strip()

                    return [
                        TextContent(
                            type="text",
                            text=f"Custom {plot_type} plot created successfully",
                        ),
                        ImageContent(type="image", data=base64_data, mimeType="image/png"),
                    ]
                elif plot_data.startswith("Plot saved to"):
                    return [
                        TextContent(
                            type="text",
                            text=f"Custom {plot_type} plot created successfully\n{plot_data}",
                        )
                    ]
                else:
                    return [
                        TextContent(
                            type="text",
                            text=f"Plot created but unexpected output format:\n{stdout}",
                        )
                    ]
            else:
                error_msg = result.get("error", "Unknown error occurred")
                error_msg = _sanitize_output(error_msg)
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"Error creating custom {plot_type} plot: "
                            f"{error_msg}\nStdout: {stdout}\n"
                            f"Stderr: {stderr}"
                        ),
                    )
                ]
        else:
            sanitized = _sanitize_output(str(result)) if result else "No result"
            return [
                TextContent(
                    type="text",
                    text=f"Unexpected result format: {sanitized}",
                )
            ]

    except TimeoutError:
        error_msg = f"Plot creation timed out after {timeout} seconds"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]

    except Exception as e:
        error_msg = f"Error creating custom plot: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


####################################################################################################
# Project Management Tools


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def save_project(ctx: Context, file_path: str | None = None) -> str:
    """Save the current Mechanical project.

    This tool saves the current project to disk. If ``file_path`` is provided,
    the project is saved to that location (Save As), overwriting an existing
    file at that path. Otherwise, the project is saved in place.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    file_path : str, default: None
        Full path for saving the project (Save As). The path should end with
        a ``.mechdb`` extension. The path is resolved on the connected
        Mechanical instance, which may be a different machine than the MCP
        server. If ``None``, the project is saved in the current location.

    Returns
    -------
    str
        Save status message with the project file path.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        if file_path is not None:
            # Validate extension
            if not file_path.lower().endswith(".mechdb"):
                file_path = file_path + ".mechdb"

            # Save As: use scripting API. json.dumps() safely escapes the
            # path into a Python string literal so embedded quotes,
            # backslashes, or other special characters cannot break out of
            # the script. ``overwrite=True`` lets repeated saves to the same
            # path succeed, matching the expected idempotent "save" behavior
            # (Project.SaveAs otherwise raises if the file already exists).
            script = f"ExtAPI.DataModel.Project.SaveAs({json.dumps(file_path)}, True)"
            mechanical.run_python_script(script)
            return f"Project saved to: {file_path}"
        else:
            # Save in place
            script = "ExtAPI.DataModel.Project.Save()"
            mechanical.run_python_script(script)
            # Get the saved path
            proj_dir = mechanical.project_directory
            return f"Project saved successfully. Project directory: {proj_dir}"

    except Exception as e:
        # Project.Save() raises this specific error when the project has
        # never been saved before, since it has no destination path to infer.
        # Surface a clear, actionable message instead of the raw gRPC/IronPython
        # traceback.
        if file_path is None and "never saved before" in str(e):
            return (
                "Project has not been saved yet, so it has no location to save "
                "in place. Call save_project with a file_path to save it for "
                "the first time (Save As)."
            )
        error_msg = f"Error saving project: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def open_project(ctx: Context, file_path: str) -> str:
    """Open an existing Mechanical project file.

    This tool opens a MECHDB project file in the connected Mechanical instance.
    Any unsaved work in the current project is lost.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    file_path : str
        Full path to the MECHDB file. The path is resolved on the connected
        Mechanical instance, which may be a different machine than the MCP
        server, so it is not required to exist on the local filesystem.

    Returns
    -------
    str
        Open status message with project information.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection is available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if not file_path.lower().endswith(".mechdb"):
        return f"Invalid file type. Expected MECHDB file. Got: {file_path}"

    try:
        # json.dumps() safely escapes the path into a Python string literal so
        # embedded quotes, backslashes, or other characters cannot break out
        # of the script body.
        script = f"ExtAPI.DataModel.Project.Open({json.dumps(file_path)})"
        mechanical.run_python_script(script)

        # Get project info after opening
        info_script = """
import json
project = ExtAPI.DataModel.Project
info = {
    "name": project.Name if hasattr(project, 'Name') else 'N/A',
    "product_version": project.ProductVersion,
}
# Count bodies and analyses
model = Model
info["body_count"] = model.Geometry.GetChildren(
    DataModelObjectCategory.Body, True
).Count if hasattr(model, 'Geometry') and model.Geometry else 0
info["analyses_count"] = model.Analyses.Count if hasattr(model, 'Analyses') else 0
json.dumps(info, ensure_ascii=False)
"""
        result = mechanical.run_python_script(info_script)
        return f"Project opened successfully: {file_path}\nProject info: {result}"

    except Exception as e:
        # The path is resolved on the (possibly remote) Mechanical instance, not
        # on the MCP server, so only use the local filesystem to enrich a
        # failure that has already occurred, never to pre-emptively block a
        # path that may legitimately exist only on a remote Mechanical server.
        hint = ""
        if not Path(file_path).exists():
            hint = (
                " The path does not exist on the local MCP server filesystem; "
                "if Mechanical is running on a different machine, verify the "
                "path exists there instead."
            )
        error_msg = f"Error opening project: {str(e)}.{hint}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def solve_analysis(
    ctx: Context,
    analysis_index: int = 0,
    wait: bool = True,
) -> str:
    """Solve the specified analysis in Mechanical.

    This tool runs the solver for the specified analysis and returns the
    solution status. It checks for common issues and provides diagnostic
    information if the solve fails.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    analysis_index : int, default: 0
        Index of the analysis to solve (0-based). The default, ``0``,
        corresponds to the first analysis.
    wait : bool, default: True
        Whether to block until the solve finishes. When ``False``, the solve is
        started and the tool returns immediately. The reported ``status`` then
        reflects the solver state at that moment rather than the final outcome.

    Returns
    -------
    str
        JSON string with solution status, timing, and result summary.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection is available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        script = f"""
import json
import time

# Validate analysis index
if Model.Analyses.Count == 0:
    result = json.dumps(
        {{"success": False, "error": "No analyses are defined in the model."}}, ensure_ascii=False
    )
elif {analysis_index} >= Model.Analyses.Count:
    result = json.dumps({{
        "success": False,
        "error": (
            "Analysis index {analysis_index} is out of range. "
            "Model has {{0}} analyses."
        ).format(Model.Analyses.Count)
    }}, ensure_ascii=False)
else:
    analysis = Model.Analyses[{analysis_index}]

    # Pre-solve checks
    warnings = []
    mesh = Model.Mesh
    if mesh is None or mesh.Elements == 0:
        warnings.append("No mesh is generated. Mesh must be generated before solving.")

    # Solve, honoring the caller's wait preference
    start_time = time.time()
    analysis.Solve({wait})
    elapsed = time.time() - start_time

    # Get solution status
    solution = analysis.Solution
    status = str(solution.Status)

    # Build result
    solve_result = {{
        "success": (status == "Done") if {wait} else True,
        "waited": {wait},
        "status": status,
        "analysis_name": analysis.Name,
        "analysis_type": str(analysis.AnalysisType),
        "elapsed_seconds": round(elapsed, 2),
        "warnings": warnings,
    }}

    # If solved successfully, get result summary
    if status == "Done":
        result_count = 0
        for i in range(solution.Children.Count):
            child = solution.Children[i]
            if hasattr(child, 'Maximum'):
                result_count += 1
        solve_result["result_objects_count"] = result_count

    result = json.dumps(solve_result, ensure_ascii=False)

result
"""
        result = mechanical.run_python_script(script)
        return (
            str(result)
            if result
            else json.dumps({"success": False, "error": "No response from solver"})
        )

    except Exception as e:
        error_msg = f"Error during solve: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"success": False, "error": error_msg})


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def export_results(
    ctx: Context,
    analysis_index: int = 0,
    result_type: str = "all",
    export_format: str = "png",
    output_dir: str | None = None,
) -> str:
    """Export results from the solved analysis.

    This tool exports result images (contour plots) and/or data from the
    current solution. It can export individual result types or all available
    results at once.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    analysis_index : int, default: 0
        Index of the analysis to export results from (0-based). Use the same
        index that was passed to ``solve_analysis``.
    result_type : str, default: ``"all"``
        Type of result to export. Options are ``"all"``, ``"deformation"``, ``"stress"``,
         ``"strain"``, or a specific result object name.
    export_format : str, default: ``"png"``
        Export format. Use ``"png"`` for images, ``"txt"`` for text data, or ``"both"`` for
        images and text.
    output_dir : str, default: None
        Directory on the Mechanical host to save exported files. It is created if
        it does not exist. If ``None``, uses the project directory. Use
        ``download_file`` or ``download_project`` to copy the files locally.

    Returns
    -------
    str
        JSON string with export status and file paths.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if analysis_index < 0:
        return json.dumps({"success": False, "error": "analysis_index must be zero or greater."})

    try:
        # Determine output directory
        if output_dir is None:
            output_dir = str(mechanical.project_directory)

        script = f"""
import json
import os

output_dir = {json.dumps(output_dir)}
result_type = {json.dumps(result_type)}
export_format = {json.dumps(export_format)}
analysis_index = {analysis_index}

_invalid_name_chars = '<>:"/|?*' + chr(92)


def _safe_file_name(name):
    cleaned = []
    for ch in name:
        if ch in _invalid_name_chars or ch.isspace() or ord(ch) < 32:
            cleaned.append('_')
        else:
            cleaned.append(ch)
    return ''.join(cleaned).rstrip('.') or 'result'

# Resolve the requested analysis before exporting so the results match the
# analysis the caller solved.
index_error = None
if Model.Analyses.Count == 0:
    solution = None
elif analysis_index >= Model.Analyses.Count:
    solution = None
    index_error = (
        "Analysis index {{0}} is out of range. Model has {{1}} analyses."
    ).format(analysis_index, Model.Analyses.Count)
else:
    solution = Model.Analyses[analysis_index].Solution

if index_error is not None:
    result = json.dumps({{"success": False, "error": index_error}}, ensure_ascii=False)
elif solution is None:
    result = json.dumps(
        {{"success": False, "error": "No analysis found in the model"}}, ensure_ascii=False
    )
elif str(solution.Status) != "Done":
    result = json.dumps({{
        "success": False,
        "error": "Solution has not been completed. Status: {{0}}".format(solution.Status)
    }}, ensure_ascii=False)
else:
    exported_files = []
    errors = []
    used_names = set()

    # The directory must exist on the Mechanical host, which may not be this machine.
    try:
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)
    except Exception as e:
        errors.append("Could not create output directory {{0}}: {{1}}".format(output_dir, str(e)))

    # Evaluate all results first
    try:
        solution.EvaluateAllResults()
    except Exception as e:
        errors.append("Result evaluation failed: {{0}}".format(str(e)))

    # Iterate through result objects
    for i in range(solution.Children.Count):
        if not os.path.isdir(output_dir):
            break
        child = solution.Children[i]

        # Check if this is a result object (has Maximum property)
        if not hasattr(child, 'Maximum'):
            continue

        # Filter by result_type
        child_name = child.Name
        if result_type != "all":
            if result_type.lower() == "deformation" and "Deformation" not in child_name:
                continue
            elif result_type.lower() == "stress" and "Stress" not in child_name:
                continue
            elif result_type.lower() == "strain" and "Strain" not in child_name:
                continue
            elif result_type.lower() not in ["all", "deformation", "stress", "strain"]:
                if result_type.lower() not in child_name.lower():
                    continue

        # Activate the result for export
        child.Activate()

        base_name = _safe_file_name(child_name)
        safe_name = base_name
        name_count = 1
        while safe_name.lower() in used_names:
            name_count += 1
            safe_name = base_name + "_" + str(name_count)
        used_names.add(safe_name.lower())

        # Export image
        if export_format in ("png", "both"):
            try:
                img_path = os.path.join(output_dir, safe_name + ".png")
                Graphics.ExportImage(img_path, GraphicsImageExportFormat.PNG)
                exported_files.append(img_path)
            except Exception as e:
                errors.append("Image export failed for {{0}}: {{1}}".format(child_name, str(e)))

        # Export text data
        if export_format in ("txt", "both"):
            try:
                txt_path = os.path.join(output_dir, safe_name + ".txt")
                child.ExportToTextFile(txt_path)
                exported_files.append(txt_path)
            except Exception as e:
                errors.append("Text export failed for {{0}}: {{1}}".format(child_name, str(e)))

    result = json.dumps({{
        "success": len(exported_files) > 0,
        "exported_files": exported_files,
        "file_count": len(exported_files),
        "errors": errors,
        "output_directory": output_dir,
    }}, ensure_ascii=False)

result
"""
        result = mechanical.run_python_script(script)
        return str(result) if result else json.dumps({"success": False, "error": "No response"})

    except Exception as e:
        error_msg = f"Error exporting results: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"success": False, "error": error_msg})


# Body of get_results_summary. The caller prepends ``analysis_filter``, set to
# either None (all analyses) or a zero-based analysis index.
_RESULTS_SUMMARY_SCRIPT = """
if Model.Analyses.Count == 0:
    summary = {'success': False, 'error': 'No analyses are defined in the model.'}
elif analysis_filter is not None and analysis_filter >= Model.Analyses.Count:
    summary = {
        'success': False,
        'error': 'Analysis index {0} is out of range. Model has {1} analyses.'.format(
            analysis_filter, Model.Analyses.Count
        ),
    }
else:
    entries = []
    for analysis_idx in range(Model.Analyses.Count):
        if analysis_filter is not None and analysis_idx != analysis_filter:
            continue

        analysis = Model.Analyses[analysis_idx]
        solution = analysis.Solution
        try:
            status = str(solution.Status)
        except:
            status = 'Unknown'

        entry = {
            'analysis_index': analysis_idx,
            'analysis_name': analysis.Name,
            'analysis_type': str(analysis.AnalysisType),
            'solution_status': status,
            'results': [],
        }

        # Results can only be evaluated once the solver has produced them.
        if status in ('Done', 'PostProcessingRequired'):
            try:
                solution.EvaluateAllResults()
            except Exception as e:
                entry['evaluation_error'] = str(e)
            try:
                status = str(solution.Status)
                entry['solution_status'] = status
            except:
                pass

        for child_idx in range(solution.Children.Count):
            child = solution.Children[child_idx]
            # Result objects are the ones exposing extrema.
            if not hasattr(child, 'Maximum'):
                continue
            item = {'name': child.Name, 'type': _category(child)}
            try:
                state = str(child.ObjectState)
            except:
                state = None
            item['state'] = state
            # Values of an unsolved, obsolete, or failed result are stale or absent.
            if state is not None:
                has_values = state == 'Solved'
            else:
                has_values = status == 'Done'
            for key, attr in (
                ('minimum', 'Minimum'),
                ('maximum', 'Maximum'),
                ('average', 'Average'),
            ):
                if not has_values:
                    item[key] = None
                    continue
                try:
                    item[key] = _quantity(getattr(child, attr))
                except:
                    item[key] = None
            entry['results'].append(item)

        entry['result_count'] = len(entry['results'])
        entries.append(entry)

    summary = {'success': True, 'analysis_count': len(entries), 'analyses': entries}

json.dumps(summary, ensure_ascii=False)
"""


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def get_results_summary(
    ctx: Context,
    analysis_index: int | None = None,
) -> str:
    """Return solved result values as structured data.

    Use this after ``solve_analysis`` to read result extrema directly, instead of
    exporting files and reading them back. Every evaluated result object is
    reported generically, so custom and user-defined results are included without
    needing a dedicated tool per result type.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    analysis_index : int, optional
        Restrict the summary to a single analysis (0-based). When ``None``, every
        analysis in the model is reported.

    Returns
    -------
    str
        JSON string with one entry per analysis, each listing its result objects
        with their ``state`` and their minimum, maximum, and average values and
        units. Values are ``null`` unless the result is solved, so stale values
        of an obsolete or failed result are never reported.
    """
    mechanical, error = _mechanical_or_error(ctx)
    if error is not None:
        return error
    mechanical = cast(Any, mechanical)

    if analysis_index is not None and analysis_index < 0:
        return _structured_error(InvalidArgumentsError("analysis_index must be zero or greater."))

    # Coerced to an int literal, so the value cannot inject script content.
    selector = "None" if analysis_index is None else str(int(analysis_index))

    try:
        script = f"{_SCRIPT_HELPERS}\nanalysis_filter = {selector}\n{_RESULTS_SUMMARY_SCRIPT}"
        result = mechanical.run_python_script(script)
        if not result:
            return _structured_error(UpstreamError("No response from Mechanical."))
        return str(result)
    except Exception as exc:
        return _structured_error(UpstreamError(f"Error reading results: {exc}"))


####################################################################################################
# Object discovery, property change previews, and script checks

_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


def _run_introspection(mechanical: Any, script: str, action: str) -> dict[str, Any]:
    """Run an introspection script and return its JSON payload.

    Raises
    ------
    UpstreamError
        If Mechanical fails or does not return a JSON object.
    """
    try:
        raw = mechanical.run_python_script(script)
    except Exception as exc:
        raise UpstreamError(f"Error {action}: {exc}") from exc
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError) as exc:
        raise UpstreamError(f"Unexpected response from Mechanical while {action}.") from exc
    if not isinstance(payload, dict):
        raise UpstreamError(f"Unexpected response from Mechanical while {action}.")
    return payload


def _with_suggestions(payload: dict[str, Any], word: str) -> dict[str, Any]:
    """Replace a long ``candidates`` list in an error with the closest matches."""
    details = payload.get("details") or {}
    candidates = details.pop("candidates", None)
    if candidates:
        details["suggestions"] = introspection.close_matches(word, candidates)
    payload["details"] = details
    return payload


@app.tool(tags={REQUIRES_MECHANICAL_TAG}, annotations=_READ_ONLY)
def find_objects(
    ctx: Context,
    name_contains: str | None = None,
    category: str | None = None,
    parent_id: int | None = None,
    max_depth: int | None = None,
    limit: int = 100,
) -> str:
    """Find objects in the Mechanical Outline tree and return their stable IDs.

    Use the returned ``object_id`` values with ``describe_object`` and
    ``preview_property_change``. IDs stay the same for the life of the object,
    unlike names, which can repeat, and positions, which change when objects are
    added. Nothing in the model is changed.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    name_contains : str, optional
        Case-insensitive text that the object name must contain.
    category : str, optional
        ``DataModelObjectCategory`` name, such as ``Force``, ``FixedSupport``,
        ``Body``, or ``EquivalentStress``. Case-insensitive.
    parent_id : int, optional
        Search below this object only. By default the whole project is searched.
    max_depth : int, optional
        Number of levels below the start object to search. By default all levels
        are searched.
    limit : int, default: 100
        Maximum number of objects to return, from 1 to 1000. ``match_count``
        always reports the full number of matches.

    Returns
    -------
    str
        JSON with ``objects`` (``object_id``, ``name``, ``category``, ``state``,
        ``path``, ``depth``, and ``child_count``), ``match_count``,
        ``truncated``, ``category_counts`` for every object searched, and the
        connected ``product_version`` and ``python_engine``.
    """
    mechanical, error = _mechanical_or_error(ctx)
    if error is not None:
        return error
    if not 1 <= limit <= 1000:
        return _structured_error(InvalidArgumentsError("limit must be between 1 and 1000."))
    if max_depth is not None and max_depth < 0:
        return _structured_error(InvalidArgumentsError("max_depth must be zero or greater."))

    args = {
        "name_contains": name_contains,
        "category": category,
        "parent_id": parent_id,
        "max_depth": max_depth,
        "limit": limit,
    }
    try:
        payload = _run_introspection(
            mechanical, introspection.find_objects_script(args), "finding objects"
        )
    except UpstreamError as exc:
        return _structured_error(exc)
    if not payload.get("success", False) and category:
        payload = _with_suggestions(payload, category)
    return json.dumps(payload, ensure_ascii=False)


@app.tool(tags={REQUIRES_MECHANICAL_TAG}, annotations=_READ_ONLY)
def describe_object(
    ctx: Context,
    object_id: int,
    details_only: bool = True,
    name_contains: str | None = None,
    include_methods: bool = False,
) -> str:
    """Describe the API properties of one object in the connected Mechanical release.

    The description is read from the connected session, so it matches the
    installed release, including releases newer than the bundled API reference.
    Values are reported with units, and enum properties list their allowed
    members. Nothing in the model is changed.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    object_id : int
        ID of the object, as returned by ``find_objects``.
    details_only : bool, default: True
        Return only properties shown in the object's Details view, which are the
        settings a user normally edits. Set to ``False`` to return every public
        API property.
    name_contains : str, optional
        Case-insensitive text that the property name or Details caption must
        contain.
    include_methods : bool, default: False
        Also return the public method signatures of the object.

    Returns
    -------
    str
        JSON with ``object`` (ID, name, category, state, parent ID, API type),
        ``unit_system``, and ``properties``. Each property reports ``name``,
        ``type``, ``kind``, ``writable``, ``editable``, and, where available,
        ``value``, ``caption``, ``display``, ``read_only_in_details``,
        ``enum_values``, and ``range``. ``editable`` means that
        ``preview_property_change`` supports the property. Details rows without
        an API property are listed in ``details_without_api``.
    """
    mechanical, error = _mechanical_or_error(ctx)
    if error is not None:
        return error

    args = {
        "object_id": object_id,
        "details_only": details_only,
        "name_contains": name_contains,
        "include_methods": include_methods,
    }
    try:
        payload = _run_introspection(
            mechanical, introspection.describe_object_script(args), "describing the object"
        )
    except UpstreamError as exc:
        return _structured_error(exc)
    return json.dumps(payload, ensure_ascii=False)


@app.tool(tags={REQUIRES_MECHANICAL_TAG}, annotations=_READ_ONLY)
def preview_property_change(
    ctx: Context,
    object_id: int,
    property_name: str,
    value: bool | int | float | str,
) -> str:
    """Validate a property change and show its effect without applying it.

    The preview reports the target object, the current value, the proposed
    value, and the validation result. A valid preview returns a single-use
    ``preview_token``. Nothing in the model is changed: show the preview to the
    user and call ``apply_property_change`` only after they agree.

    Values are checked strictly against the property type: booleans must be
    ``true`` or ``false``, integers must fit the property range, enum values must
    be an exact member name, and quantities must be a string such as
    ``"10 [mm]"`` with a unit compatible with the current value.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    object_id : int
        ID of the object, as returned by ``find_objects``.
    property_name : str
        API property name, as returned by ``describe_object``, such as
        ``ElementSize`` or ``NumberOfSteps``.
    value : bool, int, float, or str
        New value. Use a string for enum members and quantities.

    Returns
    -------
    str
        JSON with ``target``, ``current_value``, ``proposed_value``,
        ``validation`` (``valid``, ``errors``, and ``warnings``), and, when
        valid, ``no_change``, ``preview_token``, and ``expires_in_seconds``.
    """
    mechanical, error = _mechanical_or_error(ctx)
    if error is not None:
        return error

    args = {"object_id": object_id, "property_name": property_name, "value": value}
    try:
        payload = _run_introspection(
            mechanical, introspection.preview_change_script(args), "previewing the change"
        )
    except UpstreamError as exc:
        return _structured_error(exc)
    if not payload.get("success", False):
        return json.dumps(_with_suggestions(payload, property_name), ensure_ascii=False)

    fingerprint = payload.pop("fingerprint", None)
    if payload.get("validation", {}).get("valid") and isinstance(fingerprint, str):
        store = ctx.request_context.lifespan_context.change_previews
        payload["preview_token"] = introspection.store_preview(
            store, mechanical, object_id, property_name, value, fingerprint
        )
        payload["expires_in_seconds"] = introspection.PREVIEW_TTL_SECONDS
        payload["note"] = (
            "Nothing was changed. Call apply_property_change with the same arguments and "
            "this token to apply the change. The change is not reversible by this server, "
            "so call save_project first if you need a restore point."
        )
    return json.dumps(payload, ensure_ascii=False)


@app.tool(
    tags={REQUIRES_MECHANICAL_TAG},
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
    ),
)
def apply_property_change(
    ctx: Context,
    object_id: int,
    property_name: str,
    value: bool | int | float | str,
    preview_token: str,
) -> str:
    """Apply a property change that was previewed with ``preview_property_change``.

    The change is applied only if the token matches the same object, property,
    and value, has not been used, has not expired, and the current value has not
    changed since the preview. Otherwise nothing is changed and the call fails.
    After applying, the value is read back from Mechanical. There is no
    automatic undo.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    object_id : int
        ID of the object, exactly as previewed.
    property_name : str
        API property name, exactly as previewed.
    value : bool, int, float, or str
        New value, exactly as previewed.
    preview_token : str
        Token returned by ``preview_property_change``. Each token works once.

    Returns
    -------
    str
        JSON with ``target``, ``previous_value``, the read-back ``value``,
        ``readback_matches``, and ``warnings``. Errors use ``stale_preview``
        when the preview is no longer valid.
    """
    mechanical, error = _mechanical_or_error(ctx)
    if error is not None:
        return error

    store = ctx.request_context.lifespan_context.change_previews
    try:
        entry = introspection.take_preview(
            store, preview_token, mechanical, object_id, property_name, value
        )
    except (StalePreviewError, InvalidArgumentsError) as exc:
        return _structured_error(exc)

    args = {
        "object_id": object_id,
        "property_name": property_name,
        "value": value,
        "fingerprint": entry["fingerprint"],
    }
    try:
        payload = _run_introspection(
            mechanical, introspection.apply_change_script(args), "applying the change"
        )
    except UpstreamError as exc:
        return _structured_error(exc)
    return json.dumps(payload, ensure_ascii=False)


@app.tool(tags={REQUIRES_MECHANICAL_TAG}, annotations=_READ_ONLY)
def check_script(
    ctx: Context,
    script: str | None = None,
    file_path: str | None = None,
) -> str:
    """Check a Mechanical script without running it.

    Use this before ``run_python_script`` to catch mistakes early. The script is
    compiled, not run, by the scripting engine of the connected Mechanical, so
    syntax that the engine does not support (for example, f-strings in
    IronPython 2.7) is reported. Names such as ``Model.Mesh.ElementSize`` are
    then looked up in the live session to find misspelled or nonexistent API
    members. Lookups read properties but never call methods.

    A passing check does not guarantee that the script succeeds: argument
    types, values, and the model state at run time are not validated.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    script : str, optional
        Script to check. Required when ``file_path`` is not provided.
    file_path : str, optional
        Path to a local Python (``.py``) script file to check. Takes precedence
        over ``script`` when both are provided.

    Returns
    -------
    str
        JSON with ``valid``, ``engine_syntax``, ``python3_syntax``,
        ``api_check`` (``performed``, ``checked_count``, ``problems`` with line,
        chain, message, and suggestions, and ``unverified``), and the connected
        ``product_version`` and ``python_engine``.
    """
    mechanical, error = _mechanical_or_error(ctx)
    if error is not None:
        return error

    if file_path is not None:
        # check_script is read-only and may be auto-approved by hosts, and syntax
        # errors echo a source line, so only read Python scripts.
        if Path(file_path).suffix.lower() != ".py":
            return _structured_error(
                InvalidArgumentsError("file_path must point to a Python (.py) script.")
            )
        try:
            script = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            return _structured_error(
                InvalidArgumentsError(f"Cannot read script file '{file_path}': {exc}")
            )
    if script is None:
        return _structured_error(
            InvalidArgumentsError("Provide either a 'script' string or a 'file_path' to check.")
        )

    chains, python3_error, star_import = introspection.extract_api_chains(script)
    truncated = len(chains) > introspection.MAX_CHECKED_CHAINS
    chains = chains[: introspection.MAX_CHECKED_CHAINS]
    args = {"source": script, "chains": [chain["parts"] for chain in chains]}
    try:
        payload = _run_introspection(
            mechanical, introspection.check_script_script(args), "checking the script"
        )
    except UpstreamError as exc:
        return _structured_error(exc)
    if not payload.get("success", False):
        return json.dumps(payload, ensure_ascii=False)

    problems: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    for chain, resolution in zip(chains, payload.get("resolutions", []), strict=False):
        parts = chain["parts"]
        status = resolution.get("status")
        index = resolution.get("index", 0)
        location = {"line": chain["line"], "column": chain["column"]}
        if status == "undefined":
            problems.append(
                {
                    **location,
                    "severity": "warning" if star_import else "error",
                    "chain": parts[0],
                    "message": f"Name '{parts[0]}' is not defined in the Mechanical session.",
                }
            )
        elif status == "missing":
            owner = ".".join(parts[:index])
            problems.append(
                {
                    **location,
                    "severity": "error",
                    "chain": ".".join(parts[: index + 1]),
                    "message": f"'{owner}' has no member '{parts[index]}'.",
                    "suggestions": introspection.close_matches(
                        parts[index], resolution.get("candidates", [])
                    ),
                }
            )
        elif status == "unverified":
            unverified.append(
                {
                    **location,
                    "chain": ".".join(parts[: index + 1]),
                    "reason": resolution.get("reason", "not checked"),
                }
            )

    engine_syntax = payload.get("engine_syntax", {"valid": False})
    python_engine = payload.get("python_engine")
    if not engine_syntax.get("valid") and python3_error is None:
        engine_syntax["note"] = (
            f"The script is valid Python 3, but not valid for the {python_engine} "
            "engine used by this Mechanical session."
        )
    if python3_error is not None:
        api_check: dict[str, Any] = {
            "performed": False,
            "reason": "The script is not valid Python 3, so API names were not checked.",
        }
    else:
        api_check = {
            "performed": True,
            "checked_count": len(chains),
            "problems": problems,
            "unverified": unverified,
        }
        if truncated:
            api_check["note"] = (
                f"Only the first {introspection.MAX_CHECKED_CHAINS} names were checked."
            )

    result = {
        "success": True,
        "valid": bool(engine_syntax.get("valid"))
        and not any(p["severity"] == "error" for p in problems),
        "executed": False,
        "engine_syntax": engine_syntax,
        "python3_syntax": {"valid": True}
        if python3_error is None
        else {"valid": False, **python3_error},
        "api_check": api_check,
        "product_version": payload.get("product_version"),
        "python_engine": python_engine,
        "note": (
            "The script was not run. Argument types, values, and the model state at run time "
            "are not checked, and names created at run time are not resolved."
        ),
    }
    return json.dumps(result, ensure_ascii=False)


####################################################################################################
# Internal helpers


def _sanitize_output(text: str) -> str:
    """Sanitize output text to handle encoding issues.

    This function removes or replaces problematic Unicode characters that can cause
    encoding issues on Windows systems with limited character sets.

    Parameters
    ----------
    text : str
        The text to sanitize.

    Returns
    -------
    str
        The sanitized text with problematic characters removed or replaced.
    """
    if not isinstance(text, str):
        return text

    # Replace common problematic Unicode characters with ASCII alternatives
    replacements = {
        # Checkmarks and crosses
        "\u2713": "[OK]",  # checkmark
        "\u2717": "[X]",  # cross
        # Box drawing characters
        "\u2514": "\\",  # box drawing
        "\u2502": "|",  # box drawing
        "\u2500": "-",  # box drawing
        "\u2510": "\\",  # box drawing
        "\u250c": "/",  # box drawing
        "\u2518": "/",  # box drawing
        # Block elements
        "\u2588": "#",  # block
        "\u2589": "#",  # block
        "\u258a": "#",  # block
        "\u258c": "|",  # block
        "\u2590": "|",  # block
        # Superscript and subscript characters
        "\u00b9": "^1",  # superscript 1
        "\u00b2": "^2",  # superscript 2
        "\u00b3": "^3",  # superscript 3
        "\u2074": "^4",  # superscript 4
        "\u2075": "^5",  # superscript 5
        "\u2076": "^6",  # superscript 6
        "\u2077": "^7",  # superscript 7
        "\u2078": "^8",  # superscript 8
        "\u2079": "^9",  # superscript 9
        "\u2070": "^0",  # superscript 0
        # Other commonly problematic characters
        "\u2022": "*",  # bullet
        "\u2023": "*",  # triangular bullet
        "\u2219": "*",  # bullet operator
        "\u00a0": " ",  # non-breaking space
        "\u200b": "",  # zero-width space
        "\u200c": "",  # zero-width non-joiner
        "\u200d": "",  # zero-width joiner
        "\ufeff": "",  # zero-width no-break space
    }

    for unicode_char, replacement in replacements.items():
        text = text.replace(unicode_char, replacement)

    # Remove any remaining characters that can't be encoded in ascii
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        text = text.encode("ascii", errors="replace").decode("ascii")

    return text


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def get_mechanical_logs(
    ctx: Context,
    source: str = "messages",
    tail_lines: int = 200,
    contains: str | None = None,
    max_chars: int = 40000,
    analysis_index: int | None = None,
) -> str:
    """Return recent log entries from the connected Mechanical instance.

    This tool provides visibility into Mechanical session activity by reading
    either the application message list or solver output log file.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    source : str, optional
        Log source to read. Options are:

        - ``"messages"`` (default): Application messages (errors, warnings,
          info) from ``ExtAPI.Application.Messages``.
        - ``"solve_log"``: Raw solver transcript from ``solve.out`` in the
          solver working directory, read on the Mechanical host.

    tail_lines : int, default: 200
        Number of most recent lines to return.
    contains : str, optional
        Case-insensitive substring filter applied to each line.
    max_chars : int, default: 40000
        Maximum character count for the returned log text.
    analysis_index : int, optional
        Analysis whose ``solve.out`` to read (0-based) when ``source`` is
        ``"solve_log"``. When ``None``, the most recently written log is read.

    Returns
    -------
    str
        JSON string with log metadata and selected log text.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection is available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if tail_lines <= 0:
        return "Invalid parameter: tail_lines must be greater than 0."
    if max_chars <= 0:
        return "Invalid parameter: max_chars must be greater than 0."
    if analysis_index is not None and analysis_index < 0:
        return "Invalid parameter: analysis_index must be zero or greater."

    safe_tail_lines = min(tail_lines, 5000)
    safe_max_chars = min(max_chars, 200000)

    try:
        if source == "messages":
            return _get_mechanical_messages(mechanical, safe_tail_lines, contains, safe_max_chars)
        elif source == "solve_log":
            return _get_mechanical_solve_log(
                mechanical, safe_tail_lines, contains, safe_max_chars, analysis_index
            )
        else:
            return json.dumps(
                {
                    "error": (
                        f"Unknown source: {source!r}. Accepted values: 'messages', 'solve_log'."
                    )
                }
            )
    except Exception as e:
        error_msg = f"Error reading Mechanical logs: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"error": error_msg})


def _get_mechanical_messages(
    mechanical: Any,
    tail_lines: int,
    contains: str | None,
    max_chars: int,
) -> str:
    """Read application messages from Mechanical via ExtAPI."""
    script = """
import json
# str() raises in IronPython 2.7 for messages with non-ASCII text. .NET strings
# already arrive as text, so keep them as they are.
try:
    _text_types = (basestring,)
except NameError:
    _text_types = (str,)


def _text(value):
    if isinstance(value, _text_types):
        return value
    return u'{0}'.format(value)


msgs = ExtAPI.Application.Messages
entries = []
for i in range(msgs.Count):
    m = msgs[i]
    entries.append({
        "severity": str(m.Severity),
        "source": _text(m.Source) if hasattr(m, 'Source') else "",
        "summary": _text(m.Summary) if hasattr(m, 'Summary') else _text(m),
    })
json.dumps(entries, ensure_ascii=False)
"""
    raw = mechanical.run_python_script(script)

    try:
        entries = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Fallback: treat raw output as line-delimited text
        entries = None

    if entries is not None:
        lines = [
            f"[{e.get('severity', '?')}] {e.get('source', '')}: {e.get('summary', '')}"
            for e in entries
        ]
    else:
        lines = (raw or "").splitlines()

    # Filter
    if contains:
        token = contains.lower()
        lines = [ln for ln in lines if token in ln.lower()]

    total = len(lines)
    selected = lines[-tail_lines:]
    text = "\n".join(selected)

    truncated = False
    if len(text) > max_chars:
        text = text[-max_chars:]
        truncated = True

    return json.dumps(
        {
            "source": "messages",
            "total_messages": total,
            "returned_lines": len(selected),
            "tail_lines_requested": tail_lines,
            "contains": contains,
            "truncated": truncated,
            "logs": text,
        },
        indent=2,
    )


# Body of the remote solve.out reader. The caller prepends ``analysis_filter``,
# ``contains_filter`` (lower-case or None), and ``tail_count``.
_SOLVE_LOG_SCRIPT = """
import io
import json
import os


def _solve_log_candidates():
    paths = []
    for analysis_idx in range(Model.Analyses.Count):
        if analysis_filter is not None and analysis_idx != analysis_filter:
            continue
        try:
            working_dir = Model.Analyses[analysis_idx].WorkingDir
        except:
            working_dir = None
        if working_dir:
            path = os.path.join(working_dir, 'solve.out')
            if os.path.isfile(path):
                paths.append(path)
    if not paths and analysis_filter is None:
        for dir_path, _, file_names in os.walk(ExtAPI.DataModel.Project.ProjectDirectory):
            if 'solve.out' in file_names:
                paths.append(os.path.join(dir_path, 'solve.out'))
    return paths


if analysis_filter is not None and analysis_filter >= Model.Analyses.Count:
    payload = {
        'found': False,
        'error': 'Analysis index {0} is out of range. Model has {1} analyses.'.format(
            analysis_filter, Model.Analyses.Count
        ),
    }
else:
    candidates = _solve_log_candidates()
    if not candidates:
        payload = {'found': False}
    else:
        log_path = max(candidates, key=os.path.getmtime)
        try:
            handle = io.open(log_path, 'r', encoding='utf-8', errors='replace')
        except:
            handle = open(log_path, 'r')
        try:
            lines = handle.read().splitlines()
        finally:
            handle.close()
        total = len(lines)
        if contains_filter:
            lines = [line for line in lines if contains_filter in line.lower()]
        payload = {
            'found': True,
            'path': log_path,
            'total_lines': total,
            'matched_lines': len(lines),
            'lines': lines[-tail_count:],
        }

json.dumps(payload, ensure_ascii=False)
"""


def _read_remote_solve_log(
    mechanical: Any, tail_lines: int, contains: str | None, analysis_index: int | None
) -> dict[str, Any] | None:
    """Read ``solve.out`` on the Mechanical host, or return ``None`` if that is not possible."""
    selector = "None" if analysis_index is None else str(int(analysis_index))
    contains_literal = json.dumps(contains.lower()) if contains else "None"
    script = (
        f"analysis_filter = {selector}\n"
        f"contains_filter = {contains_literal}\n"
        f"tail_count = {int(tail_lines)}\n"
        f"{_SOLVE_LOG_SCRIPT}"
    )
    try:
        payload = json.loads(str(mechanical.run_python_script(script)))
    except Exception as exc:
        logger.info("Remote solve.out read failed; using the local project path: %s", exc)
        return None
    if not isinstance(payload, dict) or "found" not in payload:
        return None
    return payload


def _get_mechanical_solve_log(
    mechanical: Any,
    tail_lines: int,
    contains: str | None,
    max_chars: int,
    analysis_index: int | None = None,
) -> str:
    """Read the solver ``solve.out`` log, preferring the copy on the Mechanical host."""
    payload = _read_remote_solve_log(mechanical, tail_lines, contains, analysis_index)
    if payload is None:
        return _get_local_solve_log(mechanical, tail_lines, contains, max_chars)

    if not payload.get("found"):
        return json.dumps(
            {
                "source": "solve_log",
                "error": payload.get("error")
                or (
                    "solve.out not found in the solver working directory. "
                    "Run a solve first to generate solver output."
                ),
            }
        )

    selected = [str(line) for line in payload.get("lines", [])]
    text = "\n".join(selected)

    truncated = False
    if len(text) > max_chars:
        text = text[-max_chars:]
        truncated = True

    return json.dumps(
        {
            "source": "solve_log",
            "log_file": payload.get("path"),
            "total_lines": payload.get("total_lines"),
            "matched_lines": payload.get("matched_lines"),
            "returned_lines": len(selected),
            "tail_lines_requested": tail_lines,
            "contains": contains,
            "truncated": truncated,
            "logs": text,
        },
        indent=2,
    )


def _get_local_solve_log(
    mechanical: Any,
    tail_lines: int,
    contains: str | None,
    max_chars: int,
) -> str:
    """Read the solve.out log file from the Mechanical project directory."""
    project_dir = str(mechanical.project_directory)
    solve_log = Path(project_dir) / "solve.out"

    if not solve_log.exists():
        # Try looking one level up or in common locations
        candidates = list(Path(project_dir).rglob("solve.out"))
        if candidates:
            solve_log = candidates[0]
        else:
            return json.dumps(
                {
                    "source": "solve_log",
                    "error": (
                        f"solve.out not found in {project_dir}. "
                        "Run a solve first to generate solver output."
                    ),
                }
            )

    with solve_log.open("r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    filtered = all_lines
    if contains:
        token = contains.lower()
        filtered = [ln for ln in all_lines if token in ln.lower()]

    total = len(all_lines)
    matched = len(filtered)
    selected = filtered[-tail_lines:]
    text = "".join(selected)

    truncated = False
    if len(text) > max_chars:
        text = text[-max_chars:]
        truncated = True

    return json.dumps(
        {
            "source": "solve_log",
            "log_file": str(solve_log),
            "total_lines": total,
            "matched_lines": matched,
            "returned_lines": len(selected),
            "tail_lines_requested": tail_lines,
            "contains": contains,
            "truncated": truncated,
            "logs": text,
        },
        indent=2,
    )


# Conditionally disable tools based on session configuration
if session.on_aali:
    app.disable(tags={"aali"})

if session.locked_connection:
    app.disable(tags={"locked_connection"})
