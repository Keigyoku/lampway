# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The composer's route line in the island (facelift contract 04): the status timer writes it into the WindowManager,
where the native Send reads it (agent_ui_state.cc). No bpy here: ``sync`` is given the window manager and scene."""

from . import statusbar_state as S
from .route_line import OFF, route_line

# Every message carries the typed text and the scene context the agent reads (object names and transforms).
BASE_CONTENT = {"text": True, "names": True, "transforms": True}


def _catalog_cost(key):
    from mixar.bootstrap.generation_catalog_cache import get_credit_cost
    return get_credit_cost(key)


def sync(wm, scene) -> dict:
    images = len(getattr(scene, "mixie_chat_pending_attachments", None) or [])
    line = route_line(S.STATE.get("provider") or "", S.STATE["egress"] if S.STATE["ok"] else None,
                      dict(BASE_CONTENT, images=images))
    table = estimates(_catalog_cost)
    for key, value in (("lampway_chat_route_host", line["host"]), ("lampway_chat_route_tip", line["tooltip"]),
                       ("lampway_chat_send_ok", line["send_ok"]), ("lampway_generate_estimates", table)):
        if getattr(wm, key, None) != value:
            setattr(wm, key, value)
    return line


GENERATE_TYPES = ("image_gen", "model_3d")   # the empty state's prompts that switch to GENERATE (mixie_chat_empty_state.cc)


def estimates(cost_of) -> str:
    """'image_gen=≈ 30 credits est.;...' for the types whose cost the generation catalogue knows (``cost_of(key)``)."""
    from .price_chips import chip
    out = []
    for key in GENERATE_TYPES:
        try:
            cost = cost_of(key)
        except Exception:  # noqa: BLE001  (an unknown cost is said as unknown, by the C++ side)
            cost = None
        if cost is not None:
            out.append(f"{key}={chip({'price': {'kind': 'estimate', 'amount': cost, 'unit': 'credits'}})['text']}")
    return ";".join(out)


def refusal(context):
    """The message Send refuses with when the agent's provider route is off, else None."""
    if getattr(getattr(context, "window_manager", None), "lampway_chat_send_ok", True) is False:
        return OFF
    return None
