"""Local CLI adapters, for the user's PERSONAL use: a provider and an image backend that call the official `codex` and
`claude` binaries he is already logged into on this machine. No token is read, copied or stored: we only start the binaries.
OFF by default (a local setting turns it on). The terms caveat travels with the setting."""

import asyncio
import builtins
import json
import os
import stat
from pathlib import Path

import pytest

from lampway_server.agent import cli_adapters as CLI
from lampway_server.agent.providers import make_provider
from lampway_server.agent.providers.base import Message, ModelRequest, Text, ToolCall, ToolSpec
from lampway_server.config import Settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def fake_bin(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def collect(provider, request):
    async def run():
        return [e async for e in provider.stream(request)]
    return asyncio.run(run())


TOOLS = [ToolSpec("scene_summary", "List the scene.", {"type": "object", "properties": {}})]


def req(text="hi", tools=TOOLS):
    return ModelRequest("You are Lampway.", [Message.user_text(text)], list(tools))


# ---- the gate

def test_it_is_off_by_default_and_the_refusal_carries_the_terms_caveat(tmp_path, monkeypatch):
    monkeypatch.delenv("LAMPWAY_LOCAL_CLI", raising=False)
    assert CLI.enabled(tmp_path) is False
    with pytest.raises(ValueError) as e:
        make_provider(Settings(state_dir=tmp_path, provider="codex_cli"))
    msg = str(e.value)
    assert "LAMPWAY_LOCAL_CLI=1" in msg and "personal" in msg.lower()
    assert "Anthropic does not permit third-party developers" in CLI.TERMS_NOTE
    assert "route requests through Free, Pro, or Max plan credentials" in CLI.TERMS_NOTE


def test_a_local_setting_file_or_the_environment_turns_it_on(tmp_path, monkeypatch):
    monkeypatch.delenv("LAMPWAY_LOCAL_CLI", raising=False)
    (tmp_path / "local_cli.json").write_text(json.dumps({"enabled": True}))
    assert CLI.enabled(tmp_path) is True
    (tmp_path / "local_cli.json").write_text(json.dumps({"enabled": False}))
    assert CLI.enabled(tmp_path) is False
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    assert CLI.enabled(tmp_path) is True
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "yes")
    assert CLI.enabled(tmp_path) is False                          # exactly 1, like the studio guard


