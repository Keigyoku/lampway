"""The voice slot: ``dictation`` is the shipped path (energy gate then an audio-input model, feeding the text chat); ``live`` (a realtime voice API) would need an API key billed apart from a
ChatGPT plan, which sits against the stated rule that inference runs on the user's own plans, so it is a stub that returns needs_decision and nothing else."""


def transport(kind: str) -> dict:
    if kind == "none":
        return {"state": "off"}
    if kind == "dictation":
        return {"state": "shipped", "path": "dictation.py: energy gate, then an audio-input model on the spend ledger, into the text chat"}
    if kind == "live":
        return {"state": "needs_decision", "question": "Is any realtime voice provider acceptable under the plan-only rule, or are dictation plus text the stopping point?",
                "reason": "a realtime voice API is billed by API key, apart from a ChatGPT or Claude plan"}
    raise ValueError("voice transport is none | dictation | live")
