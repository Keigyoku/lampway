"""Material generation (docs: "Procedural: adds patterns or variation you can adjust through parameters"; the paint
library's "AI Generate" box). Upstream sent the prompt to a withheld hosted service; Lampway's server asks its own model
for a node-group script and hands back a procedural material the client registers and saves
(paint/procedural_materials: material_registry, matgen_persistence).

POST /api/v1/matgen {prompt, pipeline} -> {material_id, name, node_group_name, category, description, script}. The
script is checked before it is handed over: it parses, imports only bpy/mathutils/math, reaches no dunder, and creates
the node group it was told to name. A script that fails the check is a 502 with the reason, never a material."""

import pytest

from lampway_server import matgen
from lampway_server.agent.providers.base import Text

GOOD = '''```python
import bpy
group = bpy.data.node_groups.new("{name}", "ShaderNodeTree")
group.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
out = group.nodes.new("NodeGroupOutput")
bsdf = group.nodes.new("ShaderNodeBsdfPrincipled")
bsdf.inputs["Base Color"].default_value = (0.72, 0.45, 0.2, 1.0)
noise = group.nodes.new("ShaderNodeTexNoise")
group.links.new(noise.outputs["Fac"], bsdf.inputs["Roughness"])
group.links.new(bsdf.outputs["BSDF"], out.inputs[0])
```'''


def test_the_script_is_extracted_checked_and_the_material_named(fake, provider, monkeypatch):
    monkeypatch.setattr(matgen, "node_group_name", lambda prompt: "LW_WornCopper")   # the server picks the name; pin it
    provider.script = [[Text("Here is the material:\n" + GOOD.replace("{name}", "LW_WornCopper"))]]
    fake.login()
    r = fake.post("/api/v1/matgen", json={"prompt": "worn copper with green patina", "pipeline": "fast"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["node_group_name"] == "LW_WornCopper" and body["material_id"].startswith("matgen_")
    assert body["name"] and body["category"] == "ai_generated" and body["description"] == "worn copper with green patina"
    assert body["script"].startswith("import bpy") and "```" not in body["script"]
    request = provider.requests[-1]
    assert "LW_WornCopper" in request.system or "LW_WornCopper" in request.messages[-1].text()
    assert request.tools == []


@pytest.mark.parametrize("bad, reason", [
    ("import os\nbpy.data.node_groups.new('X', 'ShaderNodeTree')", "import"),
    ("import bpy\ng = bpy.data.node_groups.new('Other', 'ShaderNodeTree')", "node group"),
    ("import bpy\nbpy.data.node_groups.new('X', 'ShaderNodeTree').__class__", "__class__"),
    ("def broken(:", "parse"),
    ("import bpy\nopen('/etc/passwd')", "open"),
])
def test_a_script_that_fails_the_check_is_refused_with_the_reason(bad, reason):
    with pytest.raises(matgen.BadScript) as exc:
        matgen.check_script(bad.replace("'X'", "'LW_X'"), "LW_X")
    assert reason in str(exc.value)


def test_a_model_that_returns_no_script_is_a_502(fake, provider):
    provider.script = [[Text("I cannot do that.")]]
    fake.login()
    r = fake.post("/api/v1/matgen", json={"prompt": "glass"})
    assert r.status_code == 502 and "script" in r.json()["detail"]


def test_a_missing_prompt_is_422_and_a_bearer_is_required(http, fake):
    fake.login()
    assert fake.post("/api/v1/matgen", json={}).status_code == 422
    assert http.post("/api/v1/matgen", json={"prompt": "x"}).status_code == 401
