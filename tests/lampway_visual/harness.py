# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 15: the visual harness (host side).

A state (``states/<name>.py``) puts the real build's UI in a named condition; ``driver.py`` runs it inside the build,
windowed on a virtual display, captures the window and says where each named surface is; this module samples the
capture, checks each surface against its token (``expect.toml``) and diffs regions against approved goldens.

    LAMPWAY_BIN    the build to run (default build/Dev/bin/mixar)
    LAMPWAY_XVFB   the command that provides a virtual display, e.g.
                   "podman exec --user 1000:1000 -w <repo> <build box> xvfb-run -a -s '-screen 0 1600x1000x24'";
                   without it, ``xvfb-run`` on PATH; without either, the tests skip and say why
    LAMPWAY_VISUAL_APPROVE=1   set by a person approving a golden; CI never sets it

Every run gets its own HOME and XDG dirs under the output directory, so it never touches a real profile.
"""

import datetime
import json
import os
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DRIVER = HERE / "driver.py"
STATES = HERE / "states"
GOLDEN = HERE / "golden"
TOKENS = ROOT / "scripts/lampway/facelift/theme/tokens.json"
WINDOW = (1600, 1000)
NO_DISPLAY = "no virtual display: run inside the build box (or set LAMPWAY_XVFB)"
TOKEN_TOLERANCE = 2       # per channel, out of 255
DIFF_THRESHOLD = 6        # a pixel differs when a channel moves more than this, out of 255
DIFF_TOLERANCE = 0.01     # a region fails when more than this fraction of its pixels differ
PATCH = 5                 # each surface is the median of a PATCH x PATCH square


def lampway_bin():
    return Path(os.environ.get("LAMPWAY_BIN") or ROOT / "build" / "Dev" / "bin" / "mixar")


def display_runner():
    """The command prefix that gives the build a virtual display, or None."""
    if os.environ.get("LAMPWAY_XVFB"):
        return shlex.split(os.environ["LAMPWAY_XVFB"])
    if shutil.which("xvfb-run"):
        return ["xvfb-run", "-a", "-s", f"-screen 0 {WINDOW[0]}x{WINDOW[1]}x24"]
    return None


def require_display():
    if display_runner() is None:
        pytest.skip(NO_DISPLAY)
    if not lampway_bin().exists():
        pytest.skip(f"no Lampway binary at {lampway_bin()} (build it: scripts/lampway/build_linux.sh)")


def expectations(state):
    with open(HERE / "expect.toml", "rb") as fh:
        return tomllib.load(fh)[state]


def run_state(state, out_dir, *, plant=None, timeout=300):
    """Run one state in the build; return its report with every surface sampled."""
    require_display()
    out = Path(out_dir)
    home = out / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {"HOME": home, "XDG_CONFIG_HOME": home / "xdg", "XDG_DATA_HOME": home / "data",
           "XDG_CACHE_HOME": home / "cache", "LAMPWAY_BACKEND_URL": "http://127.0.0.1:9", "LAMPWAY_BRIDGE_PORT": "0",
           "LIBGL_ALWAYS_SOFTWARE": "1", "TMPDIR": os.environ.get("TMPDIR", str(out))}
    cmd = [*display_runner(), "env", *(f"{k}={v}" for k, v in env.items()), str(lampway_bin()),
           "--factory-startup", "--enable-event-simulate", "--window-geometry", "0", "0", *map(str, WINDOW),
           "--python-exit-code", "1", "--python", str(DRIVER), "--",
           str(STATES / f"{state}.py"), str(out), json.dumps(plant or {})]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    (out / "run.log").write_text(done.stdout + done.stderr, encoding="utf-8")
    report_path = out / "report.json"
    if done.returncode != 0 or not report_path.exists():
        raise RuntimeError(f"state {state} did not finish (rc={done.returncode}): {(done.stdout + done.stderr)[-2000:]}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    pixels = _load(out / report["capture"])
    for surface in report["surfaces"].values():
        surface["rgb"] = "#%02x%02x%02x" % _median(pixels, *surface["at"])
    report["expect"] = expectations(state)
    report_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def token_failures(report):
    """One line per surface whose sampled colour is not its token: 'surface: sampled #..., want token #...'."""
    expect = report["expect"]
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))["colour"]
    out = []
    for name, token in expect["surfaces"].items():
        want = tokens[token][expect.get("theme", "dark")].lower()
        got = report["surfaces"][name]["rgb"]
        if max(abs(int(got[i:i + 2], 16) - int(want[i:i + 2], 16)) for i in (1, 3, 5)) > TOKEN_TOLERANCE:
            out.append(f"{name}: sampled {got}, want {token} {want}")
    return out


def _load(path):
    from PIL import Image
    image = Image.open(path).convert("RGB")
    return image


def _median(image, x, y):
    """Median of a PATCH x PATCH square around window point (x, y); window y grows upwards, image rows downwards."""
    row = image.height - 1 - y
    half = PATCH // 2
    values = [image.getpixel((min(max(x + dx, 0), image.width - 1), min(max(row + dy, 0), image.height - 1)))
              for dx in range(-half, half + 1) for dy in range(-half, half + 1)]
    return tuple(sorted(v[c] for v in values)[len(values) // 2] for c in range(3))


def _box(image, rect):
    """A window rect [xmin, ymin, xmax, ymax] (origin bottom-left) as a PIL crop box."""
    xmin, ymin, xmax, ymax = rect
    return (xmin, image.height - ymax, xmax, image.height - ymin)


def region_diff(a_path, b_path, rect):
    """The fraction of the region's pixels whose largest channel delta exceeds DIFF_THRESHOLD."""
    a = _load(a_path).crop(_box(_load(a_path), rect))
    b = _load(b_path).crop(_box(_load(b_path), rect))
    if a.size != b.size:
        return 1.0
    pa, pb = a.getdata(), b.getdata()
    moved = sum(1 for p, q in zip(pa, pb) if max(abs(p[c] - q[c]) for c in range(3)) > DIFF_THRESHOLD)
    return moved / max(1, a.size[0] * a.size[1])


