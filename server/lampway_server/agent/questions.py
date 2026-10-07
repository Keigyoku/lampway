"""The island's answer to a question from the pane's Hermes (``clarify`` or a permission card, docs/reports/agent-modes-spec.md A2),
in the shapes the real client sends (specs/mixar_docs/agent_plan_questions.md).

The client answers with ``agent.input`` {action, text, answers, interrupt_id}: typed text, a list or map of picked answers, or (a
click on a single choice card, the generic slot dispatch) the option's value as ``action`` with empty text. Hermes asks one
question at a time; the batched ``ask_user`` wizard was the built-in loop's and went with it (A5)."""

import json

TRANSPORT_ACTIONS = {"", "respond", "submit"}


def single_answer(text, answers, action) -> str:
    text = (text or "").strip()
    if text:
        return text
    if isinstance(answers, list) and answers:
        return ", ".join(str(a) for a in answers)
    if isinstance(answers, dict) and answers:
        return json.dumps(answers, ensure_ascii=False)
    if isinstance(action, str) and action.strip() not in TRANSPORT_ACTIONS:
        return action.strip()
    return "(no answer)"
