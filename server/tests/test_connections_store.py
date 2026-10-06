# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_store.md section 6.2 and CONNECTIONS.md section 9: the secret store (keyring first, a 0600 file fallback, never a silent
switch), atomic writes, and a file that does not parse is set aside rather than emptied. Every secret here is a fake sentinel."""

import json
import os
import stat

import keyring.backend
import keyring.errors
import pytest

from lampway_server.connections import files as CF
from lampway_server.connections import store as CS

SENTINEL = "sk-" "or-v1-FAKE-SENTINEL-0123456789abcdef"


class FakeKeyring(keyring.backend.KeyringBackend):
    """A working keyring held in memory (priority set so keyring accepts it as a backend)."""
    priority = 1

    def __init__(self, locked=False):
        super().__init__()
        self.items, self.locked, self.calls = {}, locked, []

    def get_password(self, service, username):
        self.calls.append(("get", service, username))
        if self.locked:
            raise keyring.errors.KeyringLocked("locked")
        return self.items.get((service, username))

    def set_password(self, service, username, password):
        self.calls.append(("set", service, username))
        if self.locked:
            raise keyring.errors.KeyringLocked("locked")
        self.items[(service, username)] = password

    def delete_password(self, service, username):
        self.calls.append(("delete", service, username))
        if self.locked:
            raise keyring.errors.KeyringLocked("locked")
        if (service, username) not in self.items:
            raise keyring.errors.PasswordDeleteError("absent")
        del self.items[(service, username)]


def _mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


# ------------------------------------------------------------------------------------------------ test 3: keyring first, then file
def test_a_working_keyring_is_chosen_and_holds_the_secret(tmp_path):
    ring = FakeKeyring()
    store, reason = CS.choose_store(tmp_path / "secrets", backend=ring)
    assert store.kind == "keyring" and reason
    store.put("openrouter", {"key": SENTINEL})
    assert ring.items[("lampway", "openrouter:key")] == SENTINEL
    assert store.get("openrouter", "key") == SENTINEL
    assert not (tmp_path / "secrets" / "openrouter.json").exists()
    assert not any(k[1].startswith("lampway-probe") for k in ring.items), "the start probe leaves no entry behind"


def test_no_keyring_backend_falls_back_to_a_0600_file_in_a_0700_dir_and_says_why(tmp_path):
    import keyring.backends.fail
    store, reason = CS.choose_store(tmp_path / "secrets", backend=keyring.backends.fail.Keyring())
    assert store.kind == "file"
    assert "no" in reason.lower() and "keyring" in reason.lower()
    store.put("studio:meshy", {"key": SENTINEL})
    files = list((tmp_path / "secrets").glob("*.json"))
    assert len(files) == 1 and _mode(files[0]) == 0o600 and _mode(tmp_path / "secrets") == 0o700
    assert store.get("studio:meshy", "key") == SENTINEL


def test_a_locked_keyring_refuses_and_writes_no_file(tmp_path):
    store, _ = CS.choose_store(tmp_path / "secrets", backend=FakeKeyring(locked=True))
    assert store.kind == "keyring"
    with pytest.raises(CS.StoreLocked) as exc:
        store.put("openrouter", {"key": SENTINEL})
    assert str(exc.value) == "your keyring is locked: unlock it and try again (nothing was saved)"
    assert not (tmp_path / "secrets").exists() or not list((tmp_path / "secrets").glob("*.json"))


def test_a_key_pair_is_one_keyring_entry_per_field_and_forget_removes_both(tmp_path):
    ring = FakeKeyring()
    store, _ = CS.choose_store(tmp_path / "secrets", backend=ring)
    store.put("studio:hi3d", {"client_id": "cid-FAKE", "client_secret": "csec-FAKE"})
    assert ring.items[("lampway", "studio:hi3d:client_id")] == "cid-FAKE"
    assert ring.items[("lampway", "studio:hi3d:client_secret")] == "csec-FAKE"
    store.delete("studio:hi3d", ("client_id", "client_secret"))
    assert not ring.items


# ------------------------------------------------------------------------------------------------ test 9: atomic, set aside, never emptied
def test_crash_mid_write_keeps_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "state" / "thing.json"
    CF.atomic_write_json(path, {"old": True})

    def boom(src, dst):
        raise KeyboardInterrupt("killed between the temp write and the replace")
    monkeypatch.setattr(CF.os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        CF.atomic_write_json(path, {"new": True})
    monkeypatch.undo()
    assert json.loads(path.read_text()) == {"old": True}
    assert [p.name for p in path.parent.iterdir()] == ["thing.json"], "no temp file is left behind"
    assert _mode(path) == 0o600


def test_unparseable_store_is_set_aside_not_emptied(tmp_path):
    path = tmp_path / "state" / "connections.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"connections": {"openrouter": ')                # a truncated write from before this module existed
    with pytest.raises(CF.Unreadable) as exc:
        CF.read_json(path)
    assert "set aside" in str(exc.value)
    aside = list(path.parent.glob("connections.json.corrupt-*"))
    assert len(aside) == 1 and aside[0].read_text() == '{"connections": {"openrouter": '
    assert not path.exists(), "the unreadable file is moved, never overwritten by an empty one"


def test_a_missing_file_reads_as_empty_without_a_corrupt_copy(tmp_path):
    assert CF.read_json(tmp_path / "absent.json") == {}
    assert not list(tmp_path.iterdir())


def test_an_unparseable_file_store_entry_is_set_aside_and_is_an_error(tmp_path):
    import keyring.backends.fail
    store, _ = CS.choose_store(tmp_path / "secrets", backend=keyring.backends.fail.Keyring())
    store.put("fal", {"key": "fal-FAKE"})
    (tmp_path / "secrets" / "fal.json").write_text("{not json")
    with pytest.raises(CS.StoreError) as exc:
        store.get("fal", "key")
    assert "set aside" in str(exc.value)
    assert list((tmp_path / "secrets").glob("fal.json.corrupt-*"))
