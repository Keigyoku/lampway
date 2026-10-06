"""The seam: what a compute backend adapter provides. Adapters are thin; all policy lives in the runner."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


class ComputeError(Exception):
    pass


class Unknown(ComputeError):
    """The outcome is not known (a transport timeout, a lost response). Never retried."""


class Rejected(ComputeError):
    """The provider refused the request: nothing was created or billed."""


@dataclass
class Quote:
    backend: str
    hardware: str
    rate_usd_per_s: float
    max_seconds: int
    setup_seconds_max: int
    upper_bound_usd: float
    basis: str                  # measured | documented | assumed
    ttl_seconds: int


@dataclass
class PrivacyDeclaration:
    cls: str                    # ephemeral_verified | conditional | retains | unknown
    evidence: str
    conditions: tuple = ()
    conditions_met: bool = True
    reason: str = ""


@dataclass
class OwnedResource:
    ref: str
    name: str
    key: Optional[str]
    state: str
    since: float
    rate_usd_per_s: float = 0.0
    billing: bool = True


@dataclass
class Recipe:
    id: str
    version: str
    hardware_gpu: str = "none"
    setup_seconds_max: int = 60
    outputs: tuple = ("result.json",)
    no_payload_logging: bool = True
    entry: str = ""
    setup: str = ""
    type: str = "default"
    image_digest: str = ""
    files: tuple = ()                 # ((name, source path), ...) staged next to the inputs
    params_file: str = ""             # the job params are staged as this JSON file
    outputs_by_param: tuple = ()      # (param name, ((value, (extra outputs...)), ...))


_SECRET = [(re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "[redacted]"), (re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^/\s:@]+:[^/\s@]+@"), "https://"), (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer [redacted]"),
           (re.compile(r"(?i)(ghp_|AKIA|AIza)[A-Za-z0-9_\-]{8,}"), "[redacted]"), (re.compile(r"(?i)(key|token|secret|signature|password)=([^&\s]+)"), r"\1=[redacted]")]


def sanitize(text) -> str:
    """Provider error text never reaches a receipt, ledger row or log with a credential in it."""
    s = str(text)
    for pat, rep in _SECRET:
        s = pat.sub(rep, s)
    return s[:600]
