"""ask_user's batch and the answers the real client sends (specs/mixar_docs/agent_plan_questions.md).

A batch is 2..4 questions, each with options: exactly the shape the client's batched_choice.is_valid_batch accepts; any other shape the
client silently drops (store_batch clears it), so it is refused to the model here instead of shown as a wizard that never draws. The client
answers a batch once, with the complete map (chat_special_ops: action 'submit', answers {question: option}); its Cancel button is the value
``abort``; a click on a single choice card sends the option's value as ``action`` with empty text (the generic slot dispatch)."""

import json

CANCEL = "abort"                    # batched_choice.CANCEL_ACTION
RETRY_ACTION = "retry_failed_tasks"  # chat_special_ops / retry_action: the post-turn chip
RETRY_LABEL = "Retry failed tasks"
CONTINUE_MESSAGE = "continue"        # parked_resume.CONTINUE_MESSAGE: what the chip sends
TRANSPORT_ACTIONS = {"", "respond", "submit"}


def batch_error(args: dict):
    """None when the call is a valid single question or batch; else the refusal the model is shown."""
    questions = args.get("questions")
    if questions is None:
        return None if str(args.get("question") or "").strip() else "ask_user needs `question` (or `questions` for a batch of 2 to 4)"
    if args.get("question"):
        return "ask_user takes `question` OR `questions`, not both"
    if not isinstance(questions, list) or not 1 < len(questions) <= 4:
        return "a batch is 2 to 4 questions: ask one at a time otherwise"
    for i, q in enumerate(questions, 1):
        if not (isinstance(q, dict) and isinstance(q.get("question"), str) and q["question"].strip()):
            return f"batch question {i} needs a non-empty `question`"
        opts = q.get("options")
        if not (isinstance(opts, list) and [o for o in opts if str(o).strip()]):
            return f"batch question {i} ({q['question']!r}) needs `options`: the client's wizard shows a batch only as choices; ask a free-text question on its own"
    if len({q["question"].strip() for q in questions}) != len(questions):
        return "the questions of a batch must differ: the answers come back keyed by question"
    return None


def clean_batch(questions: list) -> list:
    return [{"question": q["question"].strip(), "options": [str(o).strip() for o in q["options"] if str(o).strip()][:6]} for q in questions]


def batch_answer(batch: list, answers):
    """(tool-result JSON, None) for a complete map, or (None, refusal) for a partial or unknown one."""
    if not isinstance(answers, dict):
        return None, "a batch is answered with the complete map {question: answer}"
    missing = [q["question"] for q in batch if q["question"] not in answers]
    if missing:
        return None, "answer every question of the batch together; missing: " + "; ".join(missing)
    return json.dumps({q["question"]: answers[q["question"]] for q in batch}, ensure_ascii=False), None


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
