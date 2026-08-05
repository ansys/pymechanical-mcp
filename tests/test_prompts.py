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

"""Tests for system prompt selection based on tool visibility mode."""

import pytest


@pytest.mark.unit
def test_build_system_prompt_defaults_to_dynamic_discovery_language():
    """Default prompt should describe connection-aware (dynamic) tool visibility."""
    from ansys.mechanical.mcp.prompts import build_system_prompt

    prompt = build_system_prompt()

    assert "uses connection-aware tool visibility" in prompt
    assert "exposes the full tool surface from startup" not in prompt


@pytest.mark.unit
def test_build_system_prompt_static_tools_language():
    """Static-tools prompt should describe the always-visible tool surface."""
    from ansys.mechanical.mcp.prompts import build_system_prompt

    prompt = build_system_prompt(static_tools=True)

    assert "exposes the full tool surface from startup" in prompt
    assert "--static-tools" in prompt
    assert "No Mechanical connection available" in prompt
    assert "uses connection-aware tool visibility" not in prompt


@pytest.mark.unit
def test_system_prompt_handler_reads_cli_config(monkeypatch):
    """The system_prompt resource should reflect the active --static-tools setting."""
    from ansys.mechanical.mcp import app
    from ansys.mechanical.mcp.prompts import system_prompt

    # No _cli_config set: defaults to dynamic prompt.
    if hasattr(app, "_cli_config"):
        monkeypatch.delattr(app, "_cli_config")
    assert "uses connection-aware tool visibility" in system_prompt()

    # With static_tools True in _cli_config: static prompt.
    monkeypatch.setattr(app, "_cli_config", {"static_tools": True}, raising=False)
    assert "exposes the full tool surface from startup" in system_prompt()