def test_enabled_makes_the_providers(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    assert make_provider(Settings(state_dir=tmp_path, provider="codex_cli")).name == "codex_cli"
    assert make_provider(Settings(state_dir=tmp_path, provider="claude_cli")).name == "claude_cli"


# ---- codex exec for text

def test_codex_text_runs_exec_read_only_with_the_prompt_on_stdin_and_reads_the_last_message(tmp_path):
    log = tmp_path / "args.txt"
    codex = fake_bin(tmp_path / "codex", f'echo "$@" > {log}; cat > {tmp_path}/stdin.txt; '
                     'while [ $# -gt 0 ]; do [ "$1" = "-o" ] && { shift; printf "Hello from codex" > "$1"; }; shift; done')
    p = CLI.CodexCLIProvider(binary=str(codex))
    events = collect(p, req("say hi"))
    assert events == [Text("Hello from codex")]
    args = log.read_text().split()
    assert args[0] == "exec" and "--skip-git-repo-check" in args and "--ephemeral" in args
    assert args[args.index("-s") + 1] == "read-only" and args[-1] == "-"
    prompt = (tmp_path / "stdin.txt").read_text()
    assert "You are Lampway." in prompt and "say hi" in prompt and "scene_summary" in prompt     # system, user, and the tool list


def test_a_tool_call_line_becomes_a_tool_call(tmp_path):
    codex = fake_bin(tmp_path / "codex", 'cat > /dev/null; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && { shift; '
                     'printf \'Checking.\\nTOOL_CALL {"name": "scene_summary", "arguments": {}}\' > "$1"; }; shift; done')
    events = collect(CLI.CodexCLIProvider(binary=str(codex)), req())
    assert events[0] == Text("Checking.\n") or events[0] == Text("Checking.")
    call = [e for e in events if isinstance(e, ToolCall)][0]
    assert call.name == "scene_summary" and call.arguments == {} and call.id


def test_an_unknown_tool_name_in_a_tool_call_is_not_forwarded(tmp_path):
    codex = fake_bin(tmp_path / "codex", 'cat > /dev/null; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && { shift; '
                     'printf \'TOOL_CALL {"name": "rm_rf", "arguments": {}}\' > "$1"; }; shift; done')
    events = collect(CLI.CodexCLIProvider(binary=str(codex)), req())
    assert not [e for e in events if isinstance(e, ToolCall)]
    assert any(isinstance(e, Text) and "unknown tool" in e.text for e in events)


def test_tool_results_in_history_are_part_of_the_next_prompt(tmp_path):
    codex = fake_bin(tmp_path / "codex", f'cat > {tmp_path}/stdin.txt; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && {{ shift; printf done > "$1"; }}; shift; done')
    msgs = [Message.user_text("go"),
            Message("assistant", [{"type": "tool_call", "id": "c1", "name": "scene_summary", "arguments": {}}]),
            Message("user", [{"type": "tool_result", "tool_call_id": "c1", "content": "{\"objects\": 3}", "is_error": False}])]
    collect(CLI.CodexCLIProvider(binary=str(codex)), ModelRequest("S", msgs, TOOLS))
    prompt = (tmp_path / "stdin.txt").read_text()
    assert "TOOL_RESULT" in prompt and "{\"objects\": 3}" in prompt


def test_a_failing_cli_is_an_error_with_its_stderr_tail_not_a_hang(tmp_path):
    codex = fake_bin(tmp_path / "codex", 'cat > /dev/null; echo "not logged in" >&2; exit 3')
    with pytest.raises(CLI.CLIError, match="not logged in"):
        collect(CLI.CodexCLIProvider(binary=str(codex)), req())


def test_a_slow_cli_is_killed_at_the_timeout(tmp_path):
    codex = fake_bin(tmp_path / "codex", "sleep 30")
    with pytest.raises(CLI.CLIError, match="timed out"):
        collect(CLI.CodexCLIProvider(binary=str(codex), timeout=1), req())


def test_a_missing_binary_says_so(tmp_path):
    with pytest.raises(CLI.CLIError, match="not found"):
        collect(CLI.CodexCLIProvider(binary=str(tmp_path / "nope")), req())


# ---- claude -p

def test_claude_runs_print_mode_with_no_tools_and_no_session_and_prompt_on_stdin(tmp_path):
    log = tmp_path / "args.txt"
    claude = fake_bin(tmp_path / "claude", f'echo "$@" > {log}; cat > {tmp_path}/stdin.txt; printf "Hi from claude"')
    events = collect(CLI.ClaudeCLIProvider(binary=str(claude)), req("hello"))
    assert events == [Text("Hi from claude")]
    args = log.read_text().split()
    assert args[0] == "-p" and "--no-session-persistence" in args and args[args.index("--output-format") + 1] == "text"
    assert "--tools" in args and "--bare" not in args                  # --bare would skip the login the user uses
    assert "hello" in (tmp_path / "stdin.txt").read_text()


# ---- no token is read

def test_the_adapters_never_open_a_credential_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "auth.json").write_text('{"tokens": "SECRET"}')
    (home / ".claude").mkdir()
    (home / ".claude" / ".credentials.json").write_text('{"claudeAiOauth": "SECRET"}')
    monkeypatch.setenv("HOME", str(home))
    opened = []
    real_open = builtins.open

    def spy(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", spy)
    codex = fake_bin(tmp_path / "codex", 'cat > /dev/null; while [ $# -gt 0 ]; do [ "$1" = "-o" ] && { shift; printf ok > "$1"; }; shift; done')
    claude = fake_bin(tmp_path / "claude", "cat > /dev/null; printf ok")
    collect(CLI.CodexCLIProvider(binary=str(codex)), req())
    collect(CLI.ClaudeCLIProvider(binary=str(claude)), req())
    assert not [p for p in opened if "auth.json" in p or ".credentials" in p]


# ---- codex imagegen

def test_imagegen_copies_the_new_png_untouched_and_writes_a_manifest_without_secrets(tmp_path, monkeypatch):
    home = tmp_path / "codexhome"
    (home / "generated_images").mkdir(parents=True)
    old = home / "generated_images" / "old.png"
    old.write_bytes(b"old")
    os.utime(old, (1, 1))
    ref = tmp_path / "clay.png"
    ref.write_bytes(PNG)
    codex = fake_bin(tmp_path / "codex", f'echo "$@" > {tmp_path}/args.txt; mkdir -p {home}/generated_images/s1; cp {tmp_path}/clay.png {home}/generated_images/s1/exec-1.png; echo done')
    monkeypatch.setenv("CODEX_HOME", str(home))
    out = tmp_path / "out"
    res = CLI.codex_image(str(codex), "paint it flat", [ref], out, name="1")
    assert (out / "1.png").read_bytes() == PNG and res["file"] == str(out / "1.png")
    args = (tmp_path / "args.txt").read_text()
    assert args.startswith("exec --skip-git-repo-check") and "-i " + str(ref) in args and "$imagegen" in args
    manifest = json.loads((out / "1.json").read_text())
    assert manifest["method"] == "codex exec built-in image_gen ($imagegen)" and manifest["raw_sha256"] and manifest["references"]
    assert "token" not in json.dumps(manifest).lower()


def test_imagegen_with_no_new_image_is_an_error_naming_the_log(tmp_path, monkeypatch):
    home = tmp_path / "codexhome"
    (home / "generated_images").mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(home))
    codex = fake_bin(tmp_path / "codex", "echo nothing")
    with pytest.raises(CLI.CLIError, match="no image"):
        CLI.codex_image(str(codex), "p", [], tmp_path / "out", name="1")


