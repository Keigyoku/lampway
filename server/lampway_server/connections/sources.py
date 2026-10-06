# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where a credential can come from (CONNECTIONS.md section 4), and the ``Credential`` a consumer gets at the moment of use.

Detection reads presence only: an environment variable's membership, a file's existence and mode, a binary on PATH. A value is read
only when a credential is resolved for use (or a pointer's shape is checked when the user names it), and it is registered with the
log redactor before anyone receives it. The parsing of each source is the code that parsed it before Connections existed: a dotenv
line or a bare key (``openrouter.py``), an owner-only ``<NAME>_FILE`` (``studios/rest/client.py``), the ``Bearer``/``Key`` prefix
strip (``fal.py``), and Hi3D's one file with two lines."""

import base64
import hashlib
import json
import os
import shutil
import stat
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .. import logredact

AUTO_ORDER = ("env", "pointer", "manual", "signin", "host")
MODES = ("auto",) + AUTO_ORDER


class SourceError(Exception):
    """A source exists but cannot be used; the text is the fix."""


@dataclass
class Source:
    mode: str
    label: str
    detail: str
    present: bool = True
    from_env: bool = False                    # set in the server's environment: C3, it wins over the chosen source
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)
    reader: Optional[Callable[[], dict]] = None
    sig: Optional[str] = None                 # what a check was about, known WITHOUT reading a file: a value's hash in memory, a file's stat

    def values(self) -> dict:
        if self.error:
            raise SourceError(self.error)
        return self.reader() if self.reader else {}

    def public(self) -> dict:
        return {"mode": self.mode, "present": self.present, "label": self.label, "detail": self.detail, **self.extra}


# ------------------------------------------------------------------------------------------------------------- reading files
def owner_only_problem(path: Path) -> Optional[str]:
    try:
        st = path.stat()
    except FileNotFoundError:
        return f"{path} does not exist"
    except OSError:
        return f"{path} could not be read"
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        return f"{path} must be owner-only (chmod 600)"
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        return f"{path} must be owner-only (chmod 600)"
    return None


def _strip(value: str, scheme: str) -> str:
    value = value.strip().strip("\"'")
    if scheme == "key":
        for prefix in ("Bearer ", "Key "):
            if value.startswith(prefix):
                value = value[len(prefix):].strip()
    return value


def parse_key_text(text: str, names: tuple, scheme: str = "bearer", json_field: Optional[str] = None) -> Optional[str]:
    """A key from a file's text: a JSON field when named, a dotenv line ``NAME=value`` for one of ``names``, or one bare line."""
    if json_field:
        try:
            data = json.loads(text)
        except ValueError:
            return None
        value = data.get(json_field) if isinstance(data, dict) else None
        return _strip(value, scheme) if isinstance(value, str) and value.strip() else None
    for line in text.splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip().removeprefix("export ").strip() in names:
            return _strip(value, scheme) or None
    bare = text.strip()
    if bare and "\n" not in bare and "=" not in bare:
        return _strip(bare, scheme)
    return None


def read_key_file(path: Path, names: tuple, scheme: str = "bearer", json_field: Optional[str] = None) -> str:
    problem = owner_only_problem(path)
    if problem:
        raise SourceError(problem)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise SourceError(f"{path} could not be read") from None
    value = parse_key_text(text, names, scheme, json_field)
    if not value:
        raise SourceError(f"{path} does not hold a key in a shape Lampway reads (a bare key, a line {names[0] if names else 'NAME'}=..., or a JSON field)")
    return value


# ------------------------------------------------------------------------------------------------------------- the credential
_VALUES: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


