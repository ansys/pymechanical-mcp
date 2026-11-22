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

"""Tests for activity tracking and conflicting-operation protection."""

from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
from unittest.mock import MagicMock, patch

from fastmcp import Client
import pytest

from ansys.mechanical.mcp import activity, tools
from ansys.mechanical.mcp.server import PyMechanicalAppContext, app
from ansys.mechanical.mcp.tools import REQUIRES_MECHANICAL_TAG


@pytest.fixture(autouse=True)
def _no_progress_probe(monkeypatch):
    """Keep the experimental JScript probe off unless a test enables it."""
    monkeypatch.delenv(activity.PROGRESS_PROBE_ENV, raising=False)


def _context(mechanical=None):
    """Build a tool context sharing one application context across clients."""
    state = PyMechanicalAppContext(mechanical=mechanical or MagicMock(version="261"))
    first = MagicMock()
    first.request_context.lifespan_context = state
    first.send_notification = MagicMock()
    second = MagicMock()
    second.request_context.lifespan_context = state
    second.send_notification = MagicMock()
    return first, second, state


@pytest.mark.unit
class TestOperationTracker:
    def test_start_refuses_a_second_operation(self):
        tracker = activity.OperationTracker()
        first = tracker.start("run_python_script", "script one", "client-A")
        second = tracker.start("solve_analysis", "analysis 0", "client-B")

        assert first is not None
        assert second is None
        assert tracker.active().operation_id == first.operation_id
        assert tracker.snapshot()["active_operation"]["client_id"] == "client-A"

    def test_finish_records_result_and_releases_the_guard(self):
        tracker = activity.OperationTracker()
        record = tracker.start("save_project", "save", "client-A")

        assert tracker.finish(record.operation_id, "succeeded", "Project saved") is True
        assert tracker.active() is None
        last = tracker.last()
        assert last.state == "succeeded"
        assert last.result == "Project saved"
        assert last.finished_at is not None
        assert tracker.start("save_project") is not None

    def test_history_is_bounded(self):
        tracker = activity.OperationTracker(max_history=2)
        for index in range(4):
            record = tracker.start("run_python_script")
            tracker.finish(record.operation_id, result=str(index))
        results = [entry.result for entry in tracker._history]
        assert results == ["2", "3"]

    def test_finish_ignores_an_unknown_operation(self):
        tracker = activity.OperationTracker()
        record = tracker.start("run_python_script")
        assert tracker.finish("op_other") is False
        assert tracker.is_active(record.operation_id) is True

    def test_records_survive_requesting_client_disconnect(self):
        """Completion is retained even though nobody is waiting for it."""
        tracker = activity.OperationTracker()
        record = tracker.start("run_python_script", client_id="gone-client")
        del record
        tracker.finish(tracker.active().operation_id, "succeeded", "done")

        snapshot = tracker.snapshot()
        assert snapshot["active_operation"] is None
        assert snapshot["last_operation"]["result"] == "done"
        assert snapshot["last_operation"]["client_id"] == "gone-client"


@pytest.mark.unit
class TestConflictingSubmissions:
    def test_second_client_is_rejected_with_operation_identity(self):
        release = threading.Event()
        started = threading.Event()
        mechanical = MagicMock(version="261")

        def blocking_script(script):
            started.set()
            release.wait(timeout=5)
            return "ok"

        mechanical.run_python_script.side_effect = blocking_script
        first_ctx, second_ctx, state = _context(mechanical)

        with ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(tools.run_python_script, first_ctx, script="str(1)")
            started.wait(timeout=5)
            rejected = tools.run_python_script(second_ctx, script="str(2)")
            release.set()
            first_result = running.result(timeout=5)

        assert "Script executed successfully" in first_result
        payload = json.loads(rejected)
        assert payload["error_code"] == "operation_in_progress"
        assert payload["details"]["active_operation"]["kind"] == "run_python_script"
        assert "check_mechanical_status" in payload["details"]["guidance"]
        assert mechanical.run_python_script.call_count == 1
        assert state.operations.last().state == "succeeded"

    def test_read_only_tools_stay_available_during_an_operation(self):
        release = threading.Event()
        started = threading.Event()
        mechanical = MagicMock(version="261")

        def blocking_script(script):
            started.set()
            release.wait(timeout=5)
            return "ok"

        mechanical.run_python_script.side_effect = blocking_script
        mechanical.list_files.return_value = ["model.mechdb"]
        first_ctx, second_ctx, _ = _context(mechanical)

        with ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(tools.run_python_script, first_ctx, script="str(1)")
            started.wait(timeout=5)
            listing = tools.list_files(second_ctx)
            release.set()
            running.result(timeout=5)

        assert "model.mechdb" in listing

    def test_failure_releases_the_guard_and_records_the_error(self):
        mechanical = MagicMock(version="261")
        mechanical.run_python_script.side_effect = RuntimeError("solver exploded")
        first_ctx, second_ctx, state = _context(mechanical)

        result = tools.run_python_script(first_ctx, script="boom")

        assert "Error executing script: solver exploded" in result
        assert state.operations.active() is None
        last = state.operations.last()
        assert last.state == "failed"
        assert "solver exploded" in last.error
        mechanical.run_python_script.side_effect = None
        mechanical.run_python_script.return_value = "ok"
        assert "Script executed" in tools.run_python_script(second_ctx, script="str(1)")


