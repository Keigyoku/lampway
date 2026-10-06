# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where Lampway keeps the secrets it holds (connections_store.md section 6.2): the OS keyring first (service ``lampway``, user name
``<id>:<field>``, one entry per field), else one 0600 JSON file per connection in a 0700 directory outside the Lampway home.

The choice is made once, by a write-read-delete probe of a throwaway entry, and reported with its reason. A keyring that is locked
stays the keyring: a write is refused with the fix, never quietly sent to a file instead."""

import os
import secrets as _secrets
from pathlib import Path
from typing import Optional

from . import files as CF

SERVICE = "lampway"
LOCKED_TEXT = "your keyring is locked: unlock it and try again (nothing was saved)"


class StoreError(Exception):
    pass


class StoreLocked(StoreError):
    pass


def _fname(cid: str) -> str:
    return cid.replace(":", "_").replace("/", "_")


class MemoryStore:
    """For tests: holds values in this process only."""
    kind = "memory"

    def __init__(self):
        self.items: dict = {}

    def put(self, cid: str, fields: dict) -> None:
        self.items[cid] = dict(fields)

    def get(self, cid: str, field: str) -> Optional[str]:
        return (self.items.get(cid) or {}).get(field)

    def delete(self, cid: str, fields=()) -> None:
        self.items.pop(cid, None)


class KeyringStore:
    kind = "keyring"

    def __init__(self, backend):
        self.backend = backend

    def put(self, cid: str, fields: dict) -> None:
        import keyring.errors as KE
        written = []
        try:
            for name, value in fields.items():
                self.backend.set_password(SERVICE, f"{cid}:{name}", value)
                written.append(name)
        except KE.KeyringLocked:
            raise StoreLocked(LOCKED_TEXT) from None
        except KE.KeyringError as exc:
            for name in written:                                        # a pair is stored whole or not at all
                try:
                    self.backend.delete_password(SERVICE, f"{cid}:{name}")
                except KE.KeyringError:
                    pass
            raise StoreError(f"the keyring refused the write ({type(exc).__name__}): nothing was saved") from None

    def get(self, cid: str, field: str) -> Optional[str]:
        import keyring.errors as KE
        try:
            return self.backend.get_password(SERVICE, f"{cid}:{field}")
        except KE.KeyringLocked:
            raise StoreLocked("your keyring is locked: unlock it to use this key") from None
        except KE.KeyringError as exc:
            raise StoreError(f"the keyring could not be read ({type(exc).__name__})") from None

    def delete(self, cid: str, fields=()) -> None:
        import keyring.errors as KE
        for name in fields:
            try:
                self.backend.delete_password(SERVICE, f"{cid}:{name}")
            except KE.PasswordDeleteError:
                pass
            except KE.KeyringLocked:
                raise StoreLocked("your keyring is locked: unlock it and try again (nothing was removed)") from None


class FileStore:
    kind = "file"

    def __init__(self, directory):
        self.dir = Path(directory)

    def _path(self, cid: str) -> Path:
        return self.dir / f"{_fname(cid)}.json"

    def put(self, cid: str, fields: dict) -> None:
        CF.ensure_dir(self.dir)
        os.chmod(self.dir, 0o700)
        with CF.locked(self.dir / f"{_fname(cid)}.lock"):
            CF.atomic_write_json(self._path(cid), {"fields": dict(fields)})

    def get(self, cid: str, field: str) -> Optional[str]:
        try:
            data = CF.read_json(self._path(cid))
        except CF.Unreadable as exc:
            raise StoreError(f"the stored credential was unreadable and was set aside ({exc})") from None
        return (data.get("fields") or {}).get(field)

    def delete(self, cid: str, fields=()) -> None:
        with CF.locked(self.dir / f"{_fname(cid)}.lock"):
            try:
                os.unlink(self._path(cid))
            except FileNotFoundError:
                pass


def _usable_backend(backend) -> bool:
    mod = type(backend).__module__
    return not (mod.endswith("backends.fail") or mod.endswith("backends.null"))


def choose_store(secrets_dir, backend=None):
    """``(store, reason)``: the keyring when it has a real backend and a throwaway write-read-delete works; else the file store."""
    import keyring
    import keyring.errors as KE
    if backend is None:
        try:
            backend = keyring.get_keyring()
        except Exception as exc:  # noqa: BLE001 - any failure to load a backend means there is none
            return FileStore(secrets_dir), f"no keyring on this session ({type(exc).__name__}): keys are kept in a file only you can read"
    if not _usable_backend(backend):
        return FileStore(secrets_dir), "no keyring (Secret Service) on this session: keys are kept in a file only you can read"
    probe = f"lampway-probe-{_secrets.token_hex(4)}"
    try:
        backend.set_password(SERVICE, probe, "probe")
        ok = backend.get_password(SERVICE, probe) == "probe"
        backend.delete_password(SERVICE, probe)
    except KE.KeyringLocked:
        return KeyringStore(backend), "the OS keyring (locked: unlock it to save or use a key)"
    except Exception as exc:  # noqa: BLE001 - a backend that cannot hold a value is no keyring
        return FileStore(secrets_dir), f"the keyring did not work on this session ({type(exc).__name__}): keys are kept in a file only you can read"
    if not ok:
        return FileStore(secrets_dir), "the keyring did not return what was written: keys are kept in a file only you can read"
    return KeyringStore(backend), "the OS keyring"
