#!/bin/bash
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Claude Code cloud sessions: install what the standalone pytest suite (runs OUTSIDE
# Blender, bpy stubbed by the root conftest.py) and the REUSE lint need, plus the
# compiler and system packages for a Linux app build (BUILD-LAMPWAY.md). The build
# itself (~1 h clean on 4 cores, ~13 GB) is NOT run here; start it on demand:
#   LAMPWAY_MIN_FREE_GB=20 scripts/lampway/build_linux.sh
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Blender 5.2 needs GCC >= 14 (Ubuntu 24.04 ships 13); the -dev set is
# build_linux.sh --check-deps' list, the rest is what the binary dlopens under Xvfb.
APT_PACKAGES=(
  gcc-14 g++-14 rsync pkg-config
  libx11-dev libxxf86vm-dev libxcursor-dev libxi-dev libxrandr-dev libxinerama-dev
  libxkbcommon-dev libwayland-dev libdecor-0-dev wayland-protocols libdbus-1-dev
  libgl-dev libegl-dev libsecret-1-dev libcurl4-openssl-dev libssl-dev
  libsm6 libice6 libegl-mesa0 libgl1 libegl1
)
if ! dpkg -s "${APT_PACKAGES[@]}" >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends "${APT_PACKAGES[@]}" >/dev/null
fi

python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore \
  -r scripts/python_requirements.txt \
  numpy requests \
  pytest pytest-timeout \
  reuse

# lampway-server (server/) and its test extras; imported by server/tests and some root tests.
python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore -e "server/[test]"