def shift_region(src, dst, rect, dx):
    """Write src with the region's content moved dx pixels to the right (what a misplaced panel looks like)."""
    image = _load(src)
    box = _box(image, rect)
    crop = image.crop(box)
    moved = crop.copy()
    moved.paste(crop.crop((0, 0, crop.width - dx, crop.height)), (dx, 0))
    image.paste(moved, box[:2])
    image.save(dst)


def blank_png(path, width, height):
    from PIL import Image
    Image.new("RGB", (width, height), (0, 0, 0)).save(path)


def golden_failures(state, capture, regions, *, golden_dir=GOLDEN):
    golden = Path(golden_dir) / f"{state}.png"
    if not golden.exists():
        return [f"no approved golden for {state}: capture and approve it"]
    out = []
    for name, rect in regions.items():
        ratio = region_diff(golden, capture, rect)
        if ratio > DIFF_TOLERANCE:
            out.append(f"{state}:{name} differs in {ratio:.1%} of pixels (tolerance {DIFF_TOLERANCE:.0%})")
    return out


def approve(state, capture, *, golden_dir=GOLDEN, who):
    """Make a capture the golden for its state. A person's act: refused unless LAMPWAY_VISUAL_APPROVE=1."""
    if os.environ.get("LAMPWAY_VISUAL_APPROVE") != "1":
        raise PermissionError("approving a golden is a person's act: set LAMPWAY_VISUAL_APPROVE=1 and run it yourself")
    golden_dir = Path(golden_dir)
    golden_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(capture, golden_dir / f"{state}.png")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(golden_dir / "APPROVALS.md", "a", encoding="utf-8") as fh:
        fh.write(f"- {state}: approved by {who}, {stamp}\n")
