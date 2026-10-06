# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The bounded retry ladder of view_verify (specs/mrmak/07-view-verify.md section 6.4): a pure, total function. Its ceiling cannot be bypassed by any other state: a history that has reached
``max_attempts`` never gets ``retry`` or ``generate`` back, and the ladder never calls a generator itself (it returns the next prompt; the caller's spend gate applies). The shape follows the
vendored correction loop's fixed stop priority; the code is new."""

MAX_ATTEMPTS = 3
STOP_OPTIONS = ("accept the best attempt with a warning", "give custom instructions and retry once more", "skip this part")


def escalate(original_prompt: str, reason: str, rotation_deg=None) -> str:
    """The correction block names the failure and the signed estimated rotation; the original text follows unchanged."""
    block = f"[CRITICAL CORRECTION] The previous attempt failed strict-front verification: {reason}."
    if rotation_deg is not None:
        block += f" Estimated rotation: {float(rotation_deg):+.0f}° off dead-front."
    return block + "\n\n" + original_prompt


def decide(history, max_attempts: int = MAX_ATTEMPTS) -> dict:
    """history: [{verdict: pass|soft_fail|hard_fail|uncertain, reason, model}]. Priority: pass -> accept; soft_fail -> accept_with_warning; the ceiling -> stop; the same failure twice in a row -> stop;
    otherwise retry (the first retry on the same model, the second on the fallback)."""
    if not 1 <= int(max_attempts) <= 4:
        raise ValueError("max_attempts is 1..4")
    used = len(history)
    base = {"attempts_used": used, "max_attempts": int(max_attempts)}
    if used == 0:
        return {**base, "action": "generate", "model": "primary", "reason": "first attempt"}
    last = history[-1]
    verdict = last.get("verdict")
    if verdict == "pass":
        return {**base, "action": "accept", "reason": "passed the checks"}
    if verdict == "soft_fail":
        return {**base, "action": "accept_with_warning", "reason": f"accepted with a warning: {last.get('reason', '')}"}
    if used >= int(max_attempts):
        return {**base, "action": "stop", "reason": f"stopped after {used} attempts: choose accept-best, a custom instruction (one more), or skip; no further generation without your answer", "options": list(STOP_OPTIONS)}
    if used >= 2 and history[-2].get("verdict") == "hard_fail" and verdict == "hard_fail" and history[-2].get("reason") == last.get("reason"):
        return {**base, "action": "stop", "reason": f"the same failure twice in a row ({last.get('reason')}): the ladder stops", "options": list(STOP_OPTIONS)}
    return {**base, "action": "retry", "model": "same" if used == 1 else "fallback", "reason": last.get("reason", ""), "escalate": True}
