#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# First argument selects the build environment folder (defaults to Dev).
BUILD_ENV="${1:-Dev}"

BUILD_BIN="$ROOT_DIR/build/$BUILD_ENV/bin"
if [[ "$(uname -s)" == Darwin ]]; then
	BINARY="$BUILD_BIN/Mixar.app/Contents/MacOS/Mixar"
else
	# Linux installs a flat portable tree: bin/mixar next to bin/<version>/.
	BINARY="$BUILD_BIN/mixar"
fi

if [[ ! -x "$BINARY" ]]; then
	echo "Error: Mixar binary not found at:" >&2
	echo "  $BINARY" >&2
	echo "Make sure ./build/$BUILD_ENV exists and is built." >&2
	exit 1
fi

echo "Launching Mixar from build/$BUILD_ENV..."
shift || true
if [[ "$(uname -s)" == Darwin ]]; then
	exec open -n -W "$BUILD_BIN/Mixar.app" --args "$@"
fi

# GHOST backend on Linux (env var > .env > auto). Only this one key is read
# from .env: sourcing settings.sh would export every build setting into the
# running app's environment.
#   auto -> Blender's own choice (Wayland when available, else X11)
#   x11  -> force X11; under a Wayland session this runs on XWayland, where
#           the Agent Bubble's native window controls are implemented
if [[ -z "${MIXAR_LINUX_BACKEND:-}" && -f "$ROOT_DIR/.env" ]]; then
	MIXAR_LINUX_BACKEND="$(sed -n 's/^[[:space:]]*MIXAR_LINUX_BACKEND=//p' "$ROOT_DIR/.env" \
		| tail -n 1 | sed 's/[[:space:]]*#.*$//; s/^["'"'"']//; s/["'"'"'][[:space:]]*$//; s/[[:space:]]*$//')"
fi
case "${MIXAR_LINUX_BACKEND:-auto}" in
	x11|X11)
		if [[ -z "${DISPLAY:-}" ]]; then
			echo "Error: MIXAR_LINUX_BACKEND=x11 but DISPLAY is unset (no X server or XWayland)." >&2
			exit 1
		fi
		# GHOST always tries Wayland first and falls back to X11 only when the
		# connection fails. UNSETTING WAYLAND_DISPLAY is not enough: libwayland
		# then defaults to the "wayland-0" socket and connects anyway. Set but
		# EMPTY, it names no socket, so the Wayland attempt fails cleanly.
		echo "GHOST backend: X11 (MIXAR_LINUX_BACKEND=x11)"
		exec env WAYLAND_DISPLAY= "$BINARY" "$@"
		;;
	auto|AUTO|"")
		;;
	*)
		echo "Error: MIXAR_LINUX_BACKEND must be 'auto' or 'x11', got '$MIXAR_LINUX_BACKEND'." >&2
		exit 1
		;;
esac
exec "$BINARY" "$@"
