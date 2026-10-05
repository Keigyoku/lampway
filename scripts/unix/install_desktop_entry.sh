#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-FileCopyrightText: 2026 Keigyoku (the Lampway names and launcher)
#
# SPDX-License-Identifier: GPL-2.0-or-later

# Install (or remove) a per-user Linux desktop launcher for a local build.
#
#   ./install_desktop_entry.sh [ENV]          install for build/ENV (default Prod)
#   ./install_desktop_entry.sh --uninstall    remove the launcher and icons
#
# The entry is the build's own bin/mixar.desktop, installed as lampway.desktop with the icon name `lampway`
# (never the Mixar names) and Exec pointed at the Lampway launcher (scripts/lampway/lampway), so a menu launch
# starts the server, the tools and the bridge too, and run.sh's .env settings (LAMPWAY_LINUX_BACKEND) apply.
# Nothing outside ~/.local/share is touched.

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
DESKTOP_FILE="$APP_DIR/lampway.desktop"
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
		"$ICON_DIR/scalable/apps/lampway.svg" \
		"$ICON_DIR/symbolic/apps/lampway-symbolic.svg"
	for size in $PNG_SIZES; do
		rm -f "$ICON_DIR/${size}x${size}/apps/lampway.png"
	done
	refresh_menus
	echo "Removed the Lampway launcher."
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

LAUNCHER="$ROOT_DIR/scripts/lampway/lampway"
if [[ ! -x "$LAUNCHER" ]]; then
	echo "Error: the Lampway launcher $LAUNCHER is missing or not executable." >&2
	exit 1
fi

mkdir -p "$APP_DIR" "$ICON_DIR/scalable/apps" "$ICON_DIR/symbolic/apps"
install -m 644 "$BUILD_BIN/mixar.svg" "$ICON_DIR/scalable/apps/lampway.svg"
if [[ -f "$BUILD_BIN/mixar-symbolic.svg" ]]; then
	install -m 644 "$BUILD_BIN/mixar-symbolic.svg" "$ICON_DIR/symbolic/apps/lampway-symbolic.svg"
fi
if command -v rsvg-convert >/dev/null 2>&1; then
	for size in $PNG_SIZES; do
		mkdir -p "$ICON_DIR/${size}x${size}/apps"
		rsvg-convert -w "$size" -h "$size" "$BUILD_BIN/mixar.svg" \
			-o "$ICON_DIR/${size}x${size}/apps/lampway.png"
	done
fi

# Desktop Entry spec: quote the program path, and escape the characters that
# are special inside a quoted Exec argument (\ " ` $).
quoted="$(printf '%s' "$LAUNCHER" | sed -e 's/[\\"`$]/\\&/g')"
# sed replacement: escape the delimiter-free specials & and \.
exec_line="Exec=\"$quoted\" --env $BUILD_ENV %f"
exec_line_sed="$(printf '%s' "$exec_line" | sed -e 's/[\\&]/\\&/g')"

tmp="$(mktemp "$APP_DIR/.lampway.desktop.XXXXXX")"
sed -e "s|^Exec=.*|$exec_line_sed|" \
	-e "s|^Icon=.*|Icon=lampway|" \
	"$BUILD_BIN/mixar.desktop" >"$tmp"
chmod 644 "$tmp"
mv -f "$tmp" "$DESKTOP_FILE"

if command -v desktop-file-validate >/dev/null 2>&1; then
	desktop-file-validate "$DESKTOP_FILE" || echo "Warning: desktop-file-validate reported issues." >&2
fi
refresh_menus

echo "Installed the Lampway launcher for build/$BUILD_ENV:"
echo "  $DESKTOP_FILE"
echo "It starts Lampway through the launcher, so .env settings such as LAMPWAY_LINUX_BACKEND apply."
