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

"""Tests for version-aware launch, session ownership, and remote-safe tools."""

import ast
import asyncio
import base64
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import ImageContent, TextContent
import psutil
import pytest

from ansys.mechanical.mcp import helpers, tools
from ansys.mechanical.mcp.server import PyMechanicalAppContext

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def run_mechanical_script(script: str, namespace: dict) -> object:
    """Run a generated Mechanical script and return its final expression, like Mechanical."""
    tree = ast.parse(script)
    body, last = tree.body[:-1], tree.body[-1]
    exec(compile(ast.Module(body=body, type_ignores=[]), "<script>", "exec"), namespace)  # noqa: S102
    if isinstance(last, ast.Expr):
        return eval(compile(ast.Expression(last.value), "<script>", "eval"), namespace)  # noqa: S307
    exec(compile(ast.Module(body=[last], type_ignores=[]), "<script>", "exec"), namespace)  # noqa: S102
    return None


def assert_ironpython_compatible(script: str) -> None:
    """Scripts sent to remote Mechanical sessions run on IronPython 2.7."""
    tree = ast.parse(script)
    assert not any(isinstance(node, ast.JoinedStr) for node in ast.walk(tree)), "f-string"
    assert not any(isinstance(node, ast.AnnAssign) for node in ast.walk(tree)), "annotation"


class Items(list):
    """A list exposing ``Count`` like a Mechanical collection."""

    @property
    def Count(self):  # noqa: N802
        return len(self)


def make_context(mechanical=None, owns=False):
    context = MagicMock()
    context.request_context.lifespan_context = PyMechanicalAppContext(
        mechanical=mechanical, owns_mechanical=owns
    )
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    context.elicit = AsyncMock(side_effect=RuntimeError("elicitation unavailable"))
    return context


# ---------------------------------------------------------------------------
# Version-aware launch
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestVersionNormalization:
    @pytest.mark.parametrize(
        "value", ["261", "v261", "V261", " 261 ", "26.1", "2026 R1", "2026R1", "2026r1", 261, 26.1]
    )
    def test_accepted_spellings(self, value):
        assert tools._normalize_mechanical_version(value) == 261

    @pytest.mark.parametrize("value", ["", "abc", "26", "2611", "2026", "R1", "26.10", "2026 R"])
    def test_rejected_spellings(self, value):
        with pytest.raises(ValueError, match="Unrecognized Mechanical version"):
            tools._normalize_mechanical_version(value)

    @pytest.mark.parametrize(("value", "expected"), [("242", 242), ("2025 R2", 252), ("27.1", 271)])
    def test_other_releases(self, value, expected):
        assert tools._normalize_mechanical_version(value) == expected


@pytest.mark.unit
class TestResolveLaunchExecutable:
    def test_no_version_keeps_exec_file(self):
        assert tools._resolve_launch_executable(None, None) == (None, None)
        assert tools._resolve_launch_executable(None, "C:/x.exe") == ("C:/x.exe", None)

    def test_resolves_requested_release_as_integer(self):
        with (
            patch.object(tools, "_pypim_configured", return_value=False),
            patch.object(
                tools.atp, "get_mechanical_path", return_value="C:/v261/AnsysWBU.exe"
            ) as m,
        ):
            assert tools._resolve_launch_executable("2026 R1", None) == (
                "C:/v261/AnsysWBU.exe",
                None,
            )
        m.assert_called_once_with(allow_input=False, version=261)

    def test_missing_release_lists_installed(self):
        with (
            patch.object(tools, "_pypim_configured", return_value=False),
            patch.object(tools.atp, "get_mechanical_path", return_value=None),
            patch.object(
                tools.atp,
                "get_available_ansys_installations",
                return_value={271: "a", 261: "b", -261: "student"},
            ),
        ):
            exec_file, error = tools._resolve_launch_executable("252", None)
        assert exec_file is None
        assert "Mechanical 252 was not found" in error
        assert "271, 261" in error
        assert "-261" not in error

    def test_resolver_exception_is_reported_as_not_found(self):
        with (
            patch.object(tools, "_pypim_configured", return_value=False),
            patch.object(tools.atp, "get_mechanical_path", side_effect=RuntimeError("boom")),
            patch.object(tools.atp, "get_available_ansys_installations", return_value={}),
        ):
            exec_file, error = tools._resolve_launch_executable("261", None)
        assert exec_file is None
        assert "none found" in error

    def test_invalid_version(self):
        exec_file, error = tools._resolve_launch_executable("latest", None)
        assert exec_file is None
        assert "Unrecognized Mechanical version" in error

    def test_exec_file_matching_version(self):
        with patch.object(tools.atp, "version_from_path", return_value=261):
            assert tools._resolve_launch_executable("261", "C:/v261/x.exe") == (
                "C:/v261/x.exe",
                None,
            )

    def test_exec_file_conflicting_version(self):
        with patch.object(tools.atp, "version_from_path", return_value=271):
            exec_file, error = tools._resolve_launch_executable("261", "C:/v271/x.exe")
        assert exec_file is None
        assert "Mechanical 271" in error and "261" in error

    def test_exec_file_with_unrecognized_path_is_kept(self):
        with patch.object(tools.atp, "version_from_path", side_effect=RuntimeError("no version")):
            assert tools._resolve_launch_executable("261", "/opt/custom/mech") == (
                "/opt/custom/mech",
                None,
            )

    def test_pypim_keeps_version_for_remote_launch(self):
        with (
            patch.object(tools, "_pypim_configured", return_value=True),
            patch.object(tools.atp, "get_mechanical_path") as find,
        ):
            assert tools._resolve_launch_executable("261", None) == (None, None)
        find.assert_not_called()

    def test_pypim_not_installed(self):
        with patch.dict("sys.modules", {"ansys.platform.instancemanagement": None}):
            assert tools._pypim_configured() is False


