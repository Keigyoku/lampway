<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Your Hermes and Grok native pane connectors

Built 2026-10-08 for Mode 2 MAIN panes. Each harness keeps its native login, provider choices, permissions and persona.
Lampway supplies one pane-owned binding file; the connector rereads it before each request. An unbound pane offers no
Lampway tools and refuses stale calls. Lampway does not change the user's shared harness configuration.

Install the server following [its setup instructions](../../server/README.md), including its normal editable install.
The server package provides `lampway-pane-mcp`. Substitute its absolute installed executable path below. Run the native
configuration command yourself; Lampway never runs it against your native home. This is the dedicated pane connector,
separate from any general external-app connector you already configured.

For your own Hermes, use **one** `--env` followed by both quoted values so the native parser retains both variables:

```sh
hermes mcp add lampway_pane --command <absolute-installed-lampway-pane-mcp> --env 'LAMPWAY_HERMES_CONNECTOR_CONFIG=${LAMPWAY_HERMES_CONNECTOR_CONFIG}' 'LAMPWAY_HERMES_CONNECTOR_ROOT=${LAMPWAY_HERMES_CONNECTOR_ROOT}'
```

Outside a Lampway pane these variables are absent, so discovery is empty. Hermes can ask whether to save despite empty
initial discovery; confirm only if you intend to install this dedicated connector. Restart an existing native pane after
installation. Hermes MAIN retains its native toolsets; Lampway adds no toolset filter.

For Grok, install the stdio command at user scope:

```sh
grok mcp add --scope user --transport stdio lampway_pane -- <absolute-installed-lampway-pane-mcp>
```

Start or restart a Lampway MAIN pane and bind it to a scene tab. The helper inherits its own pane binding environment;
binding changes require no prompt insertion, shared configuration change or pane restart. Remove the dedicated entry
with `hermes mcp remove lampway_pane` or `grok mcp remove --scope user lampway_pane` using the same native home.

## What was measured

Hermes v0.21.5 / v2026.9.24: native MCP installation in a synthetic home, two concurrent native discovery clients with
separate pane bindings, actual synthetic tool calls, live rebind/unbind and unchanged synthetic authentication and
environment-file hashes. Grok 1.0.46: native MCP installation, native ACP tool calls across two live bindings, and native
TUI discovery preserving a configured custom persona. Synthetic original-home configuration/authentication/agent hashes
were preserved after native bootstrap. A separate no-connector baseline reproduced Grok's policy-cache deletion and
marketplace migration; native bootstrap may change its own files, so byte immutability is not promised.

These runs denied internet access and used no account or paid provider. They prove connector discovery and routing,
not a model-driven account-backed turn. Image attachment, live-turn interruption and native session records still need
explicitly approved account-backed validation. Helper cancellation forwards the downstream request id and reaps its
owned desktop child. Desktop stdio frames are bounded at 10 MiB, accommodating the existing 8 MiB desktop transport
budget; overflow refuses the frame and reaps the owned child without retrying the tool. It does not promise that a tool already executing in Blender is aborted or rolled back.

## Worker limits

MAIN connectors preserve unrelated native MCP configuration. Workers need exclusive discovery to avoid offering scene
or unrelated tools. Hermes's `--toolsets` combines native tools and MCP server names: adding native `terminal` also
admits an unrelated MCP server named `terminal`. Connector-only workers remove native built-ins and require a specific
owner ruling; they are not silently enabled.

Grok's primary-agent overlay retains inherited MCP servers, and an empty custom agent replaces the configured persona.
A native restrictive policy can limit discovery, but moving its home changes native configuration. A preserving-home
process-local policy namespace remains unproved: the cloud runner rejected the required user-namespace UID mapping.
herdr 0.9.3 also fixes the executable for each native harness kind; it exposes no executable override. Grok's native
`wrap` command is a candidate launch route that retains herdr's canonical executable. An offline 1.0.46 probe preserved
literal child arguments and HOME/GROK_HOME, but started the child in HOME instead of the pane project. A worker bootstrap
must explicitly restore the trusted pane cwd, preserve existing policies, isolate the native leader socket, prove exclusive discovery, and verify interruption
and descendant cleanup across the nested PTY. Native wrap also forwards clipboard input. This candidate still needs
isolation and lifecycle verification and a namespace-capable validator; an upstream executable override is not assumed necessary.
Neither a PATH shim nor a shell-input fallback is implemented. No shared native policy file is changed to work around these limits.
Both unsupported worker paths refuse with actionable
help before a worker starts. Use another supported worker harness while the exclusive route is unresolved.
