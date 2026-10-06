#!/bin/bash
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Claude Code cloud sessions: install what the standalone pytest suite (runs OUTSIDE
# Blender, bpy stubbed by the root conftest.py) and the REUSE lint need. The Blender
# build itself (make build) is out of scope here: it needs the multi-GB upstream/ submodule.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore \
  -r scripts/python_requirements.txt \
  numpy requests \
  pytest pytest-timeout \
  reuse

# lampway-server (server/) and its test extras; imported by server/tests and some root tests.
python3 -m pip install --quiet --disable-pip-version-check --root-user-action=ignore -e "server/[test]"