@pytest.mark.unit
class TestLaunchHonorsVersion:
    async def test_launch_fails_fast_when_release_missing(self):
        context = make_context()
        with (
            patch.object(tools.pymechanical, "launch_mechanical") as launch,
            patch.object(tools, "_pypim_configured", return_value=False),
            patch.object(tools.atp, "get_mechanical_path", return_value=None),
            patch.object(tools.atp, "get_available_ansys_installations", return_value={271: "a"}),
        ):
            result = await tools.launch_mechanical(context, version="261")

        assert result.startswith("Failed to launch Mechanical: Mechanical 261 was not found")
        launch.assert_not_called()
        context.elicit.assert_not_awaited()
        assert context.request_context.lifespan_context.mechanical is None

    async def test_launch_uses_resolved_executable(self):
        context = make_context()
        launched = MagicMock(version="261", project_directory="C:/proj")
        with (
            patch.object(tools.pymechanical, "launch_mechanical", return_value=launched) as launch,
            patch.object(tools, "_pypim_configured", return_value=False),
            patch.object(tools.atp, "get_mechanical_path", return_value="C:/v261/AnsysWBU.exe"),
        ):
            result = await tools.launch_mechanical(context, version="26.1", batch=True)

        assert "Executable: C:/v261/AnsysWBU.exe" in result
        kwargs = launch.call_args.kwargs
        assert kwargs["exec_file"] == "C:/v261/AnsysWBU.exe"
        assert kwargs["allow_input"] is False
        assert context.request_context.lifespan_context.owns_mechanical is True

    @pytest.mark.parametrize("version", ["26.1", "2026 R1", "v261"])
    async def test_pypim_receives_normalized_release(self, version):
        context = make_context()
        with (
            patch.object(tools, "_pypim_configured", return_value=True),
            patch.object(
                tools.pymechanical, "launch_mechanical", return_value=MagicMock()
            ) as launch,
        ):
            result = await tools.launch_mechanical(context, version=version, batch=True)
        assert "Successfully launched" in result
        assert launch.call_args.kwargs["version"] == "261"
        assert "exec_file" not in launch.call_args.kwargs

    async def test_launch_without_version_never_prompts(self):
        context = make_context()
        with patch.object(tools.pymechanical, "launch_mechanical", return_value=MagicMock()) as m:
            await tools.launch_mechanical(context, batch=True)
        assert m.call_args.kwargs["allow_input"] is False
        assert "exec_file" not in m.call_args.kwargs


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestStaleSessionRecovery:
    @pytest.mark.parametrize("tool_name", ["launch_mechanical", "connect_to_mechanical"])
    async def test_exited_session_is_replaced(self, tool_name):
        stale = MagicMock(exited=True)
        context = make_context(stale, owns=True)
        fresh = MagicMock(version="261")
        target = tool_name
        with patch.object(tools.pymechanical, target, return_value=fresh):
            result = await getattr(tools, tool_name)(
                context, **({"batch": True} if tool_name == "launch_mechanical" else {})
            )

        assert "Successfully" in result
        assert context.request_context.lifespan_context.mechanical is fresh
        stale.exit.assert_not_called()

    async def test_unresponsive_session_is_replaced(self):
        stale = MagicMock(exited=False, is_alive=False)
        context = make_context(stale)
        fresh = MagicMock(version="261")
        with patch.object(tools.pymechanical, "connect_to_mechanical", return_value=fresh):
            result = await tools.connect_to_mechanical(context)
        assert "Successfully connected" in result
        assert context.request_context.lifespan_context.mechanical is fresh

    async def test_probe_exception_means_dead(self):
        class _Broken:
            exited = False

            @property
            def is_alive(self):
                raise RuntimeError("Mechanical server connection terminated.")

        assert await tools._session_is_alive(_Broken()) is False

    async def test_live_session_is_kept(self):
        live = MagicMock(exited=False, is_alive=True)
        context = make_context(live)
        with patch.object(tools.pymechanical, "connect_to_mechanical") as connect:
            result = await tools.connect_to_mechanical(context)
        assert "Already connected" in result
        connect.assert_not_called()
        assert context.request_context.lifespan_context.mechanical is live

    async def test_slow_probe_is_treated_as_busy_and_alive(self):
        class _Busy:
            exited = False

            @property
            def is_alive(self):
                time.sleep(0.5)
                return False

        with patch.object(tools, "_LIVENESS_TIMEOUT", 0.05):
            assert await tools._session_is_alive(_Busy()) is True


@pytest.mark.unit
class TestLifecycleSerialization:
    async def test_concurrent_launches_start_one_instance(self):
        context = make_context()
        launches = []

        def _slow_launch(**kwargs):
            launches.append(kwargs)
            time.sleep(0.2)
            return MagicMock(version="261", exited=False, is_alive=True)

        with patch.object(tools.pymechanical, "launch_mechanical", side_effect=_slow_launch):
            results = await asyncio.gather(
                tools.launch_mechanical(context, batch=True),
                tools.launch_mechanical(context, batch=True),
            )

        assert len(launches) == 1
        assert sum("Successfully launched" in r for r in results) == 1
        assert sum("still in progress" in r for r in results) == 1

    async def test_blocking_launch_does_not_block_event_loop(self):
        context = make_context()
        released = threading.Event()

        def _blocking_launch(**kwargs):
            released.wait(timeout=5)
            return MagicMock(version="261")

        with patch.object(tools.pymechanical, "launch_mechanical", side_effect=_blocking_launch):
            task = asyncio.create_task(tools.launch_mechanical(context, batch=True))
            await asyncio.sleep(0.05)
            # The event loop is still free to serve other requests while launch blocks.
            assert not task.done()
            released.set()
            assert "Successfully launched" in await task


