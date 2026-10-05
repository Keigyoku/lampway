#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-2.0-or-later

# Install (or remove) a per-user Linux desktop launcher for a local build.
#
#   ./install_desktop_entry.sh [ENV]          install for build/ENV (default Prod)
#   ./install_desktop_entry.sh --uninstall    remove the launcher and icons
#
# The entry is the build's own bin/mixar.desktop with Exec pointed at run.sh,
# so menu launches honour the same .env settings as `make run`
# (MIXAR_LINUX_BACKEND in particular). Nothing outside ~/.local/share is touched.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ "$(uname -s)" != Linux ]]; then
	echo "Error: desktop entries are a Linux feature." >&2
	exit 1
fi

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor"
DESKTOP_FILE="$APP_DIR/mixar.desktop"
# Fixed-size copies for menus and docks that prefer them over the SVG.
PNG_SIZES="16 22 24 32 48 64 128 256"

refresh_menus() {
	command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" || true
	# Icon loaders cache theme directory listings and only rescan when the
	# theme directory's mtime changes, so a new icon dropped into an existing
	# hicolor tree stays invisible to running shells without this.
	touch "$ICON_DIR"
	command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$ICON_DIR" || true
	# KDE Plasma caches the menu separately.
	for sycoca in kbuildsycoca6 kbuildsycoca5; do
		if command -v "$sycoca" >/dev/null 2>&1; then
			"$sycoca" >/dev/null 2>&1 || true
			break
		fi
	done
	# Running KDE processes (plasmashell) keep icons in memory; this is the
	# signal KDE's own icon settings send to make them reload.
	if command -v dbus-send >/dev/null 2>&1 && [[ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
		dbus-send --session --type=signal /KIconLoader org.kde.KIconLoader.iconChanged int32:0 2>/dev/null || true
	fi
}

if [[ "${1:-}" == "--uninstall" ]]; then
	rm -f "$DESKTOP_FILE" \
		"$ICON_DIR/scalable/apps/mixar.svg" \
		"$ICON_DIR/symbolic/apps/mixar-symbolic.svg"
	for size in $PNG_SIZES; do
		rm -f "$ICON_DIR/${size}x${size}/apps/mixar.png"
	done
	refresh_menus
	echo "Removed the Mixar launcher."
	exit 0
fi

BUILD_ENV="${1:-Prod}"
BUILD_BIN="$ROOT_DIR/build/$BUILD_ENV/bin"
for required in mixar mixar.desktop mixar.svg; do
	if [[ ! -e "$BUILD_BIN/$required" ]]; then
		echo "Error: $BUILD_BIN/$required not found. Build first: make build" >&2
		exit 1
	fi
done

mkdir -p "$APP_DIR" "$ICON_DIR/scalable/apps" "$ICON_DIR/symbolic/apps"
install -m 644 "$BUILD_BIN/mixar.svg" "$ICON_DIR/scalable/apps/mixar.svg"
if [[ -f "$BUILD_BIN/mixar-symbolic.svg" ]]; then
	install -m 644 "$BUILD_BIN/mixar-symbolic.svg" "$ICON_DIR/symbolic/apps/mixar-symbolic.svg"
fi
if command -v rsvg-convert >/dev/null 2>&1; then
	for size in $PNG_SIZES; do
		mkdir -p "$ICON_DIR/${size}x${size}/apps"
		rsvg-convert -w "$size" -h "$size" "$BUILD_BIN/mixar.svg" \
			-o "$ICON_DIR/${size}x${size}/apps/mixar.png"
	done
fi

# Desktop Entry spec: quote the program path, and escape the characters that
# are special inside a quoted Exec argument (\ " ` $).
run_script="$ROOT_DIR/scripts/unix/run.sh"
quoted="$(printf '%s' "$run_script" | sed -e 's/[\\"`$]/\\&/g')"
# sed replacement: escape the delimiter-free specials & and \.
exec_line="Exec=\"$quoted\" $BUILD_ENV %f"
exec_line_sed="$(printf '%s' "$exec_line" | sed -e 's/[\\&]/\\&/g')"

tmp="$(mktemp "$APP_DIR/.mixar.desktop.XXXXXX")"
sed -e "s|^Exec=.*|$exec_line_sed|" \
	-e "s|^Icon=.*|Icon=mixar|" \
	"$BUILD_BIN/mixar.desktop" >"$tmp"
chmod 644 "$tmp"
mv -f "$tmp" "$DESKTOP_FILE"

if command -v desktop-file-validate >/dev/null 2>&1; then
	desktop-file-validate "$DESKTOP_FILE" || echo "Warning: desktop-file-validate reported issues." >&2
fi
refresh_menus

echo "Installed the Mixar launcher for build/$BUILD_ENV:"
echo "  $DESKTOP_FILE"
echo "It starts Mixar through run.sh, so .env settings such as MIXAR_LINUX_BACKEND apply."