@pytest.mark.unit
class TestStatusActivity:
    def test_idle_status_includes_activity_block(self):
        _, ctx, _ = _context()
        mechanical = ctx.request_context.lifespan_context.mechanical
        mechanical.busy = False
        mechanical.exited = False

        data = json.loads(tools.check_mechanical_status(ctx))

        assert data["activity"]["state"] == "idle"
        assert data["activity"]["active_operation"] is None
        assert "one mutating operation at a time" in data["activity"]["guidance"]
        assert "connection" in data  # existing format preserved

    def test_busy_status_skips_scripted_info_and_names_the_operation(self):
        release = threading.Event()
        started = threading.Event()
        mechanical = MagicMock(version="261")
        mechanical.exited = False
        mechanical.busy = False

        def blocking_script(script):
            started.set()
            release.wait(timeout=5)
            return "ok"

        mechanical.run_python_script.side_effect = blocking_script
        first_ctx, observer_ctx, state = _context(mechanical)

        with ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(tools.run_python_script, first_ctx, script="str(1)")
            started.wait(timeout=5)
            status = json.loads(tools.check_mechanical_status(observer_ctx))
            release.set()
            running.result(timeout=5)

        assert status["activity"]["state"] == "busy"
        assert status["activity"]["source"] == "mcp_operation"
        assert status["activity"]["active_operation"]["kind"] == "run_python_script"
        assert status["detailed_info_skipped"] is True
        assert "do not submit another mutating tool" in status["activity"]["guidance"].lower()
        assert state.operations.active() is None

    def test_unknown_probe_activity_is_not_reported_as_idle(self):
        _, ctx, _ = _context()
        unknown = {
            "enabled": True,
            "state": "unknown",
            "detail": "Progress-bar probe did not answer within 2 s.",
        }
        with patch.object(tools.activity, "probe_progress_bar", return_value=unknown):
            data = json.loads(tools.check_mechanical_status(ctx))

        assert data["activity"]["state"] == "unknown"
        assert data["activity"]["source"] == "mechanical_progress_bar"
        assert "never automatically repeat a mutation" in data["activity"]["guidance"]

    def test_last_operation_result_is_recoverable_after_timeout(self):
        _, ctx, state = _context()
        record = state.operations.start("solve_analysis", "analysis 0", client_id="timed-out")
        state.operations.finish(record.operation_id, "succeeded", "Done")

        data = json.loads(tools.check_mechanical_status(ctx))

        assert data["activity"]["last_operation"]["client_id"] == "timed-out"
        assert data["activity"]["last_operation"]["result"] == "Done"

    def test_disconnected_status_reports_disconnected_activity(self):
        state = PyMechanicalAppContext(mechanical=None)
        ctx = MagicMock()
        ctx.request_context.lifespan_context = state

        data = json.loads(tools.check_mechanical_status(ctx))

        assert data["activity"]["state"] == "disconnected"
        assert data["error_code"] == "not_connected"

    def test_client_busy_is_reported_as_busy(self):
        _, ctx, _ = _context()
        ctx.request_context.lifespan_context.mechanical.busy = True

        data = json.loads(tools.check_mechanical_status(ctx))

        assert data["activity"]["state"] == "busy"
        assert data["activity"]["source"] == "client_busy"