@pytest.mark.unit
class TestStartInstanceFlag:
    @pytest.mark.parametrize("value", ["false", "FALSE", "False"])
    async def test_explicit_false_refuses_and_names_the_flag(self, monkeypatch, value):
        monkeypatch.setenv("PYMECHANICAL_START_INSTANCE", value)
        context = make_context()
        with patch.object(tools.pymechanical, "launch_mechanical") as launch:
            result = await tools.launch_mechanical(context, batch=True)
        assert result.startswith("Failed to launch Mechanical: Starting Mechanical is disabled")
        assert "PYMECHANICAL_START_INSTANCE" in result
        assert "connect_to_mechanical" in result
        launch.assert_not_called()
        context.elicit.assert_not_awaited()

    async def test_invalid_value_is_reported(self, monkeypatch):
        monkeypatch.setenv("PYMECHANICAL_START_INSTANCE", "yes")
        context = make_context()
        with patch.object(tools.pymechanical, "launch_mechanical") as launch:
            result = await tools.launch_mechanical(context, batch=True)
        assert "invalid value 'yes'" in result
        launch.assert_not_called()

    @pytest.mark.parametrize("value", [None, "true", "TRUE"])
    async def test_unset_or_true_launches_a_new_instance(self, monkeypatch, value):
        if value is None:
            monkeypatch.delenv("PYMECHANICAL_START_INSTANCE", raising=False)
        else:
            monkeypatch.setenv("PYMECHANICAL_START_INSTANCE", value)
        context = make_context()
        with patch.object(tools.pymechanical, "launch_mechanical", return_value=MagicMock()) as m:
            result = await tools.launch_mechanical(context, batch=True)
        assert "Successfully launched" in result
        assert m.call_args.kwargs["start_instance"] is True

    async def test_pypim_launch_is_not_blocked(self, monkeypatch):
        monkeypatch.setenv("PYMECHANICAL_START_INSTANCE", "false")
        context = make_context()
        with (
            patch.object(tools, "_pypim_configured", return_value=True),
            patch.object(tools.pymechanical, "launch_mechanical", return_value=MagicMock()),
        ):
            result = await tools.launch_mechanical(context, batch=True)
        assert "Successfully launched" in result

    def test_core_start_instance_true_ignores_the_flag(self, monkeypatch, tmp_path):
        """PyMechanical starts a process, not an attach, when start_instance=True."""
        from ansys.mechanical.core import mechanical as core

        monkeypatch.setenv("PYMECHANICAL_START_INSTANCE", "false")
        exe = tmp_path / "AnsysWBU.exe"
        exe.write_text("", encoding="utf-8")
        with (
            patch.object(core, "_HAS_ANSYS_PIM", False),
            patch.object(core, "launch_grpc", return_value=10123) as launch_grpc,
            patch.object(core.atp, "version_from_path", return_value=261),
            patch.object(core, "Mechanical", return_value=MagicMock()) as client,
        ):
            core.launch_mechanical(exec_file=str(exe), start_instance=True, allow_input=False)
        launch_grpc.assert_called_once()
        assert client.call_args.kwargs["local"] is True


@pytest.mark.unit
class TestLaunchVersionCheck:
    async def test_mismatched_release_is_closed_and_reported(self):
        context = make_context()
        launched = MagicMock(version="271", project_directory="C:/proj")
        with (
            patch.object(tools.pymechanical, "launch_mechanical", return_value=launched),
            patch.object(tools, "_pypim_configured", return_value=False),
            patch.object(tools.atp, "get_mechanical_path", return_value="C:/v261/AnsysWBU.exe"),
        ):
            result = await tools.launch_mechanical(context, version="261", batch=True)
        assert "Mechanical 271 started, but 261 was requested" in result
        launched.exit.assert_called_once_with(force=True)
        assert context.request_context.lifespan_context.mechanical is None


def _blocking_worker():
    """A launch that blocks until released, recording how often it was started."""
    release = threading.Event()
    calls = []

    def _launch(**kwargs):
        calls.append(kwargs)
        release.wait(timeout=10)
        return MagicMock(version="261", project_directory="C:/proj", exited=False, is_alive=True)

    return _launch, release, calls


async def _wait_for_job(context, timeout=5.0):
    deadline = time.monotonic() + timeout
    while tools._pending_job(context) is None:
        assert time.monotonic() < deadline, "job did not start"
        await asyncio.sleep(0.01)
    return tools._pending_job(context)


