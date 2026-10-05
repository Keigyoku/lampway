# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lampway tools: the shelf's mesh QA, rebuild, parts and proportion tools as first-class Lampway features,
the live bridge the main session drives the app through, and the agent-tool surface the server calls.

Layout (see README.md):
  settings   - project root, interpreters, bridge and server configuration (environment + user settings file)
  axi, toon  - the shelf's AXI/TOON output conventions for anything that stays a command line tool
  bridge     - the live socket bridge (MCP-compatible) and file inbox
  ui/        - operators and panels (auto-registered by the bootstrap)
"""

TOOLS_VERSION = "0.1.0"
