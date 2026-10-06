# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""A clean `pip install .` must be able to serve the agent WebSocket.

uvicorn answers a WebSocket upgrade with 404 ("No supported WebSocket library
detected") unless websockets or wsproto is installed. Found live: a fresh venv
built from pyproject served REST but never the agent socket, because websockets
was only in the `test` extra.
"""
import tomllib
from pathlib import Path


def test_runtime_dependencies_include_a_websocket_library():
    meta = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    runtime = " ".join(meta["project"]["dependencies"]).lower()
    assert "websockets" in runtime or "wsproto" in runtime or "uvicorn[standard]" in runtime


def test_the_local_embeddings_extra_carries_the_onnx_runtime():
    """The bundled weights need onnxruntime in the SERVER's environment; without it the Vault reports needs_runtime and stays deterministic."""
    meta = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    extra = " ".join(meta["project"]["optional-dependencies"].get("local-embeddings", [])).lower()
    assert "onnxruntime" in extra and "numpy" in extra
