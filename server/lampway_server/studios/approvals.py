# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Approvals: the one way a Studio action that spends credits runs.

An approval is created by a PLAN (a read back that spent nothing) and carries the price Studio showed. Only the USER can confirm
it, from the Client, by acknowledging that price; it is single-use and expires. An agent or a swarm worker never confirms: the
service takes ``by`` from the route that called it (the Client's REST route says ``captain``; no agent tool has a confirm path).
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

TTL_S = 600.0


class ApprovalError(RuntimeError):
    pass


@dataclass
class Approval:
    id: str
    action: str
    studio: str
    label: str
    args: dict
    price: float
    settings: dict
    requested_by: str
    created: float
    expires: float
    state: str = "pending"            # pending | used | rejected
    confirmed_by: str = ""
    job_id: str = ""
    answer: object = None

    def public(self, now: float) -> dict:
        state = "expired" if self.state == "pending" and now >= self.expires else self.state
        return {"id": self.id, "action": self.action, "studio": self.studio, "label": self.label, "price": self.price,
                "settings": self.settings, "requested_by": self.requested_by, "state": state, "expires": self.expires,
                "job_id": self.job_id}


class Approvals:
    def __init__(self, now, ttl: float = TTL_S):
        self._now, self._ttl = now, ttl
        self._items: dict[str, Approval] = {}

    def propose(self, *, action, studio, label, args, price, settings, requested_by) -> Approval:
        t = self._now()
        a = Approval(uuid.uuid4().hex[:12], action, studio, label, args, float(price), settings, requested_by, t, t + self._ttl)
        self._items[a.id] = a
        return a

    def get(self, approval_id: str) -> Approval:
        a = self._items.get(approval_id)
        if a is None:
            raise ApprovalError(f"no approval {approval_id!r}")
        return a

    def confirm(self, approval_id: str, price, by: str, answer=None) -> Approval:
        if by != "captain":
            raise ApprovalError("only the user can confirm a spend, from the Client; an agent or a worker never can")
        a = self.get(approval_id)
        if a.state == "used":
            raise ApprovalError(f"approval {a.id} is already used")
        if a.state == "rejected":
            raise ApprovalError(f"approval {a.id} was rejected")
        if self._now() >= a.expires:
            raise ApprovalError(f"approval {a.id} expired: ask for the plan again so the price is read back fresh")
        if a.settings.get("unit") == "answer" and answer is None:
            raise ApprovalError("an answer is required: this is a question for the user, not a spend")
        try:
            wrong = abs(float(price) - a.price) > 1e-6
        except (TypeError, ValueError):
            wrong = True
        if wrong:
            raise ApprovalError(f"the price shown was {a.price}, not {price}: nothing was confirmed")
        a.state, a.confirmed_by, a.answer = "used", by, answer
        return a

    def reject(self, approval_id: str, by: str) -> Approval:
        if by != "captain":
            raise ApprovalError("only the user can reject an approval")
        a = self.get(approval_id)
        if a.state == "pending":
            a.state = "rejected"
        return a

    def all(self) -> list:
        return list(self._items.values())
