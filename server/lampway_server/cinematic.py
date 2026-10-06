"""cinematic_shot_plan: reference blockout to AI cinematic as a typed plan (specs/wiki/cinematic_shot_plan.md). Pure python; the catalogue is injected.

One action and one camera move per shot (the wiki's rule, checked on the words: a second clause joined by and / then / a comma is refused). Each shot gets
the wiki's prompt template filled in, five stages (playblast_capture, render_condition_passes, image_edit, video_generate, frame_review) and a price for the
video stage read from the model's own pricing_skus (``videogen.estimate``; an unknown family stays unknown, never guessed). Nothing is generated here: the
image edit and the video are needs_approval cards (the user's click confirms them in the Client), and the shortest shot is named first, the cheapest test.
A failing shot is split into two shorter ones; reviews are typed (identity, doubling, action_order, camera) and say what to do next.
Storage: <root>/cinematics/<scene>/plan.json."""

import json
import re
import time
from pathlib import Path

from . import videogen as VG

STAGES = ("playblast_capture", "render_condition_passes", "image_edit", "video_generate", "frame_review")
REVIEW_KEYS = ("identity", "doubling", "action_order", "camera")
HF_PREFIX = "higgsfield/"
_SECOND_CLAUSE = re.compile(r"\b(and|then|while|before|after)\b|[,;&+]", re.I)
TEMPLATE = ("Using the supplied start{end_frame} frame, preserve {landmarks}{prop}. During this {duration:g} s shot, {action}. Camera: {camera}. "
            "End with {end}. Keep the same costume and object count.")


class ShotError(ValueError):
    pass


def _dir(root, scene) -> Path:
    if not re.match(r"^[A-Za-z0-9_\-]{1,64}$", str(scene or "")):
        raise ShotError("scene is a plain name: letters, digits, - and _")
    return Path(root) / "cinematics" / str(scene)


def _one(label, text, sid):
    text = str(text or "").strip()
    if not text or _SECOND_CLAUSE.search(text):
        raise ShotError(f"shot {sid!r}: one action and one camera move per shot ({label} {text!r}); split it into two shots")
    return text


def _refs(refs) -> str:
    out = []
    for r in refs or []:
        text = r.get("text") if isinstance(r, dict) else None
        if not text or not (re.search(r"\bleft\b", text, re.I) and re.search(r"\bright\b", text, re.I)):
            path = r.get("path") if isinstance(r, dict) else r
            raise ShotError(f"character reference {path!r} needs its wearer-left/right text (which side carries what), or the model may mirror the armour: "
                            "give [{path, text}]")
        out.append(text.strip().rstrip("."))
    if not out:
        raise ShotError("give the character references with their wearer-left/right text: [{path, text}]")
    return "; ".join(out)


def _shot(s) -> dict:
    sid = str(s.get("id") or "").strip()
    if not re.match(r"^[A-Za-z0-9_\-]{1,32}$", sid):
        raise ShotError("each shot has an id (letters, digits, - and _)")
    dur = s.get("duration_s")
    if not isinstance(dur, (int, float)) or isinstance(dur, bool) or not 1 <= dur <= 30:
        raise ShotError(f"shot {sid!r}: duration_s is 1..30 seconds")
    return {"id": sid, "action": _one("action", s.get("action"), sid), "camera": _one("camera", s.get("camera"), sid), "duration_s": dur,
            "end": str(s.get("end") or "").strip() or "the same pose", "start": s.get("start"), "prop": s.get("prop"), "reviews": []}


def _price(model, catalogue, duration):
    if str(model).startswith(HF_PREFIX):
        return {"estimate_usd": None, "known": False, "state": "needs_approval", "basis": "Higgsfield credits are read back at the confirm (get_cost), not estimated here"}
    if catalogue is None:
        return {"estimate_usd": None, "known": False, "state": "needs_key", "basis": "no OpenRouter video catalogue: add the key, then plan again"}
    est = VG.estimate(catalogue.model(model), {"duration": duration, "frames": 1})
    return {"estimate_usd": None if est["usd"] is None else round(est["usd"], 4), "known": est["known"], "state": "needs_approval", "basis": est["basis"]}


def _prompt(s, landmarks) -> str:
    return TEMPLATE.format(end_frame=" and end" if s.get("end_frame") else "", landmarks=landmarks, prop=f" and {s['prop']}" if s.get("prop") else "",
                           duration=s["duration_s"], action=s["action"], camera=s["camera"], end=s["end"])