@pytest.mark.unit
class TestSessionJobs:
    async def test_cancelled_request_still_records_the_launch(self):
        context = make_context()
        state = context.request_context.lifespan_context
        launch, release, calls = _blocking_worker()
        with patch.object(tools.pymechanical, "launch_mechanical", side_effect=launch):
            task = asyncio.create_task(tools.launch_mechanical(context, batch=True))
            job = await _wait_for_job(state)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            retry = await tools.launch_mechanical(context, batch=True)
            assert "still in progress" in retry
            assert len(calls) == 1

            release.set()
            await job.future
            await asyncio.sleep(0)

        assert state.mechanical is not None
        assert state.owns_mechanical is True
        assert tools._pending_job(state) is None
        assert "Already connected" in await tools.launch_mechanical(context, batch=True)

    async def test_connect_waits_for_a_launch_in_progress(self):
        context = make_context()
        state = context.request_context.lifespan_context
        launch, release, _ = _blocking_worker()
        with (
            patch.object(tools.pymechanical, "launch_mechanical", side_effect=launch),
            patch.object(tools.pymechanical, "connect_to_mechanical") as connect,
        ):
            task = asyncio.create_task(tools.launch_mechanical(context, batch=True))
            await _wait_for_job(state)
            result = await tools.connect_to_mechanical(context)
            assert "Mechanical launch started" in result
            connect.assert_not_called()
            release.set()
            assert "Successfully launched" in await task

    async def test_stuck_launch_is_stopped_and_its_late_result_discarded(self):
        context = make_context()
        state = context.request_context.lifespan_context
        launch, release, _ = _blocking_worker()
        own_processes = [MagicMock(name="mechanical-child")]
        with (
            patch.object(tools.pymechanical, "launch_mechanical", side_effect=launch),
            patch.object(tools, "_LAUNCH_START_TIMEOUT", 0.2),
            patch.object(tools, "_SESSION_DEADLINE_MARGIN", 0.0),
            patch.object(tools, "launched_mechanical_processes", return_value=own_processes),
            patch.object(tools, "stop_processes") as stop,
            patch.object(tools, "_close_quietly") as close,
        ):
            task = asyncio.create_task(tools.launch_mechanical(context, batch=True))
            job = await _wait_for_job(state)
            result = await task
            assert "did not finish within" in result
            stop.assert_called_once_with(own_processes)

            release.set()
            await job.future
            await asyncio.sleep(0.05)

        close.assert_called_once()
        assert job.abandoned is True
        assert state.mechanical is None
        assert tools._pending_job(state) is None

    async def test_stuck_connection_late_result_is_not_closed(self):
        context = make_context()
        state = context.request_context.lifespan_context
        release = threading.Event()
        attached = MagicMock(version="261")

        def _connect(**kwargs):
            release.wait(timeout=10)
            return attached

        with (
            patch.object(tools.pymechanical, "connect_to_mechanical", side_effect=_connect),
            patch.object(tools, "_CONNECT_TIMEOUT", 0.2),
            patch.object(tools, "_SESSION_DEADLINE_MARGIN", 0.0),
            patch.object(tools, "stop_processes") as stop,
        ):
            result = await tools.connect_to_mechanical(context)
            assert "did not finish within" in result
            stop.assert_called_once_with([])
            release.set()
            await asyncio.sleep(0.2)

        attached.exit.assert_not_called()
        assert state.mechanical is None

    async def test_expired_job_without_waiter_is_replaced_on_retry(self):
        context = make_context()
        state = context.request_context.lifespan_context
        launch, release, calls = _blocking_worker()
        with (
            patch.object(tools.pymechanical, "launch_mechanical", side_effect=launch),
            patch.object(tools, "launched_mechanical_processes", return_value=["old"]),
            patch.object(tools, "stop_processes") as stop,
        ):
            task = asyncio.create_task(tools.launch_mechanical(context, batch=True))
            stuck = await _wait_for_job(state)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            stuck.deadline = time.monotonic() - 1

            release.set()
            result = await tools.launch_mechanical(context, batch=True)

        assert "Successfully launched" in result
        stop.assert_called_once_with(["old"])
        assert len(calls) == 2
        assert stuck.abandoned is True

    async def test_failed_launch_stops_the_processes_it_left(self):
        context = make_context()
        with (
            patch.object(
                tools.pymechanical, "launch_mechanical", side_effect=RuntimeError("no license")
            ),
            patch.object(tools, "launched_mechanical_processes", return_value=["orphan"]),
            patch.object(tools, "stop_processes") as stop,
        ):
            result = await tools.launch_mechanical(context, batch=True)
            await asyncio.sleep(0.05)
        assert "no license" in result
        stop.assert_called_once_with(["orphan"])
        assert tools._pending_job(context.request_context.lifespan_context) is None

    async def test_disconnect_cancels_a_launch_in_progress(self):
        context = make_context()
        state = context.request_context.lifespan_context
        launch, release, _ = _blocking_worker()
        with (
            patch.object(tools.pymechanical, "launch_mechanical", side_effect=launch),
            patch.object(tools, "launched_mechanical_processes", return_value=["child"]),
            patch.object(tools, "stop_processes") as stop,
        ):
            task = asyncio.create_task(tools.launch_mechanical(context, batch=True))
            await _wait_for_job(state)
            result = await tools.disconnect_from_mechanical(context)
            assert "Cancelled the Mechanical launch" in result
            stop.assert_called_once_with(["child"])
            release.set()
            assert "cancelled before it finished" in await task
        assert state.mechanical is None

    async def test_status_and_diagnostics_report_the_operation(self):
        context = make_context()
        state = context.request_context.lifespan_context
        launch, release, _ = _blocking_worker()
        with patch.object(tools.pymechanical, "launch_mechanical", side_effect=launch):
            task = asyncio.create_task(tools.launch_mechanical(context, batch=True))
            await _wait_for_job(state)
            status = json.loads(tools.check_mechanical_status(context))
            assert status["in_progress"] == "launch"
            diagnostics = status
            assert diagnostics["operation_in_progress"]["kind"] == "launch"
            release.set()
            await task

    def test_server_shutdown_stops_a_launch_in_progress(self):
        from ansys.mechanical.mcp.server import PyMechanicalMCP

        mcp = PyMechanicalMCP(name="test")
        mcp.context = PyMechanicalAppContext()
        job = MagicMock(spec=tools._SessionJob, kind="launch")
        job.abandon.return_value = ["child"]
        mcp.context.session_job = job
        with patch("ansys.mechanical.mcp.helpers.stop_processes") as stop:
            mcp.product_cleanup()
        stop.assert_called_once_with(["child"])


