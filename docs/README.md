<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway documentation

Lampway is an open-source 3D suite on a Blender 5.2 core with an AI agent inside it and a server you run yourself. These pages describe what the code on the integration branch does today. Where something is specified but not built, the page says so and gives its status.

## Start here

| Page | Read it for |
|---|---|
| [Getting started](getting-started.md) | clone, build, install the server, launch, first conversation, settings, troubleshooting |
| [Providers](providers.md) | the main agent and swarm on your own plans (ChatGPT plan, the Claude CLI, OpenRouter, Anthropic, local), image and video generation, and the studios (Tripo, Meshy, Hi3D, Hyper3D, Higgsfield) |
| [Privacy and egress consent](privacy.md) | every route off until you opt in, the wire indicator, the egress log, private assets |
| [Spend: receipts, caps and clicks](spend.md) | how nothing costs money you did not agree to |

## Features

| Page | Read it for |
|---|---|
| [Compute](compute.md) | the provider-agnostic compute CLI, Boat and the other adapters, Blender offload |
| [Asset Vault](asset-vault.md) | the local asset library: what is built, what is in progress |
| [Cockpit](cockpit.md) | your real agent CLIs in Lampway's own isolated herdr, the decoupling guarantee, the WezTerm add-on |
| [Animation from video](animation-from-video.md) | clip, multi-view motion fit, checks and loop export |
| [Armour pipeline](armour-pipeline.md) | one armour piece from plates to an engine-ready, rigged export |
| [Connect AI apps (MCP)](lampway/connect-ai-apps.md) | drive your open scene from Claude Code, Codex, Cursor and others |
| [Tools](tools.md) | every agent tool, generated from the live registry |

## Project

| Page | Read it for |
|---|---|
| [Roadmap](roadmap.md) | waves, lanes and their status, decisions owed |
| [Resource audit](lampway/resource-audit.md) | third-party tools audited, and what was adopted or refused |
| [Wave reports](reports/) | the measured record of each wave: test counts, live runs, costs, honest gaps |
| [Contributing](../CONTRIBUTING.md) | the pre-publish gate, lanes and integration, test commands, the build box |
| [Security](../SECURITY.md) | reporting a vulnerability and what the design defends |
| [Third-party notices](../THIRD_PARTY.md), [NOTICE](../NOTICE.md) | licences, models, fonts, attribution |
| [Build guide](../BUILD-LAMPWAY.md) | the Linux build, measured |

## Wave reports

The reports in `docs/reports/` are the record of what each branch measured at the time. They are not edited after the fact, so a number in a report can be older than the code; the pages above are kept current against the code.

[build](reports/build.md) | [fork patches](reports/fork-patches.md) | [server](reports/server.md) | [tools](reports/tools.md) | [harden](reports/harden.md) | [features](reports/features.md) | [studios](reports/studios.md) | [video](reports/video.md) | [prompts](reports/prompts.md) | [wave 0](reports/wave0.md) | [wave 1](reports/wave1.md) | [wave 2](reports/wave2.md) | [wave 3](reports/wave3.md) | [wave 4](reports/wave4.md) | [wave 5](reports/wave5.md) | [compute spend](reports/compute-spend.md)

## Conventions on these pages

- Status words: **built** (implemented and tested), **live** (also run end to end against the real service), **partial**, **in progress** (a lane is working on it), **planned**, **waiting** (a decision only the maintainer can make).
- `[UNVERIFIED]` marks a figure, shape or availability that no source read or run backs.
- Paths are written `<workspace>` or `~/.local/share/lampway`; no page contains a personal path, address or key.