@pytest.mark.unit
class TestProgressProbe:
    def test_probe_is_opt_in(self):
        result = activity.probe_progress_bar(MagicMock(), enabled=None)
        assert result["enabled"] is False
        assert result["state"] == "not_evaluated"

    def test_probe_uses_the_jscript_bridge(self):
        mechanical = MagicMock()
        mechanical.run_python_script.return_value = "True"

        result = activity.probe_progress_bar(mechanical, enabled=True)

        script = mechanical.run_python_script.call_args.args[0]
        assert 'ScriptByName("jscript")' in script
        assert "progressBarIsInUse" in script
        assert result["state"] == "busy"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("False", "idle"), (False, "idle"), ("unsupported", "unsupported"), (None, "unsupported")],
    )
    def test_probe_interpretation(self, raw, expected):
        mechanical = MagicMock()
        mechanical.run_python_script.return_value = raw
        assert activity.probe_progress_bar(mechanical, enabled=True)["state"] == expected

    def test_probe_failure_degrades_to_unsupported(self):
        mechanical = MagicMock()
        mechanical.run_python_script.side_effect = RuntimeError("no jscript bridge")
        result = activity.probe_progress_bar(mechanical, enabled=True)
        assert result["state"] == "unsupported"
        assert "no jscript bridge" in result["detail"]

    def test_probe_timeout_is_unknown_not_idle(self):
        mechanical = MagicMock()

        def slow_script(script):
            time.sleep(0.3)
            return "False"

        mechanical.run_python_script.side_effect = slow_script
        started = time.monotonic()
        result = activity.probe_progress_bar(mechanical, enabled=True, timeout=0.01)
        assert result["state"] == "unknown"
        assert time.monotonic() - started < 0.25


@pytest.mark.unit
class TestBackgroundSolve:
    def test_wait_false_keeps_operation_active(self):
        mechanical = MagicMock(version="261")
        mechanical.run_python_script.return_value = json.dumps({"success": True, "status": "Done"})
        ctx, _, state = _context(mechanical)
        with patch.object(tools.activity, "monitor_background_solve") as monitor:
            result = tools.solve_analysis(ctx, analysis_index=2, wait=False)

        assert "success" in result
        assert state.operations.active() is not None
        assert state.operations.active().background is True
        assert state.operations.active().description == "analysis 2"
        assert monitor.call_args.args[3] == 2

    def test_wait_true_finishes_immediately(self):
        mechanical = MagicMock(version="261")
        mechanical.run_python_script.return_value = json.dumps({"success": True, "status": "Done"})
        ctx, _, state = _context(mechanical)
        with patch.object(tools.activity, "monitor_background_solve") as monitor:
            tools.solve_analysis(ctx, analysis_index=0, wait=True)

        assert state.operations.active() is None
        monitor.assert_not_called()

    def test_monitor_records_completion(self):
        tracker = activity.OperationTracker()
        record = tracker.start("solve_analysis", background=True)
        mechanical = MagicMock()
        mechanical.run_python_script.return_value = "Done"

        activity.monitor_background_solve(
            mechanical,
            tracker,
            record,
            0,
            interval=0.01,
            max_wait=2.0,
            timeout=0.2,
        )

        deadline = time.monotonic() + 2
        while tracker.last() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert tracker.last().state == "succeeded"
        assert tracker.last().result == "Done"


@pytest.fixture(autouse=True)
def _isolated_app_state():
    """Mirror the e2e fixture so protocol tests never open a real connection."""
    app.enable(tags={REQUIRES_MECHANICAL_TAG})
    setattr(app, "_cli_config", {"connect_on_startup": False, "static_tools": False})
    yield
    app.enable(tags={REQUIRES_MECHANICAL_TAG})
    setattr(app, "_cli_config", {"connect_on_startup": False, "static_tools": False})


@pytest.mark.asyncio
async def test_protocol_status_exposes_activity_without_a_connection():
    """MCP clients receive the activity block on the real tools/call surface."""
    async with Client(app) as client:
        result = await client.call_tool("check_mechanical_status", {})

    payload = json.loads(result.data)
    assert payload["activity"]["state"] == "disconnected"
    assert payload["activity"]["last_operation"] is None
