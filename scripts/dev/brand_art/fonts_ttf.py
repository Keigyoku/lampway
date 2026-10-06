#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IBM Plex Mono as TrueType for the Lampway terminal (facelift contract 16): WezTerm 20240203 cannot read the woff2 the
repository vendors (measured 2026-10-06: a "Configuration Error" pane and a fallback face). This decodes the vendored
woff2 (scripts/dev/brand_art/fonts/) into the TTF the server's add-on installs (server/lampway_server/addons/fonts/), and
copies the OFL text beside it. Generated: never edit the TTFs by hand.

    python3 scripts/dev/brand_art/fonts_ttf.py           # write (needs fontTools with brotli: pip install "fonttools[woff]")
    python3 scripts/dev/brand_art/fonts_ttf.py --check   # exit 1 when a TTF is missing or does not decode from its woff2
"""

import argparse
import hashlib
import io
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "scripts/dev/brand_art/fonts"
OUT = ROOT / "server/lampway_server/addons/fonts"
FACES = {"ibm-plex-mono-latin-400-normal.woff2": "IBMPlexMono-Regular.ttf",
         "ibm-plex-mono-latin-500-normal.woff2": "IBMPlexMono-Medium.ttf"}
LICENSE = "OFL-IBM-Plex-Mono.txt"


def decode(woff2: Path) -> bytes:
    from fontTools.ttLib import TTFont
    font = TTFont(str(woff2), recalcTimestamp=False)   # the head table keeps its date: the output is deterministic
    font.flavor = None
    buf = io.BytesIO()
    font.save(buf, reorderTables=True)
    return buf.getvalue()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    stale = []
    for src, dst in FACES.items():
        data = decode(SRC / src)
        out = OUT / dst
        if a.check:
            if not out.exists() or hashlib.sha256(out.read_bytes()).digest() != hashlib.sha256(data).digest():
                stale.append(dst)
            continue
        OUT.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    if a.check:
        if not (OUT / LICENSE).exists():
            stale.append(LICENSE)
        print("fonts_ttf: " + ("stale: " + ", ".join(stale) if stale else "current"))
        return 1 if stale else 0
    shutil.copyfile(SRC / LICENSE, OUT / LICENSE)
    print(f"fonts_ttf: {len(FACES)} faces -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
