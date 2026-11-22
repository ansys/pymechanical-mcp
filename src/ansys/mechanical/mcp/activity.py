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

"""Activity tracking and conflicting-operation protection.

PyMechanical's ``busy`` flag is client-side state: it only covers the RPCs that
the local ``Mechanical`` object is currently making. It cannot see work started
in the Mechanical GUI, nor a solve that keeps running after ``Solve(False)``
has returned. This module adds a server-side record of the operations that MCP
tools submit, plus an optional, bounded probe of Mechanical's own progress
bar through the JScript bridge.

Design rules:

- At most one mutating MCP operation is active at a time. The registry lives on
  the shared application context, so the rule applies across MCP clients.
- A completed operation is kept in a bounded history even when the requesting
  client times out or disconnects, so its identity and result can be recovered.
- An activity probe that cannot answer in time reports ``unknown``, never
  ``idle``. No code path automatically repeats a mutation after an uncertain
  outcome.
- The progress-bar probe is opt-in (``PYMECHANICAL_MCP_PROGRESS_PROBE=1``)
  until it has been validated on the supported releases and launch modes.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import queue
import threading
import time
from typing import Any, Callable, Literal
import uuid

#: Environment variable that enables the experimental JScript progress probe.
PROGRESS_PROBE_ENV = "PYMECHANICAL_MCP_PROGRESS_PROBE"

#: Default upper bound for a single activity probe, in seconds.
PROGRESS_PROBE_TIMEOUT = 2.0

#: Number of completed operations retained for client recovery.
MAX_OPERATION_HISTORY = 20

#: Maximum length of a result or error echoed in status output.
MAX_RESULT_CHARS = 500

#: States reported for the overall Mechanical activity.
ActivityState = Literal["idle", "busy", "unknown", "disconnected"]

#: States reported for the optional progress-bar probe.
ProgressState = Literal["not_evaluated", "idle", "busy", "unsupported", "unknown"]

#: States of a tracked operation.
OperationState = Literal["active", "succeeded", "failed", "cancelled", "unknown"]

# JScript bridge, mirroring the pattern PyMechanical uses for product info.
# A non-function progressBarIsInUse() is reported as 'unsupported' rather than
# raising, so headless or older releases keep working.
_PROGRESS_PROBE_SCRIPT = (
    'ExtAPI.Application.ScriptByName("jscript").ExecuteCommand('
    "\"var r = (typeof DS.Script.progressBarIsInUse === 'function') ? "
    "DS.Script.progressBarIsInUse() : 'unsupported'; returnFromScript(r);\")"
)

# Solution states that mean the solver is no longer running.
_SOLVE_FINAL_STATES = frozenset(
    {"Done", "PostProcessingRequired", "Failed", "Stopped", "Cancelled", "Canceled"}
)


def progress_probe_enabled() -> bool:
    """Return whether the experimental progress-bar probe was enabled."""
    return os.environ.get(PROGRESS_PROBE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _utc_timestamp(monotonic_hint: float | None = None) -> str:
    """Return an ISO-8601 UTC timestamp for a monotonic time value."""
    del monotonic_hint  # kept for API symmetry; wall clock is used for display only
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _shorten(value: Any) -> str | None:
    """Return a bounded, ASCII-safe string representation of *value*."""
    if value is None:
        return None
    text = str(value)
    if len(text) > MAX_RESULT_CHARS:
        return text[:MAX_RESULT_CHARS] + "...(truncated)"
    return text


@dataclass
class OperationRecord:
    """Identity and outcome of one MCP-submitted Mechanical operation."""

    operation_id: str
    kind: str
    description: str
    client_id: str | None
    started: float
    started_at: str
    state: OperationState = "active"
    result: str | None = None
    error: str | None = None
    finished: float | None = None
    finished_at: str | None = None
    background: bool = False

    def to_dict(self, now: float | None = None) -> dict[str, Any]:
        """Return a JSON-serializable summary, including elapsed time."""
        reference = time.monotonic() if now is None else now
        end = self.finished if self.finished is not None else reference
        return {
            "operation_id": self.operation_id,
            "kind": self.kind,
            "description": self.description,
            "state": self.state,
            "client_id": self.client_id,
            "started_at": self.started_at,
            "elapsed_seconds": round(max(0.0, end - self.started), 2),
            "finished_at": self.finished_at,
            "background": self.background,
            "result": _shorten(self.result),
            "error": _shorten(self.error),
        }


class OperationTracker:
    """Thread-safe registry of the active and most recent MCP operations.

    The tracker is stored on the shared application context, so every MCP
    client sees the same active operation. ``start()`` refuses a second
    mutation while one is active; ``finish()`` always records the outcome,
    including when the original request was cancelled or timed out.
    """

    def __init__(self, max_history: int = MAX_OPERATION_HISTORY) -> None:
        """Initialize an empty tracker with a bounded result history."""
        self._lock = threading.RLock()
        self._active: OperationRecord | None = None
        self._history: deque[OperationRecord] = deque(maxlen=max_history)

    def start(
        self,
        kind: str,
        description: str | None = None,
        client_id: str | None = None,
        background: bool = False,
    ) -> OperationRecord | None:
        """Register a new operation, or return ``None`` if one is already active."""
        with self._lock:
            if self._active is not None:
                return None
            now = time.monotonic()
            record = OperationRecord(
                operation_id="op_" + uuid.uuid4().hex[:12],
                kind=kind,
                description=description or kind,
                client_id=client_id,
                started=now,
                started_at=_utc_timestamp(),
                background=background,
            )
            self._active = record
            return record

    def finish(
        self,
        operation_id: str,
        state: OperationState = "succeeded",
        result: Any = None,
        error: Any = None,
    ) -> bool:
        """Record the outcome of an active operation and release the guard."""
        with self._lock:
            record = self._active
            if record is None or record.operation_id != operation_id:
                return False
            now = time.monotonic()
            record.state = state
            record.result = _shorten(result)
            record.error = _shorten(error)
            record.finished = now
            record.finished_at = _utc_timestamp()
            self._history.append(record)
            self._active = None
            return True

    def is_active(self, operation_id: str) -> bool:
        """Return whether *operation_id* is still the active operation."""
        with self._lock:
            return self._active is not None and self._active.operation_id == operation_id

    def active(self) -> OperationRecord | None:
        """Return the active operation, if any."""
        with self._lock:
            return self._active

    def last(self) -> OperationRecord | None:
        """Return the most recently completed operation, if any."""
        with self._lock:
            return self._history[-1] if self._history else None

    def snapshot(self) -> dict[str, Any]:
        """Return the active and last operation for status reporting."""
        with self._lock:
            now = time.monotonic()
            return {
                "active_operation": self._active.to_dict(now) if self._active else None,
                "last_operation": self._history[-1].to_dict(now) if self._history else None,
            }

    def clear(self) -> None:
        """Forget all records (used when a session is dropped or reset)."""
        with self._lock:
            self._active = None
            self._history.clear()


def call_with_timeout(
    function: Callable[[], Any], timeout: float, name: str = "probe"
) -> tuple[str, Any]:
    """Run *function* on a daemon thread and bound the caller's wait.

    Returns ``("result", value)``, ``("error", exception)``, or
    ``("timeout", None)``. A timed-out thread keeps running but can never make
    the caller treat an uncertain answer as idle.
    """
    results: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def runner() -> None:
        try:
            results.put(("result", function()))
        except BaseException as exc:  # noqa: BLE001 - reported to the caller
            try:
                results.put(("error", exc))
            except queue.Full:
                pass

    threading.Thread(target=runner, name=f"mcp-{name}", daemon=True).start()
    try:
        return results.get(timeout=max(0.01, timeout))
    except queue.Empty:
        return "timeout", None


def _interpret_progress_result(raw: Any) -> ProgressState:
    """Map a JScript bridge result to a progress state."""
    if isinstance(raw, bool):
        return "busy" if raw else "idle"
    if raw is None:
        return "unsupported"
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes"}:
        return "busy"
    if text in {"false", "0", "no"}:
        return "idle"
    return "unsupported"


def probe_progress_bar(
    mechanical: Any,
    *,
    enabled: bool | None = None,
    timeout: float = PROGRESS_PROBE_TIMEOUT,
) -> dict[str, Any]:
    """Probe Mechanical's progress bar through the JScript bridge.

    The probe is opt-in and strictly bounded. Any exception, unsupported API,
    or timeout is reported without raising, so headless sessions and releases
    without the progress API keep working.
    """
    use_probe = progress_probe_enabled() if enabled is None else enabled
    if not use_probe:
        return {
            "enabled": False,
            "state": "not_evaluated",
            "detail": (
                f"Set {PROGRESS_PROBE_ENV}=1 to enable the experimental "
                "DS.Script.progressBarIsInUse() probe."
            ),
        }

    kind, value = call_with_timeout(
        lambda: mechanical.run_python_script(_PROGRESS_PROBE_SCRIPT),
        timeout,
        name="progress-probe",
    )
    if kind == "timeout":
        state: ProgressState = "unknown"
        detail = f"Progress-bar probe did not answer within {timeout} s."
    elif kind == "error":
        state = "unsupported"
        detail = f"Progress-bar probe unavailable: {_shorten(value)}"
    else:
        state = _interpret_progress_result(value)
        detail = {
            "busy": "Mechanical reports an active progress bar.",
            "idle": "Mechanical reports no active progress bar.",
            "unsupported": "DS.Script.progressBarIsInUse() is not available in this release.",
        }[state]
    return {"enabled": True, "state": state, "detail": detail}


def solve_status_script(analysis_index: int) -> str:
    """Return the Mechanical script that reads one analysis's solution status."""
    return f"str(Model.Analyses[{analysis_index}].Solution.Status)"


