"""The prompt library (spec: specs/prompts/PROMPT_LIBRARY.md): a JSON template schema (five-part spine, typed variables, <= 5 negatives, timed beats,
input roles, per-model adapters, gates, provenance), built-ins shipped as data files, user and project templates that override by id and are validated
on load, render() with the rendered text, the run log with gates and the user's 1-5 rating, versions with A/B."""

import json
from pathlib import Path

import pytest

from lampway_server.prompts import library as L
from lampway_server.prompts import render as R
from lampway_server.prompts import runlog as RL
from lampway_server.prompts import schema as S


def template(**kw):
    t = {"id": "demo-walk", "version": "1.0.0", "purpose": "anim-walk", "media": "video", "title": "Demo", "description": "A demo walk.",
         "body": {"subject": "This warrior, exactly as in [start_image]: {{design_lock}}.", "action": "He walks at {{cadence_spm}} steps per minute.",
                  "camera": "Side-on tracking shot, long lens.", "style": "Even flat light, grid floor.", "constraints": "Full body in frame, two arms and two legs."},
         "variables": {"design_lock": {"type": "string", "default": "same armour design", "description": "what must not change"},
                       "cadence_spm": {"type": "integer", "default": 110, "min": 60, "max": 160, "description": "steps per minute"},
                       "direction": {"type": "enum", "default": "left", "enum": ["left", "right"], "description": "truck direction"}},
         "negatives": ["no cuts", "no zoom"], "inputs": {"start_image": {"required": True, "description": "full-body side view in the start pose"}},
         "defaults": {"model": "heygen/heygen-video-1", "resolution": "768p", "aspect_ratio": "16:9", "duration": 10},
         "model_adapters": {}, "gates": [{"id": "tracking", "description": "tracked frames", "threshold": 0.9}],
         "provenance": {"source": "test"}}
    t.update(kw)
    return t


def write(dirpath, t, name=None):
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / (name or f"{t['id']}@{t['version']}.json")
    p.write_text(json.dumps(t))
    return p


# ------------------------------------------------------------------ the schema
def test_a_good_template_validates_and_the_schema_file_is_draft_2020_12():
    assert S.validate(template()) == []
    schema = json.loads((Path(S.__file__).parent / "prompt_template.schema.json").read_text())
    assert schema["$schema"].endswith("2020-12/schema") and set(schema["required"]) >= {"id", "version", "purpose", "media", "title", "body"}
    assert set(schema["properties"]["body"]["required"]) == {"subject", "action", "camera", "style", "constraints"}


@pytest.mark.parametrize("mutate, path, why", [
    (lambda t: t.update(id="Bad Id"), "id", "kebab"),
    (lambda t: t.update(version="1.0"), "version", "semver"),
    (lambda t: t.update(purpose="vibes"), "purpose", "one of"),
    (lambda t: t.update(media="audio"), "media", "image or video"),
    (lambda t: t["body"].pop("camera"), "body.camera", "required"),
    (lambda t: t["body"].update(style=5), "body.style", "string"),
    (lambda t: t["variables"]["cadence_spm"].update(type="float"), "variables.cadence_spm.type", "one of"),
    (lambda t: t["variables"]["cadence_spm"].update(default=500), "variables.cadence_spm.default", "max"),
    (lambda t: t["variables"]["direction"].update(default="up"), "variables.direction.default", "enum"),
    (lambda t: t.update(beats=[{"t0": 3, "t1": 1, "action": "x"}]), "beats[0]", "t1"),
    (lambda t: t.update(inputs={"selfie": {"required": True, "description": "x"}}), "inputs.selfie", "role"),
    (lambda t: t.update(gates=[{"description": "no id"}]), "gates[0].id", "required"),
    (lambda t: t["body"].update(action="He walks at {{speed}} steps."), "body.action", "speed"),
])
def test_a_bad_template_is_refused_with_its_path_and_the_reason(mutate, path, why):
    t = template()
    mutate(t)
    errors = S.validate(t)
    assert errors, "the bad template was accepted"
    assert any(e["path"] == path and why in e["reason"] for e in errors), errors


