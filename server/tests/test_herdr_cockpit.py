"""The cockpit's session host over a real herdr server of Lampway's own (specs/mrmak/01 as redesigned): create, read, guarded input, and the decoupling invariant: SIGKILL the launching
process group and every agent pane survives with the same pid; a restart reconciles by the live server's truth and never double-spawns or kills."""
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from lampway_server.herdr import launcher as L
from lampway_server.herdr.host import Cockpit, CockpitError

from .herdr_support import fake_cli, fleet_witness, lroot, needs_herdr, wait_for  # noqa: F401

pytestmark = needs_herdr
SERVER_DIR = str(Path(__file__).resolve().parents[1])


def pane_pids(root, pane):
    info = json.loads(L.run(root, ["pane", "process-info", "--pane", pane]))["result"]["process_info"]
    return [p["pid"] for p in info["foreground_processes"]]


def fake_panes(root):
    snap = json.loads(L.run(root, ["api", "snapshot"]))["result"]["snapshot"]
    return snap["panes"]


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_a_session_runs_in_a_pane_is_registered_readable_and_input_is_guarded(lroot, fake_cli, tmp_path):
    c = Cockpit(lroot)
    c.ensure_server()
    rec = c.create_session("command", "Chest fit audit", str(tmp_path), command=fake_cli, task="read the chest fit", by="user")
    assert rec["state"] == "live" and rec["pane_id"] and rec["name"] == "Chest fit audit" and rec["agent"] == "command"
    reg = lroot / "sessions.json"
    assert reg.exists() and oct(reg.stat().st_mode & 0o777) == "0o600" and json.loads(reg.read_text())["sessions"][0]["id"] == rec["id"]
    assert wait_for(lambda: "fake agent ready" in c.read_screen(rec["id"]))
    with pytest.raises(CockpitError, match="agent sends are off for this session"):
        c.send_input(rec["id"], "hi", by="agent")                                         # default off
    c.set_agent_sends(rec["id"], True)
    c.send_input(rec["id"], "hello cockpit", by="agent")
    assert wait_for(lambda: "echo: hello cockpit" in c.read_screen(rec["id"]))
    with pytest.raises(CockpitError, match="You are typing in this session"):
        c.send_input(rec["id"], "x", by="agent", user_typed_at=time.time() - 1.0)
    c.send_input(rec["id"], "from the user", by="user", user_typed_at=time.time())          # the user is never blocked by their own typing
    assert wait_for(lambda: "echo: from the user" in c.read_screen(rec["id"]))


def test_a_shell_session_is_never_typed_into_by_an_agent_and_the_bypass_flag_is_the_users_click_only(lroot, tmp_path):
    c = Cockpit(lroot)
    c.ensure_server()
    sh = c.create_session("shell", "scratch shell", str(tmp_path), by="user")
    c.set_agent_sends(sh["id"], True)
    with pytest.raises(CockpitError, match="shell"):
        c.send_input(sh["id"], "rm -rf /", by="agent")
    with pytest.raises(CockpitError, match="bypass"):
        c.create_session("claude", "xx chest", str(tmp_path), bypass=True, by="agent")
    with pytest.raises(CockpitError, match="folder must be inside"):
        c.create_session("shell", "outside", "/etc", by="user", project_root=str(tmp_path))
    with pytest.raises(CockpitError, match="unknown agent"):
        c.create_session("emacs", "nope", str(tmp_path), by="user")
    with pytest.raises(CockpitError, match="name"):
        c.create_session("shell", "x", str(tmp_path), by="user")                              # 2..100 chars


CHILD = textwrap.dedent('''
    import json, sys, time
    sys.path.insert(0, {server!r})
    from pathlib import Path
    from lampway_server.herdr.host import Cockpit
    c = Cockpit(Path({root!r}))
    c.ensure_server()
    rec = c.create_session("command", "Survivor", {cwd!r}, command={cmd!r}, by="user")
    time.sleep(2)
    import lampway_server.herdr.launcher as L
    info = json.loads(L.run(Path({root!r}), ["pane", "process-info", "--pane", rec["pane_id"]]))["result"]["process_info"]
    print(json.dumps({{"id": rec["id"], "pane": rec["pane_id"], "pids": [p["pid"] for p in info["foreground_processes"]]}}), flush=True)
    time.sleep(300)
''')


def start_blender_stand_in(lroot, fake_cli, tmp_path):
    script = tmp_path / "blender_child.py"
    script.write_text(CHILD.format(server=SERVER_DIR, root=str(lroot), cwd=str(tmp_path), cmd=fake_cli))
    child = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True, start_new_session=True)
    line = child.stdout.readline()
    return child, json.loads(line)


def test_sigkill_of_the_launching_process_group_leaves_the_pane_alive_with_the_same_pid(lroot, fake_cli, tmp_path):
    child, info = start_blender_stand_in(lroot, fake_cli, tmp_path)
    assert info["pids"] and all(alive(p) for p in info["pids"])
    os.killpg(child.pid, signal.SIGKILL)                                                    # Blender (the whole process group) dies
    child.wait(timeout=10)
    time.sleep(1.0)
    assert L.server_status(lroot)["running"]
    assert all(alive(p) for p in info["pids"]) and pane_pids(lroot, info["pane"]) == info["pids"]


