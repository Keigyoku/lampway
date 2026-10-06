# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 15: the visual harness (inside the build, windowed).

    <build> --factory-startup --enable-event-simulate --window-geometry 0 0 1600 1000 \
            --python driver.py -- <state.py> <out dir> <plant json>

Waits for the deferred UI to finish loading, closes the first-run splash, runs the state's ``setup(bpy)``, applies the
planted theme colours (the harness's own falsifier), lets the window redraw, captures it, and writes ``report.json``:
the capture's file name, each named surface's window point (``surfaces(bpy, dump)`` in the state) and each named
region's window rect (``regions(bpy)``). The host samples the pixels; every timer here is bounded.
"""

import json
import os
import runpy
import sys

import bpy

state_path, out_dir, plant_json = sys.argv[sys.argv.index("--") + 1:][:3]
state = runpy.run_path(state_path)
plant = json.loads(plant_json)
run = {"tick": 0, "phase": "load", "settle": 0}
MAX_TICKS = 240          # 0.25 s each: a minute at most
SETTLE_TICKS = 6


def window():
    return bpy.context.window_manager.windows[0]


def redraw():
    win = window()
    for area in [*win.screen.areas, *win.global_areas]:  # the top and status bars are global areas
        area.tag_redraw()


def apply_plant():
    theme = bpy.context.preferences.themes[0]
    for path, hx in plant.items():
        owner_path, attr = path.rsplit(".", 1)
        owner = theme
        for part in owner_path.split("."):
            owner = getattr(owner, part)
        value = [int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        size = len(getattr(owner, attr))
        setattr(owner, attr, (value + [1.0])[:size])


def finish():
    win = window()
    dump = json.loads(bpy.context.window_manager.mixar_qa_ui_dump)
    capture = "frame.png"
    if not win.mixar_qa_capture_frame(filepath=os.path.join(out_dir, capture), x=0, y=0,
                                      width=win.width, height=win.height):
        raise RuntimeError("capture failed")
    points = state["surfaces"](bpy, dump)
    report = {"state": os.path.splitext(os.path.basename(state_path))[0], "capture": capture,
              "window": [win.width, win.height], "plant": plant,
              "surfaces": {name: {"at": [int(p[0]), int(p[1])], **({"box": int(p[2])} if len(p) > 2 else {})}
                           for name, p in points.items()},
              "regions": state["regions"](bpy),
              "facts": state["facts"](bpy, dump) if "facts" in state else {}}
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)


def quit_now():
    """Quit without the unsaved-changes prompt: a state that edits the screen (an area's type) dirties the file, and the
    prompt would wait forever on a virtual display."""
    bpy.context.preferences.view.use_save_prompt = False
    bpy.ops.wm.quit_blender()


def tick():
    try:
        return _tick()
    except Exception as exc:  # a state that raises must end the run, not stop the timer and leave the window open
        print("VISUAL: failed:", repr(exc))
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(1)


def _tick():
    run["tick"] += 1
    if run["tick"] > MAX_TICKS:
        print("VISUAL: gave up waiting for the UI", run)
        quit_now()
        return None
    boot = sys.modules.get("bootstrap")
    if run["phase"] == "load":
        if boot is not None and not getattr(boot, "_ui_loading_complete", True):
            return 0.25
        win = window()
        with bpy.context.temp_override(window=win):  # the first-run splash covers the middle of the window
            win.event_simulate(type='ESC', value='PRESS')
            win.event_simulate(type='ESC', value='RELEASE')
        run["phase"] = "setup"
        return 0.25
    if run["phase"] == "setup":
        state["setup"](bpy)
        apply_plant()
        run["phase"] = "settle"
    if run["phase"] == "settle":
        redraw()
        run["settle"] += 1
        if run["settle"] < state.get("SETTLE_TICKS", SETTLE_TICKS):
            return 0.25
        try:
            finish()
        except Exception as exc:  # report, then quit: never leave a window open
            print("VISUAL: failed:", repr(exc))
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            os._exit(1)
        quit_now()
        return None
    return 0.25


bpy.app.timers.register(tick, first_interval=1.0)
