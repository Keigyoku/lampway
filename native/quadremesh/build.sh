#!/bin/bash
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build lampway-quadremesh. The MIT-licensed AutoRemesher source is fetched at a pinned commit into --src (default: next to the build dir) and is never copied into this
# repository. Usage: build.sh [--src <autoremesher checkout>] [--build <dir>]   (run it where cmake and a C++17 compiler are: the build container)
set -euo pipefail
PIN=3cb2012c97d0623507483a84eb4cec054daa137a
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC=""; BUILD="$HERE/../../build/quadremesh"
while [ $# -gt 0 ]; do case "$1" in --src) SRC="$2"; shift 2;; --build) BUILD="$2"; shift 2;; *) echo "unknown argument $1" >&2; exit 2;; esac; done
if [ -z "$SRC" ]; then SRC="$BUILD/autoremesher-src"; fi
if [ ! -d "$SRC/src/AutoRemesher" ]; then
  git clone https://github.com/huxingyi/autoremesher "$SRC"
  git -C "$SRC" checkout "$PIN"
fi
cmake -S "$HERE" -B "$BUILD" -G Ninja -DAR_SOURCE="$SRC" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" --target lampway-quadremesh -j"${BUILD_CORES:-4}"
echo "built: $BUILD/lampway-quadremesh"