def test_restart_reconcile_readopts_the_live_pane_spawns_nothing_and_a_second_run_changes_nothing(lroot, fake_cli, tmp_path):
    child, info = start_blender_stand_in(lroot, fake_cli, tmp_path)
    os.killpg(child.pid, signal.SIGKILL)
    child.wait(timeout=10)
    before = fake_panes(lroot)
    c = Cockpit(lroot)                                                                      # Lampway comes back
    out = c.reconcile()
    assert out["server"] == "running" and out["adopted"] == [info["id"]] and out["ended"] == [] and out["unadopted"] == []
    assert out["new_panes"] == 0 and len(fake_panes(lroot)) == len(before)
    snapshot_registry = (lroot / "sessions.json").read_text()
    again = c.reconcile()
    assert again["adopted"] == [info["id"]] and again["new_panes"] == 0 and len(fake_panes(lroot)) == len(before)
    stable = lambda t: [{k: v for k, v in s.items() if k not in ("updated_at", "last_reconciled_at")} for s in json.loads(t)["sessions"]]
    assert stable((lroot / "sessions.json").read_text()) == stable(snapshot_registry)
    assert pane_pids(lroot, info["pane"]) == info["pids"]
    rec = [s for s in c.list_sessions() if s["id"] == info["id"]][0]
    assert rec["state"] == "live" and rec["adopted"] is True


def test_when_only_the_agent_process_dies_the_record_is_ended_and_nothing_is_respawned(lroot, fake_cli, tmp_path):
    c = Cockpit(lroot)
    c.ensure_server()
    rec = c.create_session("command", "Short lived", str(tmp_path), command=fake_cli, by="user")
    assert wait_for(lambda: pane_pids(lroot, rec["pane_id"]))
    pids = pane_pids(lroot, rec["pane_id"])
    for p in pids:
        os.kill(p, signal.SIGKILL)
    assert wait_for(lambda: not any(alive(p) for p in pids))
    panes_before = len(fake_panes(lroot))
    out = Cockpit(lroot).reconcile()
    assert out["ended"] == [rec["id"]] and out["adopted"] == [] and out["new_panes"] == 0 and len(fake_panes(lroot)) == panes_before
    ended = [s for s in Cockpit(lroot).list_sessions() if s["id"] == rec["id"]][0]
    assert ended["state"] == "ended" and ended["ended_at"] and "no longer running" in ended["end_reason"]
    assert Cockpit(lroot).reconcile()["ended"] == [rec["id"]] and not any(alive(p) for p in pids)         # idempotent, and never respawned


def test_a_pane_lampway_did_not_create_is_unadopted_and_never_touched(lroot, tmp_path):
    c = Cockpit(lroot)
    c.ensure_server()
    L.run(lroot, ["workspace", "create", "--cwd", str(tmp_path), "--label", "someone-elses-pane", "--no-focus"])
    before = fake_panes(lroot)
    out = c.reconcile()
    assert len(out["unadopted"]) == len(before) and out["adopted"] == [] and out["ended"] == []
    after = fake_panes(lroot)
    assert [p["pane_id"] for p in after] == [p["pane_id"] for p in before]
    with pytest.raises(CockpitError, match="not a Lampway session"):
        c.send_input(out["unadopted"][0], "x", by="user")                                  # never type into what Lampway did not create


def test_a_server_that_is_not_running_is_reported_with_user_actions_and_agents_are_not_relaunched(lroot, fake_cli, tmp_path):
    c = Cockpit(lroot)
    c.ensure_server()
    rec = c.create_session("command", "Will be orphaned", str(tmp_path), command=fake_cli, by="user")
    c.stop_server(confirmed=True)                                                           # the user stopped it (explicit, confirmed)
    assert wait_for(lambda: not L.server_status(lroot).get("running"))
    out = Cockpit(lroot).reconcile()
    assert out["server"] == "not_running" and set(out["offered"]) == {"start", "resume"} and out["new_panes"] == 0 and not L.server_status(lroot).get("running")
    rec_now = [s for s in Cockpit(lroot).list_sessions() if s["id"] == rec["id"]][0]
    assert rec_now["state"] == "live"                                                       # unknown, untouched: the live server is the truth and it is down
    c.ensure_server()                                                                       # the user clicked start
    out2 = Cockpit(lroot).reconcile()
    assert out2["ended"] == [rec["id"]] and out2["new_panes"] == 0


def test_closing_a_session_is_an_explicit_confirmed_action_and_blender_exit_does_not_do_it(lroot, fake_cli, tmp_path):
    c = Cockpit(lroot)
    c.ensure_server()
    rec = c.create_session("command", "Keep me", str(tmp_path), command=fake_cli, by="user")
    with pytest.raises(CockpitError, match="explicit user action"):
        c.close_session(rec["id"], confirmed=False)
    c.shutdown()                                                                            # what Blender exit / add-on unregister / Lampway shutdown calls
    assert L.server_status(lroot)["running"] and any(p["pane_id"] == rec["pane_id"] for p in fake_panes(lroot))
    c.close_session(rec["id"], confirmed=True)
    assert not any(p["pane_id"] == rec["pane_id"] for p in fake_panes(lroot))
    assert [s for s in c.list_sessions() if s["id"] == rec["id"]][0]["state"] == "ended"


def test_the_whole_cockpit_run_leaves_the_fleets_server_untouched(lroot, fake_cli, tmp_path):
    before = fleet_witness()
    c = Cockpit(lroot)
    c.ensure_server()
    c.create_session("command", "lampway-fleet-marker-9921", str(tmp_path), command=fake_cli, by="user")
    c.reconcile()
    after = fleet_witness()
    assert after["socket_inode"] == before["socket_inode"] and after["version"] == before["version"] and "lampway-fleet-marker-9921" not in after["raw"]
