# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding F7 with the captain's C8 ("refuse key files readable by others now"): the OpenRouter key file and the fal key file get the
owner-only check the studio ``_FILE`` variables already had, because both now resolve through Connections."""

import os

import pytest

from lampway_server.agent.providers.openrouter import KeyMissing, resolve_api_key
from lampway_server import fal as F

OR_KEY = "sk-" "or-v1-FAKE-KEYFILE-66666666666666666666"
FAL = "fal-FAKE-KEYFILE-777777777777777777"


def _file(tmp_path, name, text, mode):
    p = tmp_path / name
    p.write_text(text)
    os.chmod(p, mode)
    return p


def test_an_openrouter_key_file_readable_by_others_is_refused_with_the_fix(tmp_path):
    p = _file(tmp_path, "or.env", f"OPENROUTER_API_KEY={OR_KEY}\n", 0o644)
    with pytest.raises(KeyMissing) as exc:
        resolve_api_key({"LAMPWAY_OPENROUTER_KEY_FILE": str(p)})
    assert f"{p} must be owner-only (chmod 600)" in str(exc.value) and OR_KEY not in str(exc.value)


def test_an_owner_only_openrouter_key_file_still_works(tmp_path):
    p = _file(tmp_path, "or.env", f"OPENROUTER_API_KEY={OR_KEY}\n", 0o600)
    assert resolve_api_key({"LAMPWAY_OPENROUTER_KEY_FILE": str(p)}) == OR_KEY


def test_a_fal_key_file_readable_by_others_is_refused_with_the_fix(tmp_path, monkeypatch):
    p = _file(tmp_path, "fal.key", f"Key {FAL}\n", 0o640)
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("FALAI_KEY", raising=False)
    monkeypatch.setenv("FAL_KEY_FILE", str(p))
    client = F.FalClient(tmp_path, receipts=object())
    with pytest.raises(F.FalError) as exc:
        client._auth()
    assert f"{p} must be owner-only (chmod 600)" in str(exc.value)


def test_an_owner_only_fal_key_file_is_read_with_its_prefix_stripped(tmp_path, monkeypatch):
    p = _file(tmp_path, "fal.key", f"Key {FAL}\n", 0o600)
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("FALAI_KEY", raising=False)
    monkeypatch.setenv("FAL_KEY_FILE", str(p))
    assert F.FalClient(tmp_path, receipts=object())._auth() == {"authorization": f"Key {FAL}"}
