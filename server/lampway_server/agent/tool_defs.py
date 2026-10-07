"""The Def and P records every Lampway agent tool definition is written in (lampway_tools.DEFS and wave6_tools.DEFS). A module of its own so
wave6_tools can import them without importing lampway_tools, which appends wave6_tools.DEFS: no import cycle, whichever is imported first."""

import json
from dataclasses import dataclass, field
from typing import Optional

from .providers.base import ToolSpec


def needs(name: str, missing, schema: dict) -> str:
    """The required-argument refusal (audit F13): what is missing, then a call template - every required argument with what it is."""
    props, req = schema.get("properties") or {}, schema.get("required") or []
    template = {k: "<" + ((props.get(k) or {}).get("description") or (props.get(k) or {}).get("type") or "value")[:60] + ">" for k in req}
    return f"{name} needs {', '.join(missing)}. Call it as: {name} {json.dumps(template)}"


@dataclass
class P:
    name: str
    type: str = "string"                   # string | number | integer | boolean | array | object
    desc: str = ""
    required: bool = False
    flag: Optional[str] = None             # batch tools: None = positional, else the command-line flag
    repeat: bool = False                   # an array given as one flag per value
    items: Optional[dict] = None           # an array's item schema when the name-based default below does not fit
    minimum: Optional[float] = None        # a number's bounds (audit F14: an agent should not guess them)
    maximum: Optional[float] = None


@dataclass
class Def:
    name: str
    description: str
    params: list = field(default_factory=list)
    api: Optional[str] = None              # an api.<fn> tool function, or
    batch: Optional[str] = None            # a ported batch tool run through api.run_tool
    wip: bool = False                      # WIP tooling (a DRAFT canon page): the description and the receipt say so

    def spec(self) -> ToolSpec:
        props, req = {}, []
        for p in self.params:
            prop = {"type": p.type, "description": p.desc}
            prop.update({k: v for k, v in (("minimum", p.minimum), ("maximum", p.maximum)) if v is not None})
            if p.type == "array" and p.items is not None:
                prop["items"] = dict(p.items)
            elif p.type == "array":
                prop["items"] = ({"type": "object"} if p.name in ("poses", "waypoints", "anchors", "landmarks", "axis", "plane_origin", "depths_mm", "claims") else
                                 {"type": "number"} if p.name in ("frame_range", "frames_with_pose") else {"type": "array"} if p.name == "twist" else {"type": "string"})
            props[p.name] = prop
            if p.required:
                req.append(p.name)
        return ToolSpec(name=self.name, description=self.description,
                        parameters={"type": "object", "properties": props, "required": req, "additionalProperties": False})
