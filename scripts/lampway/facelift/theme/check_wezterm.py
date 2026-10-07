#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate for the generated lampway.wezterm.lua (contract 16, tests W1-W4). Needs luajit, not WezTerm.

    python3 check_wezterm.py               # exit 1 on a finding
    python3 check_wezterm.py --self-test   # plants one offender per check

The config is executed under a stub `wezterm` module with LAMPWAY_HOME pointed at a temp dir, then inspected:
W1  both colour schemes equal the tokens (foreground, background, cursor, selection), and ANSI never uses `wire`.
W2  calm and private: check_for_updates is false (an update check is a network call nobody opted into), no bell, no blink.
W3  isolation: the file opens no file at all, never names the user's config, refuses to load without LAMPWAY_HOME.
W4  a viewport only (the captain, 2026-10-06): the tab bar is off, and nothing renders a tab title or a status from state.
W5  no link handling of its own (the captain's ruling 11): no hyperlink rules, no open-uri handler, no mouse bindings.
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

HARNESS = r"""
local handlers, out = {}, {}
package.preload['wezterm'] = function()
  return { config_builder = function() return {} end, on = function(n, f) handlers[n] = f end,
           font_with_fallback = function(t) return t end, json_parse = function(s) return JSON_DECODE(s) end,
           format = function(t) return t end, default_hyperlink_rules = function() return {} end,
           json_encode = function(t) return '{"path":"' .. t.path .. '"}' end,
           action = setmetatable({}, { __index = function(_, k) return k end }) }
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
  for i, c in ipairs(sc.ansi) do emit(name .. '.ansi.' .. i, c) end
  for i, c in ipairs(sc.brights) do emit(name .. '.brights.' .. i, c) end
end
emit('check_for_updates', cfg.check_for_updates); emit('audible_bell', cfg.audible_bell); emit('cursor_blink_rate', cfg.cursor_blink_rate)
emit('links', tostring(cfg.hyperlink_rules ~= nil or cfg.mouse_bindings ~= nil or handlers['open-uri'] ~= nil))
emit('tab_bar', tostring(cfg.enable_tab_bar))
emit('handlers', (handlers['format-tab-title'] and 'format-tab-title ' or '') .. (handlers['update-status'] and 'update-status' or ''))
"""


def run(lua_path, with_home=True):
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "wezterm"))
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
        for k, tok in (("foreground", "text"), ("background", "canvas"), ("cursor_bg", "accent"), ("selection_bg", "accent_bed_hi")):
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
    if opens:
        f.append(f"W3 the config opens {opens}: it opens no file")
    if v.get("links") != "false":
        f.append("W5 the config handles links itself (hyperlink rules, open-uri or mouse bindings): a viewport handles none")
    if re.search(r"\.wezterm\.lua|\.config/wezterm|WEZTERM_CONFIG", src):
        f.append("W3 the config names the user's own WezTerm configuration")
    if "LOADERR" not in run(lua_path, with_home=False):
        f.append("W3 the config loads without LAMPWAY_HOME (it must refuse)")
    if v.get("tab_bar") != "false" or v.get("handlers"):
        f.append(f"W4 not a viewport: enable_tab_bar = {v.get('tab_bar')}, handlers {v.get('handlers')!r} (no tab bar, no tab title, no status)")
    return f


def self_test():
    assert not check(LUA), "the generated config must be clean before the self-test"
    src = open(LUA, encoding="utf-8").read()
    ok = True
    for label, mut, tag in (
        ("W1 drifted background", src.replace("background = '#0E1016'", "background = '#000000'", 1), "W1"),
        ("W2 update check on", src.replace("config.check_for_updates = false", "config.check_for_updates = true"), "W2"),
        ("W3 reads the user's config", src.replace("return config", "local _u = io.open(os.getenv('HOME') .. '/.wezterm.lua')\nreturn config"), "W3"),
        ("W4 a tab bar again", src.replace("config.enable_tab_bar = false", "config.enable_tab_bar = true"), "W4"),
        ("W4 a tab title from state", src.replace("return config", "wezterm.on('format-tab-title', function(tab) return 'x' end)\nreturn config"), "W4"),
        ("W5 a link handler again", src.replace("return config", "wezterm.on('open-uri', function() return false end)\nreturn config"), "W5"),
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
