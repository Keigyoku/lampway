#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate for the generated lampway.wezterm.lua (contract 16, tests W1-W4). Needs luajit, not WezTerm.

    python3 check_wezterm.py               # exit 1 on a finding
    python3 check_wezterm.py --self-test   # plants one offender per check

The config is executed under a stub `wezterm` module with LAMPWAY_HOME pointed at a temp dir, then inspected:
W1  both colour schemes equal the tokens (foreground, background, cursor, selection, tab bar), and ANSI never uses `wire`.
W2  calm and private: check_for_updates is false (an update check is a network call nobody opted into), no bell, no blink.
W3  isolation: the file opens nothing but $LAMPWAY_HOME/wezterm/state.json, never names the user's config, refuses to load
    without LAMPWAY_HOME.
W4  the tab title for each agent state carries that state's glyph and token colour (read from a planted state.json).
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(HERE, "lampway.wezterm.lua")
TOKENS = json.load(open(os.path.join(HERE, "tokens.json")))
CUE = {"idle": "muted_dim", "working": "accent_text", "unread": "agent", "blocked": "accent_text", "paused": "muted",
       "done": "go", "failed": "stop"}

HARNESS = r"""
local handlers, out = {}, {}
package.preload['wezterm'] = function()
  return { config_builder = function() return {} end, on = function(n, f) handlers[n] = f end,
           font_with_fallback = function(t) return t end, json_parse = function(s) return JSON_DECODE(s) end,
           format = function(t) return t end }
end
-- a tiny JSON decoder for the planted state file (objects, strings only)
function JSON_DECODE(s)
  local pos = 1
  local function ws() pos = s:find('[^%s]', pos) or #s + 1 end
  local val
  local function str() local e = s:find('"', pos + 1, true); local r = s:sub(pos + 1, e - 1); pos = e + 1; return r end
  local function obj() local t = {}; pos = pos + 1; ws()
    if s:sub(pos, pos) == '}' then pos = pos + 1; return t end
    while true do ws(); local k = str(); ws(); pos = pos + 1; ws(); t[k] = val(); ws()
      local c = s:sub(pos, pos); pos = pos + 1; if c == '}' then return t end end end
  val = function() ws(); local c = s:sub(pos, pos); if c == '{' then return obj() else return str() end end
  return val()
end
local ok, cfg = pcall(dofile, arg[1])
if not ok then print('LOADERR\t' .. tostring(cfg)); return end
local function emit(k, v) print(k .. '\t' .. tostring(v)) end
for name, sc in pairs(cfg.color_schemes) do
  for _, k in ipairs({'foreground', 'background', 'cursor_bg', 'selection_bg'}) do emit(name .. '.' .. k, sc[k]) end
  emit(name .. '.tab_bar.active_tab.bg_color', sc.tab_bar.active_tab.bg_color)
  for i, c in ipairs(sc.ansi) do emit(name .. '.ansi.' .. i, c) end
  for i, c in ipairs(sc.brights) do emit(name .. '.brights.' .. i, c) end
end
emit('check_for_updates', cfg.check_for_updates); emit('audible_bell', cfg.audible_bell); emit('cursor_blink_rate', cfg.cursor_blink_rate)
for _, st in ipairs({'idle', 'working', 'unread', 'blocked', 'paused', 'done', 'failed'}) do
  STATE_NOW = st
end
local f = handlers['format-tab-title']
for pid, st in pairs({['1'] = 'idle', ['2'] = 'working', ['3'] = 'unread', ['4'] = 'blocked', ['5'] = 'paused', ['6'] = 'done', ['7'] = 'failed'}) do
  local r = f({ active_pane = { pane_id = tonumber(pid), title = 't' }, is_active = false })
  emit('tab.' .. st, r[1].Foreground.Color .. ' ' .. r[2].Text)
end
"""


