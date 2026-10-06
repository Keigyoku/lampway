"""The Def and P records every Lampway agent tool definition is written in (lampway_tools.DEFS and wave6_tools.DEFS). A module of its own so
wave6_tools can import them without importing lampway_tools, which appends wave6_tools.DEFS: no import cycle, whichever is imported first."""

from dataclasses import dataclass, field
from typing import Optional

from .providers.base import ToolSpec


@dataclass
class P:
    name: str
    type: str = "string"                   # string | number | integer | boolean | array | object
    desc: str = ""
    required: bool = False
    flag: Optional[str] = None             # batch tools: None = positional, else the command-line flag
    repeat: bool = False                   # an array given as one flag per value
    items: Optional[dict] = None           # an array's item schema when the name-based default below does not fit


@dataclass
class Def:
    name: str
    description: str
    params: list = field(default_factory=list)
    api: Optional[str] = None              # an api.<fn> tool function, or
    batch: Optional[str] = None            # a ported batch tool run through api.run_tool

    def spec(self) -> ToolSpec:
        props, req = {}, []
        for p in self.params:
            prop = {"type": p.type, "description": p.desc}
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
