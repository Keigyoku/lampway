#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-FileCopyrightText: 2026 Keigyoku (the Lampway backend switch)
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

echo "Launching Lampway from build/$BUILD_ENV..."
shift || true
if [[ "$(uname -s)" == Darwin ]]; then
	exec open -n -W "$BUILD_BIN/Mixar.app" --args "$@"
fi

# GHOST backend on Linux. Precedence: LAMPWAY_LINUX_BACKEND, then the fork's old name MIXAR_LINUX_BACKEND (a
# fallback, kept so a `.env` written for it still works), in the environment first and then in .env, then auto.
# Only these two keys are read from .env: sourcing settings.sh would export every build setting into the
# running app's environment.
#   auto -> Blender's own choice (Wayland when available, else X11)
#   x11  -> force X11; under a Wayland session this runs on XWayland, where
#           the Agent Bubble's native window controls are implemented
read_env_key() {
	[[ -f "$ROOT_DIR/.env" ]] || return 0
	sed -n "s/^[[:space:]]*$1=//p" "$ROOT_DIR/.env" \
		| tail -n 1 | sed 's/[[:space:]]*#.*$//; s/^["'"'"']//; s/["'"'"'][[:space:]]*$//; s/[[:space:]]*$//'
}
LAMPWAY_LINUX_BACKEND="${LAMPWAY_LINUX_BACKEND:-${MIXAR_LINUX_BACKEND:-}}"
if [[ -z "$LAMPWAY_LINUX_BACKEND" ]]; then
	LAMPWAY_LINUX_BACKEND="$(read_env_key LAMPWAY_LINUX_BACKEND)"
fi
if [[ -z "$LAMPWAY_LINUX_BACKEND" ]]; then
	LAMPWAY_LINUX_BACKEND="$(read_env_key MIXAR_LINUX_BACKEND)"
fi
case "${LAMPWAY_LINUX_BACKEND:-auto}" in
	x11|X11)
		if [[ -z "${DISPLAY:-}" ]]; then
			echo "Error: LAMPWAY_LINUX_BACKEND=x11 but DISPLAY is unset (no X server or XWayland)." >&2
			exit 1
		fi
		# GHOST always tries Wayland first and falls back to X11 only when the
		# connection fails. UNSETTING WAYLAND_DISPLAY is not enough: libwayland
		# then defaults to the "wayland-0" socket and connects anyway. Set but
		# EMPTY, it names no socket, so the Wayland attempt fails cleanly.
		echo "GHOST backend: X11 (LAMPWAY_LINUX_BACKEND=x11)"
		exec env WAYLAND_DISPLAY= "$BINARY" "$@"
		;;
	auto|AUTO|"")
		;;
	*)
		echo "Error: LAMPWAY_LINUX_BACKEND must be 'auto' or 'x11', got '$LAMPWAY_LINUX_BACKEND'." >&2
		exit 1
		;;
esac
exec "$BINARY" "$@"
