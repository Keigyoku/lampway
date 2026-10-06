# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/editor_runner.py, sha256 a6005f707ad7), on 2026-10-06. The UE editor seam (the UE leg is on hold: its recipe tests are needs_box).
"""One batch editor execution seam for the operator tools (stdlib only).

The receipt describes execution, never a domain verdict. Callers must inspect the
fresh result and real imported/converted/rendered artifacts. Work files survive
failures. A ticking script owns its callback and must quit the editor itself.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile


@dataclass(frozen=True)
class EditorRun:
    returncode: int
    stdout: str
    result_path: str
    work: str
    receipt_path: str
    script_path: str
    config_path: str
    script_sha256: str


def run_editor(script, cfg, *, engine, project, runner="", ticking=False,
               args=None, logname="lampway-editor.log", work_root=None, timeout=7200):
    """Run script text with CFG/OUT paths and a preserved argument vector.

    cfg is JSON data; args defaults to [CFG, OUT] for existing animation jobs.
    runner is an argv list or a shell-quoted prefix (parsed, never shell-run).
    The exact spawned process is reaped on timeout. For a remote runner its
    editor's cleanup is unproven and the error receipt says so explicitly.
    """
    if not isinstance(script, str) or not script.strip():
        raise ValueError("editor script must be nonempty text")
    if not isinstance(cfg, dict):
        raise ValueError("editor configuration must be a JSON object")
    config_text = json.dumps(cfg, sort_keys=True, indent=1, allow_nan=False)
    project = str(Path(project).resolve())
    if not Path(project).is_file():
        raise ValueError("editor project does not exist: " + project)
    if not isinstance(timeout, (float, int)) or timeout <= 0:
        raise ValueError("editor timeout must be positive")
    prefix = shlex.split(runner) if isinstance(runner, str) else list(runner or [])
    if any(not isinstance(arg, str) or "\0" in arg for arg in prefix):
        raise ValueError("editor runner must contain string arguments without NUL")
    if args is not None and (not isinstance(args, (list, tuple)) or
                            any(not isinstance(arg, str) or "\0" in arg for arg in args)):
        raise ValueError("editor arguments must be a list of strings without NUL")
    if work_root:
        Path(work_root).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="lampway-editor-", dir=work_root))
    config_path, result_path = work / "cfg.json", work / "result.json"
    script_path, stdout_path = work / "script.py", work / "editor.stdout"
    receipt_path = work / "run.json"
    config_path.write_text(config_text, encoding="utf-8")
    script_args = list(args) if args is not None else [str(config_path), str(result_path)]
    bootstrap = "import sys\nCFG = %r\nOUT = %r\nsys.argv = %r\n" % (
        str(config_path), str(result_path), [str(script_path)] + script_args)
    script_path.write_text(bootstrap + script, encoding="utf-8")
    executable = str(Path(engine).resolve() / "Engine/Binaries/Linux/UnrealEditor-Cmd")
    # UE's Python parser accepts an unquoted pathname through its .py suffix,
    # including spaces (PythonScriptPlugin.cpp:816ff). An embedded double quote
    # here truncates FParse's ExecCmds value to 'py '; subprocess already carries
    # the entire flag as ONE argv element. Job values never travel in this text.
    launch = "-ExecCmds=py " + str(script_path) if ticking else "-ExecutePythonScript=" + str(script_path)
    cmd = prefix + [executable, project, "-RenderOffscreen", "-unattended", "-nopause",
                    "-nosplash", "-NoSound", "-stdout", "-FullStdOutLogOutput",
                    "-NoLoadStartupPackages", "-notrace", "-log=" + logname, launch]
    script_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()
    receipt = {"argv": cmd, "ticking": ticking, "script_sha256": script_hash,
               "config_sha256": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
               "script_path": str(script_path), "config_path": str(config_path),
               "stdout_path": str(stdout_path), "result_path": str(result_path),
               "status": "starting", "returncode": None, "pid": None}

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    save()
    try:
        # Never PIPE: a forked UnrealTraceServer can retain it beyond editor exit.
        with stdout_path.open("wb") as log:
            process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            receipt.update(pid=process.pid, status="running")
            save()
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()  # only the exact process this invocation spawned
                process.wait()
                receipt.update(status="timeout", returncode=process.returncode,
                               cleanup="runner reaped; remote editor UNPROVEN" if prefix else "spawned editor reaped")
                save()
                raise RuntimeError("editor timeout; execution receipt: " + str(receipt_path)) from None
    except OSError as exc:
        receipt.update(status="launch-error", error=str(exc))
        save()
        raise RuntimeError("editor launch failed; execution receipt: " + str(receipt_path)) from None
    receipt.update(status="exited", returncode=code)
    save()
    return EditorRun(code, stdout_path.read_text(encoding="utf-8", errors="replace"),
                     str(result_path), str(work), str(receipt_path), str(script_path),
                     str(config_path), script_hash)