class _FakeProcess:
    def __init__(self, pid, cmdline, descendants=()):
        self.pid = pid
        self._cmdline = cmdline
        self._descendants = list(descendants)

    def cmdline(self):
        return self._cmdline

    def children(self, recursive=False):
        return self._descendants


@pytest.mark.unit
class TestLaunchedProcessSelection:
    def test_only_new_grpc_children_and_their_descendants(self):
        solver = _FakeProcess(30, ["ansyscl.exe"])
        baseline_child = _FakeProcess(10, ["AnsysWBU.exe", "-grpc", "10000"])
        new_mechanical = _FakeProcess(20, ["AnsysWBU.exe", "-DSApplet", "-GRPC", "10001"], [solver])
        new_other = _FakeProcess(40, ["python.exe", "-i"])
        server = _FakeProcess(1, [], [baseline_child, new_mechanical, new_other])
        with patch.object(psutil, "Process", return_value=server):
            selected = helpers.launched_mechanical_processes(frozenset({10}))
        assert {p.pid for p in selected} == {20, 30}

    def test_stop_processes_kills_survivors(self):
        quick, stubborn = MagicMock(), MagicMock()
        with patch.object(psutil, "wait_procs", return_value=([quick], [stubborn])):
            helpers.stop_processes([quick, stubborn], timeout=0.1)
        quick.terminate.assert_called_once()
        stubborn.terminate.assert_called_once()
        stubborn.kill.assert_called_once()
        quick.kill.assert_not_called()


@pytest.mark.unit
def test_diagnostics_report_ownership():
    context = make_context(MagicMock(is_alive=True), owns=True)
    data = json.loads(tools.check_mechanical_status(context))
    assert data["mechanical_launched_by_server"] is True

    context = make_context(None)
    data = json.loads(tools.check_mechanical_status(context))
    assert data["mechanical_launched_by_server"] is False


# ---------------------------------------------------------------------------
# Screenshot: export on the Mechanical host and transfer over gRPC
# ---------------------------------------------------------------------------
def _screenshot_mechanical(tmp_path, image_bytes=PNG_BYTES, view="model"):
    mechanical = MagicMock()
    calls = []

    def _run(script):
        calls.append(script)
        if "ExportImage" in script:
            return json.dumps({"path": "C:\\remote\\proj\\shot.png", "activated": view})
        return ""

    def _download(remote_path, target_dir=None, progress_bar=None):
        local = Path(target_dir) / "shot.png"
        local.write_bytes(image_bytes)
        return [str(local)]

    mechanical.run_python_script.side_effect = _run
    mechanical.download.side_effect = _download
    return mechanical, calls


@pytest.mark.unit
class TestScreenshotTransfer:
    def test_downloads_validates_and_cleans_up(self, tmp_path):
        mechanical, calls = _screenshot_mechanical(tmp_path)
        context = make_context(mechanical)
        created_dirs = []
        real_mkdtemp = tools.tempfile.mkdtemp

        def _mkdtemp(**kwargs):
            created_dirs.append(real_mkdtemp(dir=tmp_path, **kwargs))
            return created_dirs[-1]

        with patch.object(tools.tempfile, "mkdtemp", side_effect=_mkdtemp):
            result = tools.screenshot(context)

        assert isinstance(result[1], ImageContent)
        assert base64.b64decode(result[1].data) == PNG_BYTES
        assert "view: model" in result[0].text
        mechanical.download.assert_called_once()
        assert mechanical.download.call_args.args[0] == "C:\\remote\\proj\\shot.png"
        # The local copy and the file on the Mechanical host are both removed.
        assert not Path(created_dirs[0]).exists()
        assert "os.remove" in calls[-1] and "shot.png" in calls[-1]

    def test_non_png_is_reported_not_returned(self, tmp_path):
        mechanical, calls = _screenshot_mechanical(tmp_path, image_bytes=b"")
        result = tools.screenshot(make_context(mechanical))
        assert len(result) == 1 and isinstance(result[0], TextContent)
        assert "did not produce a PNG" in result[0].text
        assert "os.remove" in calls[-1]

    def test_download_failure_still_cleans_remote_file(self, tmp_path):
        mechanical, calls = _screenshot_mechanical(tmp_path)
        mechanical.download.side_effect = ValueError("no such file")
        result = tools.screenshot(make_context(mechanical))
        assert "Failed to capture screenshot: no such file" in result[0].text
        assert "os.remove" in calls[-1]

    def test_unexpected_script_response(self, tmp_path):
        mechanical = MagicMock()
        mechanical.run_python_script.return_value = "not json"
        result = tools.screenshot(make_context(mechanical))
        assert "unexpected response" in result[0].text
        mechanical.download.assert_not_called()

    def test_script_writes_into_project_directory(self, tmp_path):
        mechanical = MagicMock()
        mechanical.run_python_script.return_value = "not json"
        tools.screenshot(make_context(mechanical), view_type="mesh")
        script = mechanical.run_python_script.call_args_list[0].args[0]
        assert_ironpython_compatible(script)

        exported = []

        def _export(path, *args):
            Path(path).write_bytes(PNG_BYTES)
            exported.append(path)

        namespace = {
            "Model": MagicMock(),
            "ExtAPI": SimpleNamespace(
                DataModel=SimpleNamespace(Project=SimpleNamespace(ProjectDirectory=str(tmp_path))),
                Graphics=SimpleNamespace(ExportImage=_export),
            ),
            "Ansys": MagicMock(),
            "GraphicsResolutionType": MagicMock(),
            "GraphicsImageExportFormat": MagicMock(),
        }
        result = json.loads(run_mechanical_script(script, namespace))
        assert result["activated"] == "mesh"
        assert Path(result["path"]).parent == tmp_path
        assert Path(result["path"]).name.startswith("mcp_screenshot_")
        assert exported == [result["path"]]


