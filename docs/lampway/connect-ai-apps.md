# Connect AI apps (MCP)

Lampway can be driven from an AI assistant that speaks MCP (Claude Code, Codex, Cursor, VS Code, OpenCode, Claude Desktop and others). The assistant starts a small local
launcher, the launcher talks to your running Lampway over a loopback connection, and the assistant uses Lampway's scene tools on your open scene.

## Turn it on

1. Open Lampway and sign in to your Lampway server.
2. Profile menu, **Connect AI Apps (MCP)**, then enable MCP.
3. Pick your app in the dialog. It shows the exact setup for that app:
   - Claude Code: `claude mcp add --scope user lampway -- ~/.lampway/connector/lampway-mcp`, or click **Add to Claude Code**.
   - Codex: a `[mcp_servers.lampway]` table in `~/.codex/config.toml`, or click **Add to Codex**.
   - Others: merge the shown JSON into the app's `mcpServers` configuration.

The server is named `lampway` and the launcher lives at `~/.lampway/connector/lampway-mcp` (`lampway-mcp.cmd` on Windows).

## Upgrading from a build that still said Mixar

- The first start reads the old `~/.mixar/connector/installation.json` once and writes the new location.
- For one release the old launcher path (`~/.mixar/connector/mixar-mcp`) stays as a small script that forwards to the new launcher, so an app configured with the old command
  keeps working. Adding Lampway to Claude Code or Codex replaces an old `mixar` entry with the `lampway` one.
- `MIXAR_MCP_DISCOVERY_DIR` still works for one release; `LAMPWAY_MCP_DISCOVERY_DIR` wins when both are set.

## Safety

Only a loopback credential is written to disk (private to your user). The assistant acts on your open, signed-in scene; your own mouse or keyboard always takes control back, and
spends on paid providers still wait for your click.
