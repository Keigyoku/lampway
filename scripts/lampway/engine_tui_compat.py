# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply the owned display extension only to a verified normal engine copy."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGETS = {
    "ui-tui/src/app/createGatewayEventHandler.ts": "d6c433ae982e50bc83bbb766bccf2b7088c4bf56eac13a887355c3a7153ff382",
    "ui-tui/src/app/slash/commands/core.ts": "2bbe1c96e93f82e4e53af4cece1ddf84331a1709796733948593394a8ef428aa",
}


def _replace(text, before, after):
    if text.count(before) != 1:
        raise ValueError("native TUI compatibility anchor is not unique")
    return text.replace(before, after, 1)


def apply(source):
    source = Path(source)
    output = {}
    for name, expected in TARGETS.items():
        data = (source / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"unsupported native TUI source: {name}")
        output[name] = data.decode()
    event = "ui-tui/src/app/createGatewayEventHandler.ts"
    output[event] = _replace(output[event], "import { execFile } from 'child_process'",
        "import { execFile } from 'child_process'\n"
        "import { introMsg, toTranscriptMessages } from '../domain/messages.js'\n"
        "import { createNativeHistoryRefresh } from './lampwayHistory.js'")
    output[event] = _replace(output[event], "  const { appendMessage, panel, setHistoryItems } = ctx.transcript",
        "  const { appendMessage, panel, setHistoryItems } = ctx.transcript\n"
        "  const nativeHistory = createNativeHistoryRefresh({\n"
        "    sid: () => getUiState().sid || undefined,\n"
        "    idle: () => !getUiState().busy && !getTurnState().streaming,\n"
        "    read: sid => rpc('lampway.history_snapshot', { session_id: sid }),\n"
        "    replace: rows => {\n"
        "      const info = getUiState().info\n"
        "      setHistoryItems([...(info ? [introMsg(info)] : []), ...toTranscriptMessages(rows)])\n"
        "    }\n"
        "  })")
    output[event] = _replace(output[event], "    switch (ev.type) {",
        "    nativeHistory.event(ev.type, ev.payload)\n\n    switch (ev.type) {")
    core = "ui-tui/src/app/slash/commands/core.ts"
    output[core] = _replace(output[core], "import { forceRedraw, type MouseTrackingMode } from '@hermes/ink'",
        "import { forceRedraw, type MouseTrackingMode } from '@hermes/ink'\n"
        "import { requestNativeHistoryRefresh } from '../../lampwayHistory.js'")
    output[core] = _replace(output[core],
        "            ctx.transcript.setHistoryItems((prev: Msg[]) => ctx.transcript.trimLastExchange(prev))\n"
        "            ctx.transcript.sys(`undid ${r.removed} messages`)",
        "            if (!requestNativeHistoryRefresh(ctx.sid!, () => ctx.transcript.sys(`undid ${r.removed} messages`))) {\n"
        "              ctx.transcript.setHistoryItems((prev: Msg[]) => ctx.transcript.trimLastExchange(prev))\n"
        "              ctx.transcript.sys(`undid ${r.removed} messages`)\n"
        "            }\n"
        )
    helper = (HERE / "hermes_tui/lampwayHistory.ts").read_bytes()
    # Validate all sources and anchors before writing anything into the copy.
    for name, text in output.items():
        (source / name).write_text(text)
    (source / "ui-tui/src/app/lampwayHistory.ts").write_bytes(helper)
    return {"protocol": 1,
        "patcher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "helper_sha256": hashlib.sha256(helper).hexdigest(),
        "sources": {name: {"native_sha256": TARGETS[name],
            "patched_sha256": hashlib.sha256(text.encode()).hexdigest()} for name, text in output.items()}}