def monitor_background_solve(
    mechanical: Any,
    tracker: OperationTracker,
    record: OperationRecord,
    analysis_index: int,
    *,
    interval: float = 2.0,
    max_wait: float = 3600.0,
    timeout: float = 5.0,
) -> None:
    """Finish a ``wait=False`` solve record once the solver stops.

    The monitor runs on a daemon thread so the result is retained even if the
    requesting client disconnects. If completion cannot be confirmed, the
    record is finished as ``unknown``: it is never retried automatically.
    """

    def runner() -> None:
        deadline = time.monotonic() + max_wait

        def read() -> Any:
            return mechanical.run_python_script(solve_status_script(analysis_index))

        while tracker.is_active(record.operation_id) and time.monotonic() < deadline:
            time.sleep(interval)
            kind, value = call_with_timeout(read, timeout, name="solve-monitor")
            if kind != "result":
                continue
            status = str(value).strip()
            if status in _SOLVE_FINAL_STATES:
                state: OperationState = (
                    "succeeded" if status in {"Done", "PostProcessingRequired"} else "failed"
                )
                tracker.finish(record.operation_id, state=state, result=status)
                return
        if tracker.is_active(record.operation_id):
            tracker.finish(
                record.operation_id,
                state="unknown",
                result="Solve completion could not be confirmed within the monitoring window.",
            )

    threading.Thread(target=runner, name="mcp-solve-monitor", daemon=True).start()