# ---------------------------------------------------------------------------
# Results summary: never report stale values
# ---------------------------------------------------------------------------
class _Result:
    DataModelObjectCategory = "EquivalentStress"

    def __init__(self, name, state, value=5.0):
        self.Name = name
        self._state = state
        self.Minimum = 0.0
        self.Maximum = value
        self.Average = value / 2

    @property
    def ObjectState(self):  # noqa: N802
        if self._state is None:
            raise AttributeError("ObjectState")
        return self._state


class _Solution:
    def __init__(self, status, children, status_after_evaluate=None, evaluate_error=None):
        self.Status = status
        self.Children = Items(children)
        self._after = status_after_evaluate
        self._error = evaluate_error
        self.evaluated = False

    def EvaluateAllResults(self):  # noqa: N802
        self.evaluated = True
        if self._error:
            raise RuntimeError(self._error)
        if self._after:
            self.Status = self._after


def _summary(solution):
    analysis = SimpleNamespace(Name="Static", AnalysisType="Static", Solution=solution)
    namespace = {"Model": SimpleNamespace(Analyses=Items([analysis]))}
    script = f"{tools._SCRIPT_HELPERS}\nanalysis_filter = None\n{tools._RESULTS_SUMMARY_SCRIPT}"
    assert_ironpython_compatible(script)
    data = json.loads(run_mechanical_script(script, namespace))
    return data["analyses"][0]


@pytest.mark.unit
class TestResultsSummaryValidity:
    def test_solved_results_report_values(self):
        entry = _summary(_Solution("Done", [_Result("Stress", "Solved")]))
        result = entry["results"][0]
        assert result["state"] == "Solved"
        assert result["maximum"] == {"value": 5.0, "unit": None}

    def test_obsolete_results_report_no_values(self):
        solution = _Solution("SolveRequired", [_Result("Stress", "Obsolete")])
        entry = _summary(solution)
        result = entry["results"][0]
        assert result["state"] == "Obsolete"
        assert result["minimum"] is result["maximum"] is result["average"] is None
        assert solution.evaluated is False

    def test_failed_evaluation_reports_no_values(self):
        entry = _summary(_Solution("Done", [_Result("Stress", "SolveFailed")]))
        assert entry["results"][0]["maximum"] is None

    def test_postprocessing_required_is_evaluated(self):
        solution = _Solution(
            "PostProcessingRequired",
            [_Result("Stress", "Solved")],
            status_after_evaluate="Done",
        )
        entry = _summary(solution)
        assert solution.evaluated is True
        assert entry["solution_status"] == "Done"
        assert entry["results"][0]["maximum"]["value"] == 5.0

    def test_evaluation_error_is_reported(self):
        entry = _summary(_Solution("Done", [_Result("Stress", "Solved")], evaluate_error="bad"))
        assert entry["evaluation_error"] == "bad"

    @pytest.mark.parametrize(("status", "has_values"), [("Done", True), ("SolveRequired", False)])
    def test_missing_object_state_falls_back_to_solution_status(self, status, has_values):
        entry = _summary(_Solution(status, [_Result("Stress", None)]))
        result = entry["results"][0]
        assert result["state"] is None
        assert (result["maximum"] is not None) is has_values


# ---------------------------------------------------------------------------
# Model info and export scripts
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_model_info_counts_bodies_recursively():
    mechanical = MagicMock()
    mechanical.run_python_script.return_value = "{}"
    tools.get_model_info(make_context(mechanical))
    script = mechanical.run_python_script.call_args.args[0]
    assert "geom.GetChildren(DataModelObjectCategory.Body, True)" in script
    assert "geom.Children.Count" not in script
    assert_ironpython_compatible(script)


@pytest.mark.unit
@pytest.mark.parametrize("max_items,expected", [(0, 0), (50, 50), (None, 2105)])
def test_model_info_bounds_lists_on_mechanical_host(max_items, expected):
    mechanical = MagicMock()
    tools.get_model_info(make_context(mechanical), max_items=max_items)
    script = mechanical.run_python_script.call_args.args[0]
    bodies = Items(
        [
            SimpleNamespace(GeometryType="Solid", Suppressed=False),
            SimpleNamespace(GeometryType="Surface", Suppressed=True),
            SimpleNamespace(),
        ]
    )
    model = SimpleNamespace(
        Name="Model",
        Geometry=SimpleNamespace(GetChildren=lambda *args: bodies),
        Analyses=Items(),
        Materials=SimpleNamespace(Children=Items()),
        NamedSelections=SimpleNamespace(
            Children=Items(
                [SimpleNamespace(Name="Selection %04d" % index) for index in range(2105)]
            )
        ),
    )
    namespace = {
        "Model": model,
        "ExtAPI": SimpleNamespace(
            DataModel=SimpleNamespace(
                Project=SimpleNamespace(ProductVersion="2026 R1", Name="Project")
            )
        ),
        "DataModelObjectCategory": SimpleNamespace(Body="Body"),
    }
    result = json.loads(run_mechanical_script(script, namespace))
    assert len(result["named_selections"]) == expected
    meta = result["collection_info"]["named_selections"]
    assert meta["total_count"] == 2105
    assert meta["truncated"] is (expected < 2105)
    assert result["geometry"]["body_counts_by_type"] == {"Solid": 1, "Surface": 1, "Unknown": 1}
    assert result["geometry"]["suppression_counts"] == {"suppressed": 1, "active": 1, "unknown": 1}
    assert_ironpython_compatible(script)


