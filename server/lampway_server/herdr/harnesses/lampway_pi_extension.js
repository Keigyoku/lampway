// SPDX-FileCopyrightText: 2026 Lampway contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Lampway's Pi extension (docs/reports/agent-modes-spec.md B1, the Pi row): a wrapper only, never an agent host.
//
// A Pi pane that Lampway started bound to a scene tab is launched with `-e <this file>` and LAMPWAY_PI_MCP naming the pane's own
// MCP config (0600, under Lampway's herdr root, written by the cockpit host: the same `mcpServers` entries a Claude Code pane gets,
// Lampway's launcher pinned to the tab by LAMPWAY_BOUND_SESSION and, when the server knows its pane endpoint, the swarm entry with
// the pane's own bearer). This file hands those entries to Pi's own MCP client (`pi.registerMcpServer`, Pi >= 1.0) for this session
// only: nothing is written to the user's ~/.pi/agent/mcp.json or the project's .pi/mcp.json, and nothing else is read.
// Pi then connects, lists and calls Lampway's tools itself, through its own tool pipeline and permission gates.
import { readFileSync } from "node:fs";

export default function lampway(pi) {
  const path = process.env.LAMPWAY_PI_MCP;
  if (!path) return;                                    // not a Lampway pane: the extension does nothing
  let servers = {};
  try {
    servers = JSON.parse(readFileSync(path, "utf8")).mcpServers || {};
  } catch (err) {
    console.error(`lampway: the pane's MCP config ${path} could not be read (${err.message}); Lampway's tools are not available here`);
    return;
  }
  for (const [name, entry] of Object.entries(servers)) {
    pi.registerMcpServer(name, { exposure: "direct", ...entry });
  }
}