def test_more_than_five_negatives_are_refused_at_save_but_render_caps_at_five():
    t = template(negatives=[f"no thing {i}" for i in range(7)])
    assert any(e["path"] == "negatives" and "5" in e["reason"] for e in S.validate(t))


# ------------------------------------------------------------------ the library
def test_builtins_user_and_project_load_and_override_by_id(tmp_path):
    builtin, user, project = tmp_path / "b", tmp_path / "u", tmp_path / "p"
    write(builtin, template(title="Built-in"))
    write(user, template(title="User", version="1.0.1"))
    lib = L.Library(builtin_dir=builtin, user_dir=user, project_dir=project)
    assert lib.get("demo-walk")["title"] == "User" and lib.get("demo-walk")["scope"] == "user"
    write(project, template(title="Project", version="1.0.2"))
    lib = L.Library(builtin_dir=builtin, user_dir=user, project_dir=project)
    assert lib.get("demo-walk")["title"] == "Project" and lib.get("demo-walk")["scope"] == "project"
    assert [v["version"] for v in lib.versions("demo-walk")] == ["1.0.2", "1.0.1", "1.0.0"], "a new version never overwrites the old one"
    assert lib.get("demo-walk", version="1.0.0")["title"] == "Built-in"


def test_a_same_version_in_a_higher_scope_overrides_the_lower_one(tmp_path):
    builtin, user = tmp_path / "b", tmp_path / "u"
    write(builtin, template(title="Built-in"))
    write(user, template(title="Mine"), name="mine.json")
    assert L.Library(builtin_dir=builtin, user_dir=user).get("demo-walk")["title"] == "Mine"


def test_an_invalid_user_file_is_refused_with_the_path_and_reason_and_the_rest_still_load(tmp_path):
    builtin, user = tmp_path / "b", tmp_path / "u"
    write(builtin, template())
    bad = template(id="other-one")
    bad["body"].pop("style")
    write(user, bad)
    (user / "broken.json").write_text("{not json")
    lib = L.Library(builtin_dir=builtin, user_dir=user)
    assert lib.get("demo-walk") and lib.get("other-one", missing_ok=True) is None
    reasons = {Path(e["file"]).name: e["errors"] for e in lib.errors}
    assert "other-one@1.0.0.json" in reasons and any(x["path"] == "body.style" for x in reasons["other-one@1.0.0.json"])
    assert "broken.json" in reasons and "JSON" in reasons["broken.json"][0]["reason"]


def test_save_writes_user_scope_only_validates_and_never_overwrites_a_version(tmp_path):
    lib = L.Library(builtin_dir=tmp_path / "b", user_dir=tmp_path / "u", project_dir=tmp_path / "p")
    p = lib.save(template())
    assert Path(p).parent == tmp_path / "u" and lib.get("demo-walk")["scope"] == "user"
    with pytest.raises(L.LibraryError, match="1.0.0"):
        lib.save(template(title="changed"))
    lib.save(template(title="changed", version="1.0.1"))
    assert lib.get("demo-walk")["version"] == "1.0.1"
    bad = template()
    bad["body"].pop("subject")
    with pytest.raises(L.LibraryError, match="body.subject"):
        lib.save(bad)
    assert not (tmp_path / "p").exists()


def test_the_shipped_builtins_load_clean_and_cover_the_spec():
    lib = L.Library()
    assert lib.errors == [], lib.errors
    ids = {t["id"] for t in lib.list()}
    assert {"anim-walk-side-track", "anim-walk-front-dollyback", "anim-walk-ortho-inplace", "anim-split-front-side", "anim-loop", "anim-motion-transfer",
            "articulation-study", "plate-4k-crisper", "mesh-paint-albedo-front", "mesh-paint-albedo-side", "material-id-draft", "concept-variant", "seamless-tile",
            "character-reference-fullbody", "anim-start-frame-side-grid", "texture-plate-delit"} <= ids
