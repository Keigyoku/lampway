# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lampway has its own keyring slot (rebrand finding 4).

A stock Mixar install on the same machine kept its login in the service ``MixarSafeStorage``; Lampway used the same name, so each client read the
other's token and sent it to its own backend. Lampway's service is ``LampwaySafeStorage`` everywhere (Python, C++, Windows credential targets), and
nothing reads the old slot: a Mixar token is a credential for Mixar's backend and is never migrated.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/scripts"))
from mixar.config import brand  # noqa: E402
from mixar.modules.auth.core import auth  # noqa: E402

OLD = "MixarSafeStorage"


def test_the_service_name_is_lampways_and_defined_once():
    assert brand.KEYRING_SERVICE == "LampwaySafeStorage"
    header = (ROOT / "src/source/blender/blenlib/BLI_lampway_brand.h").read_text(encoding="utf-8")
    assert re.search(r'#define LAMPWAY_KEYRING_SERVICE "LampwaySafeStorage"', header)


def test_no_shipped_source_names_the_old_service():
    offenders = []
    for root in ("src/scripts/mixar", "src/source/creator", "server", "scripts"):
        for f in (ROOT / root).rglob("*"):
            if f.is_file() and f.suffix in (".py", ".cc", ".hh", ".h", ".sh") and "__pycache__" not in f.parts:
                for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if OLD in line:
                        offenders.append(f"{f.relative_to(ROOT)}:{n}")
    assert offenders == [], offenders


def test_the_client_reads_and_writes_only_the_lampway_slot(monkeypatch):
    store, touched = {}, []

    def get(service, user):
        touched.append(service)
        return store.get((service, user))

    def put(service, user, value):
        touched.append(service)
        store[(service, user)] = value

    monkeypatch.setattr(auth, "_is_windows", False)
    monkeypatch.setattr(auth.keyring, "get_password", get)
    monkeypatch.setattr(auth.keyring, "set_password", put)
    store[(OLD, "AccessToken")] = "a-mixar-token"          # a stock Mixar install's token sits in the keyring
    assert auth.get_access_token() == ""                    # it is not ours and is never read
    auth.store_access_token("lampway-token")
    assert store[("LampwaySafeStorage", "AccessToken")] == "lampway-token"
    assert auth.get_access_token() == "lampway-token"
    assert set(touched) == {"LampwaySafeStorage"} and store[(OLD, "AccessToken")] == "a-mixar-token"