def _price_all(rec, catalogue):
    total, known = 0.0, True
    for s in rec["shots"]:
        s["prompt"] = _prompt(s, rec["landmarks"])
        s["video"] = _price(rec["model"], catalogue, s["duration_s"])
        s["stages"] = [{"stage": st, "state": "needs_approval" if st in ("image_edit", "video_generate") else "ready"} for st in STAGES]
        known = known and s["video"]["known"]
        total += s["video"]["estimate_usd"] or 0.0
    rec["price_known"] = known
    rec["total_video_usd"] = round(total, 4) if known else None
    rec["first_shot"] = min(rec["shots"], key=lambda s: (s["duration_s"], rec["shots"].index(s)))["id"]
    return rec


def _save(root, scene, rec) -> dict:
    d = _dir(root, scene)
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def _load(root, scene) -> dict:
    p = _dir(root, scene) / "plan.json"
    if not p.exists():
        raise ShotError(f"no plan for scene {scene!r}: plan it first")
    return json.loads(p.read_text(encoding="utf-8"))


def plan(root, scene, shots, character_refs, model, catalogue) -> dict:
    _dir(root, scene)
    if not shots:
        raise ShotError("give the shot list: [{id, action (one verb), camera (one move), duration_s, end}]")
    rows = [_shot(s) for s in shots]
    if len({r["id"] for r in rows}) != len(rows):
        raise ShotError("shot ids are unique")
    if not str(model or "").strip():
        raise ShotError("name the video model (lampway_video_models lists them)")
    rec = {"scene": scene, "model": model, "landmarks": _refs(character_refs), "refs": [r.get("path") for r in character_refs], "shots": rows,
           "planned": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "note": "a plan only: the image edit and the video are needs_approval (the user confirms each spend in the Client); nothing was generated"}
    return _save(root, scene, _price_all(rec, catalogue))


def split(root, scene, shot_id, actions, catalogue, durations=None) -> dict:
    rec = _load(root, scene)
    i = next((k for k, s in enumerate(rec["shots"]) if s["id"] == shot_id), None)
    if i is None:
        raise ShotError(f"no shot {shot_id!r}; the shots are {[s['id'] for s in rec['shots']]}")
    if not isinstance(actions, list) or len(actions) != 2:
        raise ShotError("a split takes two actions: [first, second]")
    s = rec["shots"][i]
    d = durations or [s["duration_s"] / 2, s["duration_s"] / 2]
    if len(d) != 2 or abs(sum(d) - s["duration_s"]) > 1e-6:
        raise ShotError(f"the two durations add up to the shot's {s['duration_s']} s")
    a = _shot({"id": f"{shot_id}a", "action": actions[0], "camera": s["camera"], "duration_s": d[0], "end": "mid-action", "start": s.get("start"), "prop": s.get("prop")})
    b = _shot({"id": f"{shot_id}b", "action": actions[1], "camera": s["camera"], "duration_s": d[1], "end": s["end"], "start": f"the end frame of {shot_id}a",
               "prop": s.get("prop")})
    rec["shots"][i:i + 1] = [a, b]
    rec.setdefault("splits", []).append({"shot": shot_id, "into": [a["id"], b["id"]], "when": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return _save(root, scene, _price_all(rec, catalogue))


def review(root, scene, shot_id, review, by="agent", note="") -> dict:
    rec = _load(root, scene)
    s = next((x for x in rec["shots"] if x["id"] == shot_id), None)
    if s is None:
        raise ShotError(f"no shot {shot_id!r}")
    if not isinstance(review, dict) or set(review) != set(REVIEW_KEYS) or any(v not in ("pass", "fail") for v in review.values()):
        raise ShotError(f"a review is pass | fail for each of {', '.join(REVIEW_KEYS)}")
    if by not in ("captain", "agent"):
        raise ShotError("by is captain | agent")
    failed = [k for k in REVIEW_KEYS if review[k] == "fail"]
    decision = "chain" if not failed else "split" if failed == ["action_order"] else "redo"
    nxt = ("chain the next shot from this one's last frame" if decision == "chain" else
           "split the action into two shorter shots (split)" if decision == "split" else
           f"redo with a simpler instruction; failed: {', '.join(failed)} (identity: check the wearer-left/right text and the reference)")
    s.setdefault("reviews", []).append({"review": review, "by": by, "decision": decision, "note": str(note), "when": time.strftime("%Y-%m-%dT%H:%M:%S")})
    _save(root, scene, rec)
    return {"shot": shot_id, "decision": decision, "next": nxt, "failed": failed}
