# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md 5.10 and steps 2/8 for embeddings (HC20, D6): the bundled local models stay every job's default; an embed.* choice
that names an OpenRouter model gives the Vault's embedding service its OpenRouter client (through Connections) and its model; the old
``embed_defaults.json`` is imported into Choices once and renamed ``.migrated``."""

import json

import pytest

from lampway_server import choices as CH
from lampway_server import connections as C
from lampway_server.choices import store as CS
from lampway_server.connections import store as CNS

KEY = "sk-" "or-v1-" + "3a2b" * 16


@pytest.fixture
def live(tmp_path, monkeypatch):
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    C.set_active(C.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", store=CNS.MemoryStore(), env={}))
    yield tmp_path / "state"
    CH.set_active(None, None)


def test_local_first_the_vault_has_no_openrouter_client_by_default(live):
    from lampway_server.library.vault import Vault
    C.active().put_secret("openrouter", {"key": KEY}, by="user")
    v = Vault(live)
    assert v.embed.or_ is None, "D6: nothing uploads until the user chooses an OpenRouter embedding"
    v.close()


def test_an_openrouter_embedding_choice_gives_the_service_its_client_and_model(live):
    from lampway_server.library.vault import Vault
    C.active().put_secret("openrouter", {"key": KEY}, by="user")
    CH.active_store().set("embed.text_doc", "global", None, {"preferred": "openrouter:qwen/qwen3-embedding-8b"}, by="user")
    v = Vault(live)
    assert v.embed.or_ is not None
    assert v.embed.default_model("text_api") == "qwen/qwen3-embedding-8b"
    v.close()


def test_the_old_defaults_file_is_imported_once_and_renamed(live):
    from lampway_server.choices.bridge import import_embed_defaults
    lib = live / "library"
    lib.mkdir(parents=True)
    (lib / "embed_defaults.json").write_text(json.dumps({"text_doc:private": "openrouter-not-a-prefix", "text_query:private": "local:clip-vit-b-32",
                                                         "image_look:private": "voyageai/voyage-multimodal-3.5"}))
    n = import_embed_defaults(lib)
    doc = CH.active_store().global_doc()["purposes"]
    assert doc["embed.image_look"]["preferred"] == "openrouter:voyageai/voyage-multimodal-3.5"
    assert doc["embed.text_query"]["preferred"] == "local:clip-vit-b-32"
    assert n == 2 and not (lib / "embed_defaults.json").exists() and (lib / "embed_defaults.json.migrated").exists()
    assert import_embed_defaults(lib) == 0