def test_claude_is_isolated_from_the_owners_settings_hooks_mcp_and_folder_instructions(tmp_path):
    # a worker must not load ~/.claude settings and hooks, MCP servers or a CLAUDE.md from wherever the server was started
    log, where = tmp_path / "args.txt", tmp_path / "cwd.txt"
    claude = fake_bin(tmp_path / "claude", f"printf '%s\\n' \"$@\" > {log}; pwd > {where}; cat > /dev/null; printf ok")
    collect(CLI.ClaudeCLIProvider(binary=str(claude), workdir=tmp_path / "work"), req())
    args = log.read_text().split("\n")
    assert args[args.index("--setting-sources") + 1] == "" and "--strict-mcp-config" in args
    assert where.read_text().strip() == str(tmp_path / "work" / "claude_cli_cwd")      # an empty directory of its own


def test_the_swarm_can_run_on_the_claude_cli_with_its_own_model(tmp_path, monkeypatch):
    from lampway_server.agent.providers import make_swarm_provider
    env = {"LAMPWAY_STATE_DIR": str(tmp_path), "LAMPWAY_PROVIDER": "chatgpt_plan", "LAMPWAY_SWARM_PROVIDER": "claude_cli",
           "LAMPWAY_CLAUDE_SWARM_MODEL": "claude-sonnet-5-5"}
    monkeypatch.delenv("LAMPWAY_LOCAL_CLI", raising=False)
    with pytest.raises(ValueError, match="off"):                       # still gated by the local-CLI switch and its terms note
        make_swarm_provider(Settings.from_env(env), "worker-1")
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    w = make_swarm_provider(Settings.from_env(env), "worker-1")
    assert isinstance(w, CLI.ClaudeCLIProvider) and w.model == "claude-sonnet-5-5"
