# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway never reads another app's credentials (docs/reports/agent-modes-spec.md R0 and B0).

The BYOK dialog had a "Codex (ChatGPT sub)" provider that read ``~/.codex/auth.json`` (or took it from the clipboard) and sent the
bundle to the server as an API key. Plan usage in Lampway's own agent is Sign in with ChatGPT, Lampway's own OAuth client; a user
who wants Codex runs Codex itself, as a Bring Your Own Agent harness, on Codex's own login.
"""

import ast
from pathlib import Path

from mixar.modules.byok.core import model_suggestions

CLIENT = Path(__file__).resolve().parents[1] / "src/scripts/mixar"

#: Other apps' credential files: a path to one, or its bare name joined into a path. Writing Codex's config.toml stays allowed
#: (the user's click adds Lampway's MCP entry there); reading a login never is.
FOREIGN_CREDENTIALS = ("auth.json", ".credentials.json", "oauth_creds.json")


def _names_a_credential(text: str) -> bool:
    return text in FOREIGN_CREDENTIALS or any(f"/{name}" in text for name in FOREIGN_CREDENTIALS)


def test_no_client_source_names_another_apps_credential_file():
    offenders = []
    for path in CLIENT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _names_a_credential(node.value):
                offenders.append(f"{path.relative_to(CLIENT)}:{node.lineno}")
    assert offenders == []


def test_the_check_sees_a_planted_read():
    assert _names_a_credential("auth.json") and _names_a_credential("~/.codex/auth.json")
    assert _names_a_credential("~/.claude/.credentials.json") and not _names_a_credential("_auth.json")


def test_the_provider_list_has_no_codex_subscription_option():
    ids = [item[0] for item in model_suggestions.get_provider_items()]
    assert "codex" not in ids
    assert "openrouter" in ids and "local" in ids
