<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Security Policy

## Reporting a vulnerability

Report security issues **privately**, in this order of preference:

1. GitHub private vulnerability reporting: <https://github.com/Keigyoku/lampway/security/advisories/new>
2. By email to `security@lampway.dev`, once the project announces that the mailbox is live. **Placeholder: the project owner has not named a contact yet, so until this line is replaced, use the first route.**

Do not open a public issue for vulnerabilities, secrets, credential leaks, exploit details, or private user data.

Include a concise description, the affected version or commit, safe reproduction steps, and the impact. Do not include real account passwords, API keys, tokens, private scene data, or third-party secrets in reports.

## Scope

In scope: the Lampway client and server code in this repository, its build and packaging scripts, and how it handles tokens, local credentials, user files, spend and network requests. Examples that count: the agent sandbox reading or writing outside its allowed paths, a local process or a web page driving the app or the server, a spend that did not wait for the user, data leaving through a route that was off, a key or token reaching a log, a receipt or a repository file.

Out of scope: third-party services Lampway can be pointed at (their own vulnerabilities are theirs to fix), the upstream projects it is built on unless the flaw is in code this repository changed, and attacks that need you to have already enabled a local-CLI adapter or the cockpit on a hostile machine.

## What the design defends (and where it stops)

Lampway is a single-user, local-first application. The defences below are what the code does; each has tests, and the hardening report ([`docs/reports/harden.md`](docs/reports/harden.md)) tabulates the 14 findings and their fixes.

- **The server binds to loopback** (`127.0.0.1:8787`) and answers `421` to any request whose `Host` is not loopback or the configured bind host (a defence against DNS rebinding); a WebSocket with a wrong Host is closed. Sign-in start and sign-out are `POST`s that require a loopback `Origin`. Do not bind the server to a non-loopback address unless you understand that it is a single-user server with one account.
- **The live bridge** (the loopback socket that executes Python inside the app) serves only the application's own user: the peer's uid is read from the kernel's socket table, unattributable connections are refused and a request is capped at 16 MiB. Turn it off with `--bridge-port 0`.
- **The script sandbox** gates `open()`, numpy loads, `bpy.ops` and datablock file methods by realpath, refuses `allow_pickle`, and allows `mixar.*` imports but not `os`, `sys`, `subprocess` or `pathlib`. Every tool path is jailed to the project root; a path outside it, `..` or a symlink out is refused. Tool arguments reach the sandbox as one JSON string literal so no value can change the code.
- **Spend** cannot be confirmed by an agent, a swarm worker or a script: the confirm is a user click, takes its actor from the route, and the Client refuses it while any script runs. Residual gaps are known and named: a person can still run the confirm operator by hand, and the MCP bridge's own execution path is not itself gated.
- **Egress**: every outbound route is off until you switch it on, with one choke point at the HTTP transport and a content-free log ([`docs/privacy.md`](docs/privacy.md)). The gate covers the server process and the compute CLI.
- **Secrets**: provider keys live in the environment, a key file you name, or sign-in stores written with mode 0600 (`chatgpt_auth.json`, `agent_settings.json`, `provider_prefs.json`, the file keyring). They are never part of saved provider settings and are redacted from logs and error text (OpenRouter keys, OAuth `code`, `state` and token query values, including uvicorn's access log). Receipts and the ledger drop signed URLs and secret-looking keys and reject secret-prefixed values.
- **Refresh tokens** persist across restarts (0600); the JWT secret is generated once and kept in the state directory.
- **No telemetry by default**, and only ever to the configured backend. The client's allowed hosts are your own server.
- **Child processes**: the cockpit starts your own agent CLIs only on your click and never reads their credential files; the Boat adapter runs the CLI with a cleaned environment so none of Lampway's keys reach it.

Known limits worth reporting against, not hiding: the swarm's lane isolation cannot technically stop a worker script from editing another worker's `bpy.data` objects (the server detects and reports it); the local-CLI adapters (`claude_cli`, `codex_cli`) run binaries you are logged into and are for personal use under their providers' terms; provider request shapes for several studios and cloud providers are unverified against the live services.

## Supported versions

The most recent tagged release, and the integration branch that `main` carries, are the supported security review targets. There are no tagged binaries yet; Lampway ships as source.

## Handling of reports

Reports are read by the maintainers. Please give us a reasonable chance to fix a problem before you disclose it publicly, and tell us if you intend to publish a fix or an advisory. Credit is given unless you ask otherwise.