class Credential:
    """One connection's secret at the moment of use. It never shows its value: no repr, no str, no pickling, no JSON, no attribute."""
    __slots__ = ("id", "source", "_spec", "_oauth", "__weakref__")

    def __init__(self, spec, source_mode: str, values: Optional[dict] = None, oauth=None):
        self.id, self.source, self._spec, self._oauth = spec.id, source_mode, spec, oauth
        clean = {k: v for k, v in (values or {}).items() if v}
        for v in clean.values():
            logredact.register_secret(v)
        if spec.scheme == "basic" and len(clean) == 2:
            logredact.register_secret(base64.b64encode(":".join(clean[f] for f in spec.fields).encode()).decode())
        _VALUES[self] = clean

    def __repr__(self) -> str:
        return f"<Credential {self.id} from {self.source}>"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("a Credential cannot be pickled")

    def __getstate__(self):
        raise TypeError("a Credential cannot be pickled")

    def headers(self) -> dict:
        v = _VALUES.get(self) or {}
        scheme = self._spec.scheme
        if self._oauth is not None:
            token = self._oauth._access_token_sync()
            logredact.register_secret(token)
            return {"Authorization": f"Bearer {token}"}
        if scheme == "x-api-key":
            return {"x-api-key": v["key"]}
        if scheme == "key":
            return {"Authorization": f"Key {v['key']}"}
        if scheme == "modal":
            return {"Modal-Key": v["token_id"], "Modal-Secret": v["token_secret"]}
        if scheme == "basic":
            pair = base64.b64encode(f"{v['client_id']}:{v['client_secret']}".encode()).decode()
            return {"Authorization": f"Basic {pair}"}
        return {"Authorization": f"Bearer {v['key']}"} if v.get("key") else {}

    def env(self) -> dict:
        """The value(s) under the one variable name each a child reads (``MESHY_API_KEY``), for exactly one child process."""
        v = _VALUES.get(self) or {}
        names = self._spec.child_env_names()
        return {names[f]: v[f] for f in names if v.get(f)}


def secret_of(cred: Credential, field: str = "key") -> str:
    """The one internal door to a raw value, for the in-process transport adapters (the redactor has already seen it)."""
    return (_VALUES.get(cred) or {}).get(field, "")


def fingerprint(values: dict, lampway_held: bool) -> dict:
    joined = "\0".join(values[k] for k in sorted(values))
    out = {"sha8": hashlib.sha256(joined.encode()).hexdigest()[:8]}
    last = values[sorted(values)[-1]] if values else ""
    if lampway_held and len(last) >= 20:                          # 16 characters stay hidden
        out["last4"] = last[-4:]
    return out


# ------------------------------------------------------------------------------------------------------------- detection
def _stat_sig(path: Path) -> Optional[str]:
    try:
        st = path.stat()
    except OSError:
        return None
    return f"{st.st_mtime_ns}:{st.st_size}"


def _env_source(spec, env) -> Optional[Source]:
    found, names = {}, []
    for f in spec.fields:
        name = next((n for n in spec.env.get(f, ()) if (env.get(n) or "").strip()), None)
        if name is None:
            return None
        found[f] = _strip(env[name], spec.scheme)
        names.append(name)
    if not found:
        return None
    return Source("env", f"{' + '.join(names)} from the environment", ", ".join(names), from_env=True, reader=lambda: dict(found),
                  sig=fingerprint(found, False)["sha8"])


def _env_file_source(spec, env) -> Optional[Source]:
    named = {f: next((n for n in spec.file_env.get(f, ()) if env.get(n)), None) for f in spec.fields}
    if not spec.fields or not any(named.values()):
        return None
    first = next(n for n in named.values() if n)
    path = Path(env[first]).expanduser()

    def read() -> dict:
        if spec.id == "studio:hi3d" and named.get("client_id") and not named.get("client_secret"):
            problem = owner_only_problem(path)
            if problem:
                raise SourceError(problem)
            lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if len(lines) != 2:
                raise SourceError(f"{path} must hold the client id and the secret on two lines")
            return {"client_id": lines[0], "client_secret": lines[1]}
        out = {}
        for f in spec.fields:
            n = named.get(f)
            if n is None:
                raise SourceError(f"{spec.label} needs {' and '.join(spec.file_env[x][0] for x in spec.fields)}")
            out[f] = read_key_file(Path(env[n]).expanduser(), spec.env.get(f, ()), spec.scheme)
        return out

    error = owner_only_problem(path)
    names = ", ".join(n for n in named.values() if n)
    return Source("pointer", f"the file {names} names", f"{names} -> {path}", from_env=True, error=error,
                  extra={"mode_ok": error is None or "chmod" not in error}, reader=read, sig=_stat_sig(path))