def run(lua_path, with_home=True):
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "wezterm"))
    panes = {str(i): {"state": s, "name": s} for i, s in enumerate(["idle", "working", "unread", "blocked", "paused", "done", "failed"], 1)}
    json.dump({"panes": panes, "egress": {"state": "idle"}}, open(os.path.join(tmp, "wezterm", "state.json"), "w"))
    h = os.path.join(tmp, "harness.lua")
    open(h, "w").write(HARNESS)
    env = {"PATH": os.environ.get("PATH", "/usr/bin"), "HOME": tmp}
    if with_home:
        env["LAMPWAY_HOME"] = tmp
    out = subprocess.run(["luajit", h, lua_path], capture_output=True, text=True, env=env, timeout=30).stdout
    return dict(line.split("\t", 1) for line in out.splitlines() if "\t" in line)


def check(lua_path):
    f = []
    src = re.sub(r"--[^\n]*", "", open(lua_path, encoding="utf-8").read())   # code only: comments may explain the rule
    v = run(lua_path)
    if "LOADERR" in v:
        return [f"W0: the config does not load: {v['LOADERR']}"]
    c = TOKENS["colour"]
    for name, var in (("Lampway Night", "dark"), ("Lampway Paper", "light")):
        for k, tok in (("foreground", "text"), ("background", "canvas"), ("cursor_bg", "accent"), ("selection_bg", "accent_bed_hi"),
                       ("tab_bar.active_tab.bg_color", "surface")):
            got = v.get(f"{name}.{k}", "").upper()
            if got != c[tok][var].upper():
                f.append(f"W1 {name}.{k} = {got}, token {tok} = {c[tok][var]}")
        for i in range(1, 9):
            for kind in ("ansi", "brights"):
                if v.get(f"{name}.{kind}.{i}", "").upper() in (c["wire"]["dark"].upper(), c["wire"]["light"].upper()):
                    f.append(f"W1 {name}.{kind}.{i} uses the reserved wire colour")
    if v.get("check_for_updates") != "false":
        f.append("W2 check_for_updates is not false: WezTerm would call GitHub without an opt-in")
    if v.get("audible_bell") != "Disabled" or v.get("cursor_blink_rate") != "0":
        f.append("W2 bell or blinking cursor is on (calm by default)")
    opens = re.findall(r"io\.open\(([^,)]+)", src)
    if opens != ["STATE_FILE"]:
        f.append(f"W3 the config opens {opens}, only STATE_FILE is allowed")
    if re.search(r"\.wezterm\.lua|\.config/wezterm|WEZTERM_CONFIG", src):
        f.append("W3 the config names the user's own WezTerm configuration")
    if "LOADERR" not in run(lua_path, with_home=False):
        f.append("W3 the config loads without LAMPWAY_HOME (it must refuse)")
    for st, tok in CUE.items():
        got = v.get(f"tab.{st}", "")
        if not got.upper().startswith(c[tok]["dark"].upper()):
            f.append(f"W4 tab title for {st}: {got!r}, want colour {c[tok]['dark']}")
    glyphs = [v.get(f"tab.{st}", "").split(" ", 1)[-1] for st in CUE]
    if len(set(glyphs)) != len(glyphs):
        f.append("W4 two agent states share a tab glyph")
    return f


def self_test():
    assert not check(LUA), "the generated config must be clean before the self-test"
    src = open(LUA, encoding="utf-8").read()
    ok = True
    for label, mut, tag in (
        ("W1 drifted background", src.replace("background = '#0E1016'", "background = '#000000'", 1), "W1"),
        ("W2 update check on", src.replace("config.check_for_updates = false", "config.check_for_updates = true"), "W2"),
        ("W3 reads the user's config", src.replace("local STATE_FILE", "local _u = io.open(os.getenv('HOME') .. '/.wezterm.lua')\nlocal STATE_FILE"), "W3"),
        ("W4 two states share a glyph", src.replace("glyph = '✕'", "glyph = '✓'"), "W4"),
    ):
        p = os.path.join(tempfile.mkdtemp(), "mut.lua")
        open(p, "w", encoding="utf-8").write(mut)
        hit = any(x.startswith(tag) for x in check(p))
        print(("caught  " if hit else "MISSED  ") + label)
        ok &= hit
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    fs = check(LUA)
    for x in fs:
        print(x)
    print(f"check_wezterm: {len(fs)} finding(s)")
    sys.exit(1 if fs else 0)
