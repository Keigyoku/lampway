"""The Lampway cockpit's session host: a herdr server of Lampway's OWN on its own socket (specs/mrmak/01-workbench-sessions.md, redesigned as the cockpit).

INVARIANTS (the captain's rulings, 2026-10-05):
  1. ISOLATION. Lampway never addresses the fleet's herdr server. Every herdr invocation goes through launcher.run, which sets HOME, XDG_CONFIG_HOME, HERDR_SOCKET_PATH,
     HERDR_CLIENT_SOCKET_PATH and HERDR_CONFIG_PATH under the Lampway root, scrubs every inherited HERDR_* variable, and refuses to run otherwise. Only launcher.py spawns processes.
  2. CONTROLLED DECOUPLING. The herdr server and its agent panes survive Blender crashing, SIGKILL, being closed, an add-on unregister, and the Lampway server restarting or crashing.
     The server is launched detached (a transient systemd user unit when available, else its own session), never as a child that dies with Blender. Nothing here stops a pane or the server
     implicitly: only an explicit user action in the cockpit (with a confirm), or an agent finishing on its own. The one exception is the swarm's own:
     a swarm closes a worker pane IT opened (its record names that swarm and worker) when the task is cancelled, fails or times out
     (agent-modes spec S3, ``Cockpit.end_swarm_pane``), and a unit's next swarm closes the previous runs' worker panes of THAT unit
     whose worker has ended (spec Q13, ``Cockpit.close_ended_workers``); it can never close any other pane, nor a live one.
  3. RECONCILE ON START. The live server is the truth and the session registry is the map. Live pane + record: re-adopt. Live pane, no record: show as "unadopted", never kill it. Record, no
     pane (or the agent process gone): mark ended, keep the transcript for resume, never respawn silently. Server not running: report it and offer start / resume as user actions; never
     auto-relaunch agents without a click. Reconcile is idempotent: a second run changes nothing and never double-spawns.
  4. One reconcile pass at start covers both sessions and paid jobs (jobreceipts.reconcile), so a restart finds everything that was in flight.
"""
