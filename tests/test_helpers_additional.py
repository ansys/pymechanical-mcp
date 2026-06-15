# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0

"""Additional unit tests for helper and startup modules."""

import json
import runpy
import sys
from types import ModuleType
from unittest.mock import MagicMock

import psutil

from ansys.mechanical.mcp import helpers


class _Proc:
    def __init__(self, name, status, pid, cmdline, cwd="C:/work", children_count=0, cwd_raises=False):
        self._name = name
        self._status = status
        self.pid = pid
        self._cmdline = cmdline
        self._cwd = cwd
        self._children_count = children_count
        self._cwd_raises = cwd_raises

    def cmdline(self):
        return self._cmdline

    def status(self):
        return self._status

    def name(self):
        return self._name

    def children(self, recursive=True):
        return [object()] * self._children_count

    def cwd(self):
        if self._cwd_raises:
            raise psutil.AccessDenied(pid=self.pid)
        return self._cwd


def test_probe_grpc_endpoint_unreachable(monkeypatch):
    def _raise(*args, **kwargs):
        raise OSError("unreachable")

    monkeypatch.setattr(helpers.socket, "create_connection", _raise)

    result = helpers._probe_grpc_endpoint("127.0.0.1", 60000)

    assert result["reachable"] is False
    assert "unreachable" in result["error"]


def test_list_instances_variants(monkeypatch):
    import psutil

    running = _Proc(
        name="AnsysWBU.exe",
        status=psutil.STATUS_RUNNING,
        pid=101,
        cmdline=["AnsysWBU.exe", "--port", "10000", "-grpc"],
        children_count=3,
    )
    sleeping = _Proc(
        name="mechanical",
        status=psutil.STATUS_SLEEPING,
        pid=102,
        cmdline=["mechanical", "--foo"],
        cwd_raises=True,
    )
    other = _Proc(
        name="python",
        status=psutil.STATUS_RUNNING,
        pid=103,
        cmdline=["python", "script.py"],
    )

    monkeypatch.setattr(psutil, "process_iter", lambda: [running, sleeping, other])

    table_all = helpers.list_instances(instances=False, cmd=True, location=True)
    assert "AnsysWBU.exe" in table_all
    assert "10000" in table_all
    assert "N/A" in table_all

    table_instances_only = helpers.list_instances(instances=True)
    assert "AnsysWBU.exe" in table_instances_only
    assert "mechanical" not in table_instances_only


def test_get_info_success():
    mechanical = MagicMock()
    mechanical.version = "252"
    mechanical.project_directory = "C:/project"
    mechanical.is_alive = True
    mechanical.name = "Mech"
    mechanical.busy = False
    mechanical.exited = False
    mechanical.get_product_info.return_value = {"product": "Mechanical"}
    mechanical.run_python_script.return_value = json.dumps(
        {"product_version": "252", "model_name": "Model"}
    )

    info = helpers.get_info(mechanical)

    assert info["connection"]["version"] == "252"
    assert info["product_info"]["raw"]["product"] == "Mechanical"
    assert info["model"]["model_name"] == "Model"


class _BrokenMechanical:
    @property
    def version(self):
        raise RuntimeError("version unavailable")

    def get_product_info(self):
        raise RuntimeError("product info unavailable")

    def run_python_script(self, script):
        raise RuntimeError("script failed")


def test_get_info_error_paths():
    info = helpers.get_info(_BrokenMechanical())

    assert "error" in info["connection"]
    assert "error" in info["product_info"]
    assert "error" in info["model"]


def test_startup_code_error_paths(monkeypatch):
    from ansys.mechanical.mcp.mechanical_helper import startup_code

    monkeypatch.setattr(startup_code, "MATPLOTLIB_AVAILABLE", False)
    assert startup_code.save_matplotlib_plot() == "Error: matplotlib is not available"

    monkeypatch.setattr(startup_code, "PYVISTA_AVAILABLE", False)
    assert startup_code.save_plot(MagicMock()) == "Error: PyVista is not available"


def test_module_entrypoint_invokes_launcher(monkeypatch):
    fake_server = ModuleType("ansys.mechanical.mcp.server")
    launcher = MagicMock()
    fake_server.launcher = launcher

    monkeypatch.setitem(sys.modules, "ansys.mechanical.mcp.server", fake_server)
    runpy.run_module("ansys.mechanical.mcp.__main__", run_name="__main__")

    launcher.assert_called_once()
