#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Copy the Python half of the tree (src/scripts/mixar and src/scripts/startup) into an INSTALLED build,
# so a Python-only change runs without a compile. The install is what `scripts/unix/build.sh` leaves in
# build/<env>/bin; its 5.2/scripts/mixar is a copy of src/scripts/mixar plus generated files.
#   scripts/lampway/sync_python.sh [--bin-dir build/Dev/bin]
# Generated files that exist only in the install (config/_build_env.py) are never deleted. Test trees are
# not shipped, the same as the build's own install step. Refusals go to stdout and exit 1; an unknown flag exits 2.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN="$ROOT/build/${MIXAR_ENV:-Dev}/bin"
while [ $# -gt 0 ]; do
  case "$1" in
    --bin-dir) BIN="${2:?--bin-dir needs a path}"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done
DST="$BIN/5.2/scripts"
if [ ! -d "$DST/mixar" ]; then
  echo "error: $BIN is not an installed build (no 5.2/scripts/mixar)"
  echo "help[1]:"; echo "  - Run \`scripts/lampway/build_linux.sh\` first"
  exit 1
fi
EX=(--exclude=__pycache__ --exclude=tests --exclude=testing --exclude=_build_env.py)
rsync -a --delete "${EX[@]}" "$ROOT/src/scripts/mixar/" "$DST/mixar/"
if [ -d "$ROOT/src/scripts/startup/bootstrap" ]; then
  mkdir -p "$DST/startup/bootstrap"
  rsync -a --exclude=__pycache__ "$ROOT/src/scripts/startup/bootstrap/" "$DST/startup/bootstrap/"
fi
echo "synced: $DST"
