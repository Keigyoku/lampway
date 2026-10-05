"""Material generation: a procedural material (a node-group-building script) from a prompt, by the configured model.

Upstream's paint library sent the prompt to a withheld hosted service. Here the server asks its own provider for the
script, then checks it before handing it over (the client runs it again under its sandbox guard when the node group is
first built, material_registry._run_script): it must parse; import nothing but bpy, mathutils and math; reach no
dunder; call no open/exec/eval/compile/__import__; and create the node group it was told to name, as a ShaderNodeTree.
"""

import ast
import re
import uuid
from dataclasses import dataclass

from .agent.providers.base import Message, ModelRequest, Text

ALLOWED_IMPORTS = {"bpy", "mathutils", "math"}
_FORBIDDEN_CALLS = {"open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars"}
_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)

SYSTEM = """You write Blender 5.x procedural materials as node groups, for a layer-painting tool.
Answer with ONE Python code block and nothing else. Rules for the script:
- `import bpy` (and `import math` / `import mathutils` if needed); nothing else, no file or network access;
- create the group with `group = bpy.data.node_groups.new("{name}", "ShaderNodeTree")`;
- add exactly one output socket: `group.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")`
  and a `NodeGroupOutput` node linked from a Principled BSDF's "BSDF" output;
- build the look from procedural texture nodes (Noise, Voronoi, Wave, Musgrave via Noise, ColorRamp, Mix, Bump,
  Mapping + Texture Coordinate), never from image files;
- expose the useful controls as INPUT sockets (Scale, Roughness, Wear, colours) with sensible defaults, so the user
  can adjust the material afterwards;
- set node locations so the graph reads left to right; no `print`, no `bpy.ops`, no `bpy.context`.
"""


class BadScript(ValueError):
    pass


@dataclass
class Material:
    material_id: str
    name: str
    node_group_name: str
    script: str
    description: str
    category: str = "ai_generated"

    def as_dict(self) -> dict:
        return {"material_id": self.material_id, "name": self.name, "node_group_name": self.node_group_name,
                "script": self.script, "description": self.description, "category": self.category}


def node_group_name(prompt: str) -> str:
    words = [w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", prompt)][:4]
    return "LW_" + ("".join(words) or "Material") + "_" + uuid.uuid4().hex[:4]


def extract_script(text: str) -> str:
    """The first fenced code block, else the whole text when it looks like a script."""
    m = _FENCE.search(text or "")
    if m:
        return m.group(1).strip() + "\n"
    stripped = (text or "").strip()
    if stripped.startswith("import bpy"):
        return stripped + "\n"
    raise BadScript("the model returned no script (no code block)")


def check_script(script: str, group_name: str) -> None:
    """Refuse a script that could do anything but build the named node group."""
    try:
        tree = ast.parse(script)
    except SyntaxError as exc:
        raise BadScript(f"the script does not parse: {exc.msg} (line {exc.lineno})") from None
    creates = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
            bad = [n for n in names if n not in ALLOWED_IMPORTS]
            if bad:
                raise BadScript(f"the script imports {', '.join(bad)}; only bpy, mathutils and math are allowed")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise BadScript(f"the script reaches {node.attr}, which is not allowed")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            raise BadScript(f"the script reaches {node.id}, which is not allowed")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALLS:
                raise BadScript(f"the script calls {func.id}(), which is not allowed")
            if (isinstance(func, ast.Attribute) and func.attr == "new" and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "node_groups" and node.args and isinstance(node.args[0], ast.Constant)):
                if node.args[0].value != group_name:
                    raise BadScript(f"the script creates node group {node.args[0].value!r}, not {group_name!r}")
                creates = True
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "bpy" and func.attr in ("ops",):
                raise BadScript("the script uses bpy.ops, which is not allowed")
    if not creates:
        raise BadScript(f"the script does not create the node group {group_name!r}")


async def generate(provider, prompt: str, pipeline: str = "fast") -> Material:
    """Ask ``provider`` for the script and check it; BadScript when the model's answer is not a usable material."""
    name = node_group_name(prompt)
    detail = ("Keep it to a handful of nodes." if pipeline != "detailed"
              else "Take the time for layered detail: base, wear, edge variation, fine grain.")
    request = ModelRequest(SYSTEM.replace("{name}", name), [Message.user_text(
        f"Material: {prompt.strip()}\nNode group name: {name}\n{detail}")], [])
    parts = []
    async for event in provider.stream(request):
        if isinstance(event, Text):
            parts.append(event.text)
    script = extract_script("".join(parts))
    check_script(script, name)
    title = " ".join(w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", prompt)[:5]) or "Material"
    return Material(f"matgen_{uuid.uuid4().hex[:10]}", title, name, script, prompt.strip())
