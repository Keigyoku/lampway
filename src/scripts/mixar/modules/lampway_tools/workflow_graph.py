# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""workflow_graph: a typed DAG of Lampway tool calls, so a workflow is data. Nodes name a tool and its arguments; ``after`` orders them; an argument string
``@node.key`` is that upstream node's output, ``{{name}}`` an input. Every node's output is cached by the hash of (tool, resolved args, the hashes of the outputs
it consumed), so an identical run executes nothing, a changed argument re-executes only what depends on it, and ``rerun`` re-executes a node and what follows it.
A node with ``spend: true`` (it must name its ``studio_action``) is PLANNED and priced, never run: the user confirms spends in the Studios panel, and what
depends on it waits. Storage: ``<root>/graphs/<name>/{graph.json, versions/, cache/}`` and ``<root>/graphs/_templates/``. Pure python; the executor is
``api.call`` unless one is injected."""

import hashlib
import json
import re
from pathlib import Path
from typing import Callable, Optional

PLANNED = "planned only: the user confirms spends in the Studios panel"
_REF = re.compile(r"^@([A-Za-z0-9_\-]+)\.([A-Za-z0-9_\-]+)$")
_VAR = re.compile(r"\{\{(\w+)\}\}")
_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class GraphError(ValueError):
    pass


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _subst(value, inputs: dict):
    if isinstance(value, str):
        whole = _VAR.fullmatch(value)
        if whole:                                                             # the whole argument is one input: it keeps its type (a list stays a list)
            if whole.group(1) not in inputs:
                raise GraphError(f"the graph needs the input {whole.group(1)!r}")
            return inputs[whole.group(1)]
        def one(m):
            if m.group(1) not in inputs:
                raise GraphError(f"the graph needs the input {m.group(1)!r}")
            return str(inputs[m.group(1)])
        return _VAR.sub(one, value)
    if isinstance(value, dict):
        return {k: _subst(v, inputs) for k, v in value.items()}
    if isinstance(value, list):
        return [_subst(v, inputs) for v in value]
    return value


class Graphs:
    def __init__(self, root, executor: Optional[Callable] = None, tools=None):
        self.root = Path(root) / "graphs"
        self.executor = executor
        self._tools = tools

    # ------------------------------------------------------------------ files
    def _dir(self, name: str) -> Path:
        if not _NAME.match(str(name)):
            raise GraphError("a graph name is letters, digits, - and _ (1 to 64)")
        return self.root / name

    def _load(self, name: str, resolved: bool = True) -> dict:
        """The graph; ``{{inputs}}`` are filled from the inputs stored with it (resolved=False keeps the placeholders, for templates)."""
        p = self._dir(name) / "graph.json"
        if not p.exists():
            raise GraphError(f"no graph {name!r}: define it first")
        graph = json.loads(p.read_text(encoding="utf-8"))
        if not resolved:
            return graph
        inputs = graph.get("inputs") or {}
        return dict(graph, nodes=[dict(n, args=_subst(n.get("args") or {}, inputs)) for n in graph["nodes"]])

    def _tool_names(self) -> list:
        if self._tools is not None:
            return list(self._tools)
        from . import api
        return list(api.TOOL_FUNCS)

    # ------------------------------------------------------------------ validation
    def _validate(self, graph: dict) -> list:
        """The node ids in topological order (definition order breaks ties)."""
        nodes = (graph or {}).get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise GraphError("a graph has a list of nodes")
        ids = [n.get("id") for n in nodes]
        if len(set(ids)) != len(ids) or any(not _NAME.match(str(i)) for i in ids):
            raise GraphError("node ids are unique and made of letters, digits, - and _")
        tools = self._tool_names()
        for n in nodes:
            if n.get("tool") not in tools:
                raise GraphError(f"node {n['id']!r} names an unknown tool {n.get('tool')!r}; the tools are: {', '.join(sorted(tools))}")
            if n.get("spend") and not n.get("studio_action"):
                raise GraphError(f"node {n['id']!r} spends: it must declare its studio_action (the Studios action the user confirms)")
            for a in n.get("after") or []:
                if a not in ids:
                    raise GraphError(f"node {n['id']!r} comes after an unknown node {a!r}")
        order, done, remaining = [], set(), list(nodes)
        while remaining:
            ready = [n for n in remaining if all(a in done for a in n.get("after") or [])]
            if not ready:
                raise GraphError("the graph has a cycle through " + ", ".join(n["id"] for n in remaining))
            n = ready[0]
            order.append(n["id"])
            done.add(n["id"])
            remaining.remove(n)
        for o in graph.get("outputs") or []:
            if o not in ids:
                raise GraphError(f"output {o!r} is not a node")
        return order

    # ------------------------------------------------------------------ define / show / versions / templates
    def define(self, name: str, graph: dict, inputs: Optional[dict] = None) -> dict:
        graph = dict(json.loads(json.dumps(graph)), inputs=dict(inputs or {}))
        self._validate(graph)
        for n in graph["nodes"]:
            _subst(n.get("args") or {}, graph["inputs"])                      # a missing input is refused now, not at the first run
        d = self._dir(name)
        d.mkdir(parents=True, exist_ok=True)
        (d / "graph.json").write_text(json.dumps(graph, indent=1), encoding="utf-8")
        return {"name": name, "graph": graph}

    def show(self, name: str) -> dict:
        d = self._dir(name)
        versions = sorted(p.stem for p in (d / "versions").glob("*.json")) if (d / "versions").exists() else []
        return {"name": name, "graph": self._load(name), "versions": versions}

    def version(self, name: str, version: str) -> dict:
        graph = self._load(name, resolved=False)
        v = self._dir(name) / "versions"
        v.mkdir(exist_ok=True)
        if not _NAME.match(version):
            raise GraphError("a version name is letters, digits, - and _")
        (v / f"{version}.json").write_text(json.dumps(graph, indent=1), encoding="utf-8")
        return {"name": name, "version": version}

    def rollback(self, name: str, version: str) -> dict:
        p = self._dir(name) / "versions" / f"{version}.json"
        if not p.exists():
            raise GraphError(f"no version {version!r} of {name!r}")
        (self._dir(name) / "graph.json").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        return {"name": name, "rolled_back_to": version}

    def template_save(self, name: str, template: str, description: str = "") -> dict:
        if not str(description).strip():
            raise GraphError("a template needs a description (what it is for)")
        t = self.root / "_templates"
        t.mkdir(parents=True, exist_ok=True)
        if not _NAME.match(template):
            raise GraphError("a template name is letters, digits, - and _")
        (t / f"{template}.json").write_text(json.dumps({"description": description, "graph": {k: v for k, v in self._load(name, resolved=False).items() if k != "inputs"}}, indent=1), encoding="utf-8")
        return {"template": template}

    def template_use(self, template: str, name: str, inputs: Optional[dict] = None) -> dict:
        p = self.root / "_templates" / f"{template}.json"
        if not p.exists():
            raise GraphError(f"no template {template!r}")
        return self.define(name, json.loads(p.read_text(encoding="utf-8"))["graph"], inputs)

    # ------------------------------------------------------------------ planning and running
    def _cache(self, name: str) -> Path:
        c = self._dir(name) / "cache"
        c.mkdir(parents=True, exist_ok=True)
        return c

    def _walk(self, name: str, force: frozenset = frozenset(), execute: bool = False) -> dict:
        graph = self._load(name)
        order = self._validate(graph)
        nodes = {n["id"]: n for n in graph["nodes"]}
        cache = self._cache(name)
        outputs, out_hash, states, messages, plan, resolved = {}, {}, {}, {}, [], {}
        credits = 0.0
        for nid in order:
            n = nodes[nid]
            deps = n.get("after") or []
            bad = [d for d in deps if states.get(d) not in ("done", "cached", "confirmed")]
            args = self._resolve(n.get("args") or {}, outputs)
            key = _h({"tool": n["tool"], "args": args, "upstream": {d: out_hash.get(d) for d in deps}}) if not bad else None
            hit = key is not None and (cache / f"{key}.json").exists() and nid not in force and not n.get("spend")
            row = {"node": nid, "tool": n["tool"], "input_hash": key, "cached": bool(hit), "credits_planned": float(n.get("credits") or 0) if n.get("spend") else 0}
            plan.append(row)
            resolved[nid] = (args, key, bad)
            if n.get("spend"):
                credits += row["credits_planned"]
            if not execute:
                continue
            if bad:
                states[nid], messages[nid] = "blocked", f"waiting on {', '.join(bad)}"
                continue
            if n.get("spend"):
                confirmed = cache / f"confirmed-{key}.json"
                if not confirmed.exists():
                    states[nid], messages[nid] = "planned_only", PLANNED
                    continue
                out = json.loads(confirmed.read_text(encoding="utf-8"))
                states[nid] = "confirmed"
                outputs[nid], out_hash[nid] = out, _h(out)
                continue
            if hit:
                out = json.loads((cache / f"{key}.json").read_text(encoding="utf-8"))
                states[nid] = "cached"
            else:
                out = self._exec(n["tool"], args)
                if not (isinstance(out, dict) and out.get("ok", True)):
                    states[nid], messages[nid] = "failed", str((out or {}).get("error") or "the tool failed")
                    continue
                (cache / f"{key}.json").write_text(json.dumps(out, default=str), encoding="utf-8")
                states[nid] = "done"
            outputs[nid], out_hash[nid] = out, _h(out)
        return {"plan": plan, "credits_planned": credits, "states": states, "messages": messages, "outputs": {o: outputs.get(o) for o in graph.get("outputs") or []},
                "_resolved": resolved, "_nodes": nodes}

    @staticmethod
    def _resolve(value, outputs: dict):
        if isinstance(value, str):
            m = _REF.match(value)
            if m:
                src = outputs.get(m.group(1))
                return src.get(m.group(2)) if isinstance(src, dict) else value
            return value
        if isinstance(value, dict):
            return {k: Graphs._resolve(v, outputs) for k, v in value.items()}
        if isinstance(value, list):
            return [Graphs._resolve(v, outputs) for v in value]
        return value

    def _exec(self, tool: str, args: dict):
        if self.executor is not None:
            return self.executor(tool, args)
        from . import api
        return api.call(tool, json.dumps(args))

    def confirm(self, name: str, node: str) -> dict:
        """The user's confirm of ONE spend node: it runs that node's tool once with its resolved arguments, and the output is kept for exactly those inputs
        (a changed upstream needs a new confirm). Nothing else that spends is run."""
        res = self._walk(name, execute=True)
        n = res["_nodes"].get(node)
        if n is None or not n.get("spend"):
            raise GraphError(f"{node!r} is not a spend node of {name!r}: only a planned spend is confirmed")
        args, key, bad = res["_resolved"][node]
        if bad:
            raise GraphError(f"{node!r} is waiting on {', '.join(bad)}: confirm those first")
        if res["states"].get(node) == "confirmed":
            return {"node": node, "state": "confirmed", "already": True}
        out = self._exec(n["tool"], args)
        if not (isinstance(out, dict) and out.get("ok", True)):
            return {"node": node, "state": "failed", "error": str((out or {}).get("error") or "the tool failed")}
        (self._cache(name) / f"confirmed-{key}.json").write_text(json.dumps(out, default=str), encoding="utf-8")
        return {"node": node, "state": "confirmed", "output": out}

    def plan(self, name: str) -> dict:
        res = self._walk(name)
        return {"plan": res["plan"], "credits_planned": res["credits_planned"]}

    def run(self, name: str) -> dict:
        return {k: v for k, v in self._walk(name, execute=True).items() if not k.startswith("_")}

    def rerun(self, name: str, from_node: str) -> dict:
        graph = self._load(name)
        if from_node not in {n["id"] for n in graph["nodes"]}:
            raise GraphError(f"no node {from_node!r}")
        down, grew = {from_node}, True
        while grew:
            grew = False
            for n in graph["nodes"]:
                if n["id"] not in down and any(a in down for a in n.get("after") or []):
                    down.add(n["id"])
                    grew = True
        return {k: v for k, v in self._walk(name, force=frozenset(down), execute=True).items() if not k.startswith("_")}
