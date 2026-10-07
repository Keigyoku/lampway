<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# MCP wrapper T3: offline Blender documentation

T3 implements `lampway_blender_docs` with no-argument live corpus metadata,
`view=get`, `view=search`, and `view=help`. It runs on the server, does not execute
Blender at runtime, and introduces no runtime egress route. The in-app dispatcher
keeps JSON replies; C1 owns MCP TOON rendering and structured content.

The worktree is `lp/mcp-wrapper-migration`, based on current remote `lp/wave5`
commit `287c9d63`. This report describes the working tree, before the coordinator's
final commit and exact-head aggregate checks.

## Sources and package data

The complete MCP source was verified at 27,896 UTF-8 bytes with SHA256
`2decc1a200d059fe1d1ff2f2afb022c17eaeb9d59fef5214c2364c670e8faa77`.
It was delivered from the user-provided
[artifact](https://claude.ai/artifact/72F22QoSzhaWMqNpRhJsnD). Only C0–C2/T1–T3
belong to this lane.

The API corpus contains **1,969 RST files**, generated headlessly by Lampway's
own binary with the generator at pinned upstream commit
`fbe6228777e7d9afefcd61a413844e790ae75db7`. The core source declares Blender
5.2.0; the binary's `bpy.app.version_string` reports the branded version `0.1.0`.
The manifest records both rather than misreporting the runtime version.

The manual contains **2,358 RST files**, from the official
[Blender manual repository](https://projects.blender.org/blender/blender-manual),
`blender-v5.2-release` commit `4a3be8f9ed3b66b24913e0a0d491d3429a70ea08`.
The specification requested a matching release tag. The official repository had
no 5.2 tag at acquisition, so this immutable release-branch revision is used and
identified explicitly in the manifest and shipped notice.

The parser, search and lookup come from
[Blender Lab MCP](https://projects.blender.org/lab/blender_mcp), v1.0.3,
commit `2cea8d566dde07fbac28a61d698909d69724e853`. Original Blender Authors SPDX
lines are retained. Imports are adapted to the server package and the lookup is
extracted from its original MCP registration. A narrow adapter resolves class
members such as `Object.location` through the existing parser's qualified path.

The actual corpus occupies approximately **29 MiB** on disk, exceeding the
proposal's illustrative 16 MB. All RST files have manifest SHA256 entries. API
GPL-2.0-or-later, manual CC-BY-SA-4.0 and helper GPL-3.0-or-later licences have
REUSE annotations and licence texts; the notice and licence texts ship with the
server package.

## Tests and evidence

Initial RED: `tests/test_blender_docs.py::test_offline_blender_docs_is_registered`
failed with `T3 offline Blender documentation tool is absent`, before registration.
After the minimal registry implementation, 14 behaviour cases failed on missing
lookup, search, refusal, home, truncation and help behaviour before implementation.

Review found that manual search returned a manual page identifier but the prior
adapter's help defaulted to API scope and rejected that page identifier. The
follow-up tests and fix were written together, so this was not a chronological
test-first change. An isolated reconstruction of that prior adapter reproduced
both defects using the real `modeling/modifiers/generate/bevel` result: missing
`scope=manual` help and `bad_argument` on its lookup. Current tests cover the
scoped search-to-get sequence and absolute, traversal and backslash refusals.

The final targeted command was:

```text
cd server
<server-python> -m pytest -o addopts= -q tests/test_blender_docs.py \
  tests/test_agent_turn.py tests/test_lampway_tools.py tests/test_server_tools.py
63 passed in 2.10s
```

Tests use the full pinned corpus: `bpy.types.Object.location` returns
`mathutils.Vector` and its description; manual `bevel modifier` ranks the Bevel
Modifier page first. They cover definitive missing results, input bounds and
unknown arguments, path refusal, string truncation, namespace limits, manifest
integrity, and in-app JSON dispatch with Blender/network calls prohibited.

A local wheel build, without publishing, produced a **6,974,877-byte** wheel,
SHA256 `9c1e1df0295afeccf26df64f78d0213766315ed60641abd5d9b0e7d75ea93e3b`.
ZIP inspection verified all **4,327 RST file hashes**, manifest, notice and three
licence texts. An extracted-wheel run checked API lookup, manual ranking and
manual-page lookup with socket connections prohibited. This wheel was built
before the coordinator's final lane changes; its hash is a packaging receipt,
not a release artifact claim.

No push, merge, deployment or publication was performed. The final full server,
rail, generated documentation and exact-head checks belong to lane closeout;
the targeted result above is not a claim that the repository's baseline suites
are all green.

## Publication derivatives and original-contract re-audit (2026-10-07)

The unchanged pre-publish gate initially reported three findings in this lane's
bundled RST: one illustrative bearer credential, one Git SSH remote matching the
email detector, and one API script example containing a personal home path.
These are now explicit placeholders or a generic absolute path. The original
documents' headings, RST directives, identifiers and surrounding explanations
are retained. The manual's Fork instructions still explain obtaining the SSH
URL; the authentication example still shows the Authorization header; the API
example still runs a Python script using an absolute path.

The manifest's `publication_derivatives` records each of the three upstream
original hashes, packaged hashes, source revisions and paths, transformation,
replacement, modifier and date. Existing `files_sha256` entries now describe
packaged bytes. The shipped notice marks the adaptations; GPL-2.0-or-later API
and CC-BY-SA-4.0 manual attribution/licence texts are preserved. No gate,
allow-list, exemption, security setting or git history changed.
All three original hashes were independently checked against their source
files: API `doc/python_api/rst/info_overview.rst` in pinned upstream, and both
manual files under `manual/` in the official checkout at the manifest revision.

RED before changing the data:
`<server-python> -m pytest -o addopts= -q tests/test_blender_docs.py -k 'publication_derivatives or modified_pages'`
reported **1 failed, 1 passed**, failing because derivative provenance was absent.
GREEN: `<server-python> -m pytest -o addopts= -q tests/test_blender_docs.py`
reported **24 passed in 2.71s**. It checks all 4,327 packaged hashes, derivative
metadata and operations, modified-page search discoverability, Object.location
lookup and Bevel Modifier ranking. The unchanged command
`python3 scripts/lampway/prepublish_gate.py --tree server/lampway_server/blender_docs`
now reports **0 findings**. These results supersede the earlier corpus bytes;
the earlier wheel hash above does not identify the current sanitized package.

T3's exact source requires a manual at a matching release tag. A fresh official
remote query on 2026-10-07,
`git ls-remote https://projects.blender.org/blender/blender-manual.git 'refs/tags/*5.2*' 'refs/heads/blender-v5.2-release'`,
returned only `4a3be8f9ed3b66b24913e0a0d491d3429a70ea08 refs/heads/blender-v5.2-release`
and no matching tag. The immutable official release-branch pin is accurately
recorded, but **the matching-release-tag contract remains unmet**. Acceptance
question: may this exact official release-branch revision substitute for the
unavailable 5.2 release tag, retaining the pin and provenance until an official
tag exists? No substitute tag is created or represented as upstream's.

The exact T3 test says the data's Blender version equals
`bpy.app.version_string`. The manifest records that literal branded value as
`blender_version_string: 0.1.0`, separately from `core_version: 5.2.0`.
The native overlay confirms the distinction: `BKE_blender_version.h` declares
Blender core 502/patch 0 and Mixar brand 1/patch 0;
`blenkernel/intern/blender.cc` formats `BKE_blender_version_string()` from the
brand macros; upstream `python/intern/bpy_app.cc` exposes it as the Python
version string. Thus the branded metadata equality is preserved. **Literal
core-version equality with the branded runtime string is false** and cannot be
claimed. If acceptance requires that stronger equality, the captain must decide
whether the separately recorded runtime and core identities suffice; changing
the product's native version identity is outside this documentation lane.

Any already-published ordinary commit-email metadata remains an integrator
historical-action finding. This forward correction does not remove historical
RST blobs or identities and does not authorize rewriting published history.