def _record_pointer(spec, rec, env) -> Optional[Source]:
    ptr = rec.get("pointer")
    if not ptr or not spec.fields:
        return None
    if ptr.get("env"):
        name = ptr["env"]
        if not (env.get(name) or "").strip():
            return Source("pointer", f"{name} (your pointer)", name, present=False,
                          error=f"the environment of the Lampway server has no {name}: set it before starting Lampway, or paste the key instead")
        value = _strip(env[name], spec.scheme)
        return Source("pointer", f"{name} (your pointer)", name, reader=lambda: {spec.fields[0]: value}, sig=fingerprint({"k": value}, False)["sha8"])
    path = Path(ptr["path"]).expanduser()
    error = owner_only_problem(path)
    return Source("pointer", f"the file {path} (your pointer)", str(path), error=error, extra={"mode_ok": error is None or "chmod" not in error},
                  reader=lambda: {spec.fields[0]: read_key_file(path, spec.env.get(spec.fields[0], ()), spec.scheme, ptr.get("field"))},
                  sig=_stat_sig(path))


def _which(binary: str, which: Callable, home: Path) -> Optional[str]:
    if binary.startswith("~/"):
        p = home / binary[2:]
        return str(p) if p.is_file() and os.access(p, os.X_OK) else None
    return which(binary)


def detect(spec, rec: dict, env, store, oauth, which: Callable = shutil.which, home: Optional[Path] = None) -> list:
    """Every source of this connection, in the auto order, each with its presence (no value is read here)."""
    home = Path(home or Path.home())
    out = []
    s = _env_source(spec, env)
    if s:
        out.append(s)
    for s in (_env_file_source(spec, env), _record_pointer(spec, rec, env)):
        if s:
            out.append(s)
    manual = rec.get("manual")
    if manual:
        kind = manual.get("store")
        if store is not None and kind != store.kind:
            out.append(Source("manual", f"your key in the {kind}", kind,
                              error=f"the key was saved in the {kind}, which is not the store in use now ({store.kind}): unlock or restore it, or paste the key again"))
        else:
            out.append(Source("manual", f"your key in the {'keyring' if kind == 'keyring' else kind + ' store'}", kind,
                              reader=lambda: {f: store.get(spec.id, f) for f in manual.get("fields", spec.fields)},
                              sig=(manual.get("fingerprint") or {}).get("sha8")))
    if oauth is not None:
        st = oauth.status()
        out.append(Source("signin", "your sign-in", spec.label, present=bool(st.get("signed_in")), extra={"set_up": bool(st.get("client_id"))},
                          sig="signin"))
    for b in spec.binary:
        found = _which(b, which, home)
        out.append(Source("host", f"the {Path(b).name} login on this machine", Path(b).name, present=bool(found), sig="host"))
        break
    if spec.kind == "browser_session":
        prof = home / spec.paths[0][2:]
        out.append(Source("host", "the tool browser's profile", str(prof), present=prof.is_dir(), sig="host"))
    return out


def host_paths(spec, home: Path) -> list:
    """The registry's host files: exists and mode only, never opened."""
    rows = []
    for p in spec.paths:
        full = home / p[2:] if p.startswith("~/") else Path(p)
        try:
            st = full.stat()
            rows.append({"path": p, "exists": True, "owner_only": not (st.st_mode & (stat.S_IRWXG | stat.S_IRWXO))})
        except OSError:
            rows.append({"path": p, "exists": False})
    return rows