@pytest.mark.unit
@pytest.mark.parametrize("value", [-1, 1001, True, "50"])
def test_model_info_rejects_invalid_limit(value):
    mechanical = MagicMock()
    result = json.loads(tools.get_model_info(make_context(mechanical), max_items=value))
    assert result["error_code"] == "invalid_arguments"
    mechanical.run_python_script.assert_not_called()


class _ExportResult:
    def __init__(self, name):
        self.Name = name
        self.Maximum = 1.0

    def Activate(self):  # noqa: N802
        pass

    def ExportToTextFile(self, path):  # noqa: N802
        Path(path).write_text("data", encoding="utf-8")


def _run_export(tmp_path, children, output_dir, evaluate_error=None, **kwargs):
    mechanical = MagicMock()
    mechanical.run_python_script.return_value = "{}"
    tools.export_results(make_context(mechanical), output_dir=str(output_dir), **kwargs)
    script = mechanical.run_python_script.call_args.args[0]
    assert_ironpython_compatible(script)

    solution = _Solution("Done", children, evaluate_error=evaluate_error)
    namespace = {
        "Model": SimpleNamespace(Analyses=Items([SimpleNamespace(Solution=solution)])),
        "Graphics": SimpleNamespace(
            ExportImage=lambda path, *args: Path(path).write_bytes(PNG_BYTES)
        ),
        "GraphicsImageExportFormat": SimpleNamespace(PNG="PNG"),
    }
    return json.loads(run_mechanical_script(script, namespace))


@pytest.mark.unit
class TestExportResults:
    def test_output_directory_is_created_on_mechanical_host_only(self, tmp_path):
        mechanical = MagicMock()
        mechanical.run_python_script.return_value = "{}"
        target = tmp_path / "not" / "created"
        tools.export_results(make_context(mechanical), output_dir=str(target))
        # The MCP host must not create directories for a possibly remote Mechanical.
        assert not target.exists()

        data = _run_export(tmp_path, [_ExportResult("Total Deformation")], target)
        assert data["success"] is True
        assert (target / "Total_Deformation.png").is_file()

    def test_invalid_and_duplicate_names_are_safe(self, tmp_path):
        children = [
            _ExportResult("Stress: Max/Min"),
            _ExportResult("Stress: Max/Min"),
            _ExportResult("Deformation (2)"),
        ]
        data = _run_export(tmp_path, children, tmp_path, export_format="both")
        names = sorted(Path(p).name for p in data["exported_files"])
        assert names == [
            "Deformation_(2).png",
            "Deformation_(2).txt",
            "Stress__Max_Min.png",
            "Stress__Max_Min.txt",
            "Stress__Max_Min_2.png",
            "Stress__Max_Min_2.txt",
        ]
        assert all(Path(p).is_file() for p in data["exported_files"])

    def test_generated_suffix_does_not_overwrite_existing_name(self, tmp_path):
        children = [_ExportResult(name) for name in ["Stress", "Stress", "Stress_2", "stress"]]
        data = _run_export(tmp_path, children, tmp_path, export_format="txt")
        names = [Path(path).name.lower() for path in data["exported_files"]]
        assert data["success"] is True
        assert len(names) == len(set(names)) == 4
        assert all(Path(path).is_file() for path in data["exported_files"])

    def test_evaluation_error_is_reported(self, tmp_path):
        data = _run_export(tmp_path, [_ExportResult("Stress")], tmp_path, evaluate_error="bad")
        assert "Result evaluation failed: bad" in data["errors"]

    def test_negative_index_is_rejected(self):
        mechanical = MagicMock()
        data = json.loads(tools.export_results(make_context(mechanical), analysis_index=-1))
        assert data["success"] is False
        mechanical.run_python_script.assert_not_called()


# ---------------------------------------------------------------------------
# Solve log read on the Mechanical host
# ---------------------------------------------------------------------------
def _solve_log_namespace(tmp_path, working_dirs):
    analyses = Items([SimpleNamespace(WorkingDir=str(d) if d else None) for d in working_dirs])
    return {
        "Model": SimpleNamespace(Analyses=analyses),
        "ExtAPI": SimpleNamespace(
            DataModel=SimpleNamespace(Project=SimpleNamespace(ProjectDirectory=str(tmp_path)))
        ),
    }


def _remote_mechanical(namespace):
    mechanical = MagicMock()
    mechanical.project_directory = "/does/not/exist/locally"
    scripts = []

    def _run(script):
        scripts.append(script)
        return run_mechanical_script(script, dict(namespace))

    mechanical.run_python_script.side_effect = _run
    return mechanical, scripts


