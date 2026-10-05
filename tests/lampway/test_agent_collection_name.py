# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""One name for the collection the agent's work lands in. The sweep that renamed Mixie to Lampway Agent made the client's default "Lampway Agent Agent" while the server kept sending
"Mixie Agent", and the 22 mirrored tests pinned the wrong value. The client (``brand.AGENT_COLLECTION``) and the server (``lampway_server.brand.AGENT_COLLECTION``) each define it ONCE and
every use reads that constant; this test pins the two together and fails on a doubled word or a leftover old name anywhere in the server's strings."""

import pathlib
import re

from mixar.config import brand

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER = ROOT / "server/lampway_server"


def _server_constant():
    m = re.search(r'^AGENT_COLLECTION\s*=\s*"([^"]+)"', (SERVER / "brand.py").read_text(), re.M)
    assert m, "server/lampway_server/brand.py must define AGENT_COLLECTION"
    return m.group(1)


def test_client_and_server_agree_on_the_collection_name():
    assert _server_constant() == brand.AGENT_COLLECTION == "Lampway Agent"


def test_the_clients_default_target_is_the_constant_not_a_literal():
    from mixar.modules.common.agent_execution import commit
    assert commit.DEFAULT_TARGET_COLLECTION == brand.AGENT_COLLECTION
    src = (ROOT / "src/scripts/mixar/modules/common/agent_execution/commit.py").read_text()
    assert "AGENT_COLLECTION" in src and 'DEFAULT_TARGET_COLLECTION = "' not in src


def test_the_server_sends_the_constant_and_no_old_or_doubled_name_remains():
    harness = (SERVER / "agent/harness.py").read_text()
    assert re.search(r"^TARGET_COLLECTION\s*=\s*AGENT_COLLECTION", harness, re.M)
    for path in list(SERVER.rglob("*.py")):
        text = path.read_text()
        assert "Mixie Agent" not in text and "Agent Agent" not in text, path.relative_to(ROOT)
    assert "Agent Agent" not in (ROOT / "src/scripts/mixar/modules/common/agent_execution/commit.py").read_text()
