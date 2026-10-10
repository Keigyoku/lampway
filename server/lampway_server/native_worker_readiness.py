# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only native startup qualification, separate from descriptive harness adapters."""
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from . import hermes_worker as H
from .herdr import launcher as L

GROK_REFUSAL = ("Grok workers require the qualified Linux Grok 1.0.46 native boundary, an ordinary bubblewrap executable, "
                "unused native policy slots, usable unprivileged namespaces and the exact installed lampway_pane MCP "
                "connector. Unsupported native startup is refused; account-backed execution remains unverified.")

HERMES_REFUSAL = ("Your Hermes connector-only worker policy needs its supported native Python startup and gateway MCP guard. "
                  "Select Hermes 0.21.5 (2026.9.24) with its normal interpreter and local gateway, and install "
                  "Lampway's lampway-pane-mcp helper alongside the server interpreter; unsupported startup is refused.")

_CONSOLE_SCRIPTS = (
    '''import sys
from hermes_cli.main import main
if __name__ == "__main__":
    if sys.argv[0].endswith("-script.pyw"):
        sys.argv[0] = sys.argv[0][:-11]
    elif sys.argv[0].endswith(".exe"):
        sys.argv[0] = sys.argv[0][:-4]
    sys.exit(main())
''',
    '''import re
import sys
from hermes_cli.main import main
if __name__ == "__main__":
    sys.argv[0] = re.sub(r"(-script\\.pyw|\\.exe)?$", "", sys.argv[0])
    sys.exit(main())
''',
    '''import sys
from hermes_cli.main import main
if __name__ == "__main__":
    sys.exit(main())
''',
)


def console_interpreter(binary) -> str:
    """Only known Python console entry templates; custom wrappers need separate qualification."""
    path = Path(binary)
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("unsupported native Hermes entry")
    with path.open("rb") as stream:
        source = stream.read(16385)
    if len(source) > 16384:
        raise ValueError("unsupported native Hermes entry size")
    text = source.decode("utf8")
    first = text.splitlines()[0]
    python = first[2:].strip() if first.startswith("#!") else ""
    if not os.path.isabs(python) or any(char.isspace() for char in python):
        raise ValueError("Hermes worker needs a normal absolute Python console shebang")
    try:
        tree = ast.dump(ast.parse(text), include_attributes=False)
    except SyntaxError as exc:
        raise ValueError("unsupported native Hermes console script") from exc
    if tree not in {ast.dump(ast.parse(value), include_attributes=False) for value in _CONSOLE_SCRIPTS}:
        raise ValueError("custom native Hermes entry is not qualified")
    return python


def pane_helper() -> str:
    """Only the console entry installed with this server, never a request or PATH substitute."""
    path = Path(sys.executable).with_name("lampway-pane-mcp")
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK)
            or info.st_mode & (stat.S_ISUID | stat.S_ISGID)):
        raise ValueError("Lampway's installed pane helper must be an ordinary executable")
    return str(path)


def _valid_receipt(value, entry) -> bool:
    if not isinstance(value, dict):
        return False
    expected_admissions = sorted(f"{name}.{klass}.{method}"
        for name, (klass, methods) in H._LIFECYCLES.items() for method in methods)
    digest = hashlib.sha256(Path(H.__file__).read_bytes()).hexdigest()
    package = value.get("native_package")
    root = value.get("gateway_source_root")
    python = value.get("python")
    return (type(value.get("schema")) is int and value["schema"] == 1
        and value.get("guard") == "installed" and value.get("entry") == entry
        and value.get("native_version") == list(H.SUPPORTED_NATIVE)
        and value.get("guard_sha256") == digest
        and value.get("loader") == "tools.mcp_tool_config._load_mcp_config"
        and sorted(value.get("admissions", [])) == expected_admissions
        and value.get("gateway_handoff") == "hermes_cli.main_tui_launch._apply_tui_python_env"
        and value.get("source_root_hook_shadow") is False
        and isinstance(package, str) and os.path.isabs(package)
        and isinstance(root, str) and os.path.isabs(root) and str(Path(package).parent.parent) == root
        and isinstance(python, str) and os.path.isabs(python) and value.get("gateway_python") == python)


def hermes_worker_note(binary) -> str:
    """Probe exits from owned sitecustomize before CLI main, provider discovery, login or frontend."""
    if not binary:
        return HERMES_REFUSAL
    try:
        helper = pane_helper()
        python = console_interpreter(binary)
        # Readiness has no worker bearer and creates no pane or persistent native configuration.
        with tempfile.TemporaryDirectory(prefix="lampway-hermes-worker-probe-",
                dir=os.environ.get("TMPDIR") or "/tmp") as temporary:
            root = Path(temporary)
            hook = root / "startup"
            hook.mkdir(mode=0o700)
            source = hook / "sitecustomize.py"
            source.write_text(H.startup_source())
            source.chmod(0o600)
            entry = H.canonical_entry(helper, str(root / "panes" / "probe" / "mcp.json"), str(root))
            previous = os.environ.get("PYTHONPATH")
            env = {"PYTHONPATH": str(hook) + (os.pathsep + previous if previous is not None else ""),
                   H.POLICY_ENV: json.dumps(entry, separators=(",", ":")), H.PROBE_ENV: "1"}
            code, output = L.worker_probe([str(binary), "--version"], env)
            value = json.loads(output)
            if code != 0 or not _valid_receipt(value, entry) or value["python"] != python:
                return HERMES_REFUSAL
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return HERMES_REFUSAL
    return ""


def grok_worker_description(binary, *, cwd=None) -> dict:
    """Native read-only identity query and no-op namespace qualification, before any pane files."""
    from . import grok_worker as G
    paths = G.candidate_paths(binary)
    native, bwrap, connector = (paths[key] for key in ('native', 'bwrap', 'connector'))
    project = str(Path(cwd or os.getcwd()).resolve())
    code, listing = L.worker_probe([str(native), "mcp", "list", "--json"], {}, cwd=project)
    if code != 0:
        raise ValueError(GROK_REFUSAL)
    description = G.preflight(native, bwrap, connector, listing)
    code, _ = L.worker_probe(description.pop("namespace_probe"), {})
    if code != 0:
        raise ValueError(GROK_REFUSAL)
    return description


def grok_worker_note(binary) -> str:
    try:
        grok_worker_description(binary)
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return GROK_REFUSAL
    return ""