@pytest.mark.unit
class TestRemoteSolveLog:
    def test_reads_selected_analysis_on_mechanical_host(self, tmp_path):
        first, second = tmp_path / "a1", tmp_path / "a2"
        first.mkdir()
        second.mkdir()
        (first / "solve.out").write_text("one\nERROR first\n", encoding="utf-8")
        (second / "solve.out").write_text(
            "\n".join(f"line {i}" for i in range(10)) + "\nERROR second\n", encoding="utf-8"
        )
        mechanical, scripts = _remote_mechanical(_solve_log_namespace(tmp_path, [first, second]))

        data = json.loads(tools._get_mechanical_solve_log(mechanical, 3, None, 1000, 1))

        assert_ironpython_compatible(scripts[0])
        assert data["log_file"] == str(second / "solve.out")
        assert data["total_lines"] == 11
        assert data["logs"] == "line 8\nline 9\nERROR second"

        data = json.loads(tools._get_mechanical_solve_log(mechanical, 10, "error", 1000, 0))
        assert data["matched_lines"] == 1
        assert data["logs"] == "ERROR first"

    def test_most_recent_log_by_default(self, tmp_path):
        old, new = tmp_path / "old", tmp_path / "new"
        old.mkdir()
        new.mkdir()
        (old / "solve.out").write_text("old\n", encoding="utf-8")
        (new / "solve.out").write_text("new\n", encoding="utf-8")
        import os

        os.utime(old / "solve.out", (1, 1))
        mechanical, _ = _remote_mechanical(_solve_log_namespace(tmp_path, [old, new]))
        data = json.loads(tools._get_mechanical_solve_log(mechanical, 5, None, 1000))
        assert data["logs"] == "new"

    def test_falls_back_to_project_directory_walk(self, tmp_path):
        nested = tmp_path / "x" / "y"
        nested.mkdir(parents=True)
        (nested / "solve.out").write_text("walked\n", encoding="utf-8")
        mechanical, _ = _remote_mechanical(_solve_log_namespace(tmp_path, [None]))
        data = json.loads(tools._get_mechanical_solve_log(mechanical, 5, None, 1000))
        assert data["logs"] == "walked"

    def test_not_found_and_out_of_range(self, tmp_path):
        mechanical, _ = _remote_mechanical(_solve_log_namespace(tmp_path, [tmp_path / "none"]))
        data = json.loads(tools._get_mechanical_solve_log(mechanical, 5, None, 1000, 0))
        assert "solve.out not found" in data["error"]
        data = json.loads(tools._get_mechanical_solve_log(mechanical, 5, None, 1000, 4))
        assert "out of range" in data["error"]

    def test_negative_analysis_index_is_rejected(self):
        mechanical = MagicMock()
        result = tools.get_mechanical_logs(
            make_context(mechanical), source="solve_log", analysis_index=-1
        )
        assert "analysis_index must be zero or greater" in result
        mechanical.run_python_script.assert_not_called()


# ---------------------------------------------------------------------------
# Instance discovery
# ---------------------------------------------------------------------------
class _Proc:
    def __init__(self, name, pid, cmdline, children=0, vanish=False):
        self._name = name
        self.pid = pid
        self._cmdline = cmdline
        self._children = children
        self._vanish = vanish
        self._name_calls = 0

    def cmdline(self):
        return self._cmdline

    def status(self):
        return psutil.STATUS_RUNNING

    def name(self):
        self._name_calls += 1
        if self._vanish and self._name_calls > 1:
            raise psutil.NoSuchProcess(pid=self.pid)
        return self._name

    def children(self, recursive=True):
        return [object()] * self._children

    def cwd(self):
        return "C:/work"


@pytest.mark.unit
class TestInstanceDiscovery:
    def test_grpc_port_and_headless_instances(self, monkeypatch):
        batch = _Proc(
            "AnsysWBU.exe",
            11,
            ["AnsysWBU.exe", "-DSApplet", "-b", "-AppModeMech", "-grpc", "10001"],
        )
        mcp_server = _Proc("ansys-mechanical-mcp.exe", 12, ["ansys-mechanical-mcp", "--port", "9"])
        monkeypatch.setattr(psutil, "process_iter", lambda: [batch, mcp_server])

        table = helpers.list_instances(instances=True)

        assert "10001" in table
        assert "11" in table
        assert "ansys-mechanical-mcp" not in table

    def test_upper_case_windows_command_line(self, monkeypatch):
        gui = _Proc(
            "AnsysWBU.exe",
            31,
            ["C:\\V271\\ANSYSWBU.EXE", "-DSAPPLET", "-APPMODEMECH", "-GRPC", "10050"],
        )
        monkeypatch.setattr(psutil, "process_iter", lambda: [gui])
        table = helpers.list_instances(instances=True)
        assert "10050" in table
        assert "31" in table

    def test_process_exiting_during_listing_is_skipped(self, monkeypatch):
        gone = _Proc("AnsysWBU.exe", 21, ["AnsysWBU.exe", "-grpc", "10002"], vanish=True)
        monkeypatch.setattr(psutil, "process_iter", lambda: [gone])
        table = helpers.list_instances(instances=True)
        assert "10002" not in table


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCors:
    def test_cors_middleware_is_passed_only_when_configured(self):
        from ansys.mechanical.mcp.server import app, launcher

        with (
            patch.object(asyncio, "run"),
            patch.object(app, "run_http_async", new=MagicMock(return_value=object())) as run,
        ):
            launcher(["--transport", "http"])
            assert "middleware" not in run.call_args.kwargs

            launcher(["--transport", "http", "--cors-origins", "http://a.test, http://b.test"])
            (middleware,) = run.call_args.kwargs["middleware"]

        assert middleware.kwargs["allow_origins"] == ["http://a.test", "http://b.test"]
        assert "mcp-session-id" in middleware.kwargs["expose_headers"]

    def test_cors_preflight_is_answered(self):
        from starlette.applications import Starlette
        from starlette.testclient import TestClient

        from ansys.mechanical.mcp.server import _build_cors_middleware

        web_app = Starlette(middleware=_build_cors_middleware(["http://a.test"]))
        response = TestClient(web_app).options(
            "/mcp",
            headers={"Origin": "http://a.test", "Access-Control-Request-Method": "POST"},
        )
        assert response.headers["access-control-allow-origin"] == "http://a.test"
        denied = TestClient(web_app).options(
            "/mcp",
            headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "POST"},
        )
        assert "access-control-allow-origin" not in denied.headers
