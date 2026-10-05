# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A file keyring backend for the Lampway profile: login must survive a restart on a machine with no
Secret Service (a box, a VM, Xvfb), and must never touch the desktop's own wallet. Selected with
PYTHON_KEYRING_BACKEND=mixar.modules.lampway_tools.keyring_file.FileKeyring."""

import json
import os
import stat
import sys
from pathlib import Path

import keyring.errors
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import keyring_file  # noqa: E402


@pytest.fixture
def kr(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_KEYRING_FILE", str(tmp_path / "kr" / "keyring.json"))
    return keyring_file.FileKeyring()


def test_set_get_round_trip_and_survives_a_new_instance(kr, tmp_path):
    kr.set_password("MixarSafeStorage", "AccessToken", "tok-a")
    assert kr.get_password("MixarSafeStorage", "AccessToken") == "tok-a"
    assert keyring_file.FileKeyring().get_password("MixarSafeStorage", "AccessToken") == "tok-a"


def test_missing_entry_is_none(kr):
    assert kr.get_password("s", "u") is None


def test_delete_removes_and_a_second_delete_raises(kr):
    kr.set_password("s", "u", "p")
    kr.delete_password("s", "u")
    assert kr.get_password("s", "u") is None
    with pytest.raises(keyring.errors.PasswordDeleteError):
        kr.delete_password("s", "u")


def test_the_file_is_owner_only_and_its_directory_too(kr, tmp_path):
    kr.set_password("s", "u", "p")
    f = tmp_path / "kr" / "keyring.json"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700


def test_services_and_users_do_not_collide(kr):
    kr.set_password("a", "u", "1")
    kr.set_password("b", "u", "2")
    kr.set_password("a", "v", "3")
    assert [kr.get_password("a", "u"), kr.get_password("b", "u"), kr.get_password("a", "v")] == ["1", "2", "3"]


def test_a_corrupt_file_reads_as_empty_and_is_replaced_on_write(kr, tmp_path):
    f = tmp_path / "kr" / "keyring.json"
    f.parent.mkdir(parents=True)
    f.write_text("{not json")
    assert kr.get_password("s", "u") is None
    kr.set_password("s", "u", "p")
    assert json.loads(f.read_text())["s"]["u"] == "p"


def test_default_path_is_under_lampway_home(monkeypatch, tmp_path):
    monkeypatch.delenv("LAMPWAY_KEYRING_FILE", raising=False)
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    assert keyring_file.keyring_path() == tmp_path / "home" / "keyring.json"


def test_it_is_a_usable_keyring_backend_by_dotted_name(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_KEYRING_FILE", str(tmp_path / "k.json"))
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "mixar.modules.lampway_tools.keyring_file.FileKeyring")
    import keyring
    keyring.core.init_backend()
    keyring.set_password("MixarSafeStorage", "RefreshToken", "r1")
    assert keyring.get_password("MixarSafeStorage", "RefreshToken") == "r1"
