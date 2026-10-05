# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A file-backed keyring for the Lampway profile (``PYTHON_KEYRING_BACKEND=
mixar.modules.lampway_tools.keyring_file.FileKeyring``).

Why: the client keeps its login pair in the OS keyring; on a machine with no Secret Service (a box, a VM, a
virtual display) every store fails and the login never persists, and on a desktop the pair would land in the
wallet next to the user's other credentials. This backend keeps Lampway's pair in ``<lampway home>/keyring.json``
(0600, in a 0700 directory). That is weaker than an OS wallet: anything running as the user can read it. The
launcher selects it; a user who prefers the OS keyring simply does not set the variable.
"""

import json
import os
import tempfile
from pathlib import Path

from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from .settings import lampway_home


def keyring_path() -> Path:
    override = os.environ.get("LAMPWAY_KEYRING_FILE")
    return Path(override) if override else lampway_home() / "keyring.json"


class FileKeyring(KeyringBackend):
    priority = 1

    def _read(self) -> dict:
        try:
            data = json.loads(keyring_path().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        path = keyring_path()
        created = not path.parent.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        if created:                                          # only a directory we made: never chmod /tmp
            os.chmod(path.parent, 0o700)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".kr")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def get_password(self, service, username):
        return self._read().get(service, {}).get(username)

    def set_password(self, service, username, password):
        data = self._read()
        data.setdefault(service, {})[username] = password
        self._write(data)

    def delete_password(self, service, username):
        data = self._read()
        if username not in data.get(service, {}):
            raise PasswordDeleteError("password not found")
        del data[service][username]
        if not data[service]:
            del data[service]
        self._write(data)
