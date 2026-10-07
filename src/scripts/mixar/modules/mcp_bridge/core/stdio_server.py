# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later
"""Official SDK stdio endpoint combining local UI and existing backend tools."""

import asyncio
from contextlib import asynccontextmanager
import http.client
import json
import re
import uuid

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from mixar.modules.common.ui_control.core import schema
from . import aliases, availability, presentation
from .generated_guide import GUIDE, LOCAL_GUIDE
from .connector import Connector, instances, signed_in, usable

#: Domains of the tools this launcher serves locally (the backend never sees them).
LOCAL_DOMAINS = tuple(dict.fromkeys(schema.DOMAINS.values()))


def ui_index(query="", domain=None):
    """Compact catalog entries for the local tools."""
    query = query.casefold()
    entries = [{"name": tool["name"], "domain": tool["_meta"]["mixar/domain"],
                "summary": tool["description"].split(". ", 1)[0].rstrip(".") + ".",
                "read_only": tool["annotations"]["readOnlyHint"], "credits": "free."}
               for tool in schema.tools()
               if domain in (None, tool["_meta"]["mixar/domain"])
               and (query in tool["name"].casefold() or query in tool["description"].casefold())]
    return entries


def with_ui_domain(tools):
    """Let mixar_tool_catalog's advertised domain filter name the local domains."""
    for tool in tools:
        domain = tool.get("inputSchema", {}).get("properties", {}).get("domain")
        if tool["name"] == "mixar_tool_catalog" and domain:
            domain["enum"] = [*domain.get("enum", []),
                              *(name for name in LOCAL_DOMAINS if name not in domain.get("enum", []))]
    return tools


def failure(exc, call_id):
    payload = {"error": str(exc), "call_id": call_id,
               "note": "No automatic mutation retry occurred. Inspect status before further edits."}
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload))],
                                structured_content=payload, is_error=True,
                                meta={"mixar/request-id": call_id})


def create_server(connector):
    status = {"listed": False, "readiness": "starting"}

    def visible(tools):
        if getattr(connector, "health", {}).get("ui_control") is False:
            # Interface control is opt-in; scene and project tools stay.
            return [tool for tool in tools if tool["name"] not in schema.UI_INPUT]
        return tools

    guide = {"text": GUIDE, "prepared": False, "catalog_pending": False, "backend": None}

    async def prepare_guide():
        if guide["prepared"]:
            return
        text = GUIDE
        fetch = getattr(connector, "instructions", None)
        if fetch:
            try:
                live = await asyncio.wait_for(asyncio.to_thread(fetch), availability.CATALOG_TIMEOUT_SECONDS)
                if isinstance(live, str) and live.strip():
                    text = live + "\n" + LOCAL_GUIDE
            except (OSError, ValueError, KeyError, RuntimeError, TimeoutError, http.client.HTTPException):
                pass
        backend, status["readiness"] = await availability.fetch_tools(connector)
        guide["backend"], guide["catalog_pending"] = backend, True
        tools = aliases.expose(visible(schema.tools() + (backend or [])))
        names = {tool["name"] for tool in tools}
        # A saved guide may describe tools absent from an older backend or an
        # empty snapshot. Drop those lines rather than advertise nonexistent tools.
        lines = [line for line in text.splitlines()
                 if set(re.findall(r"[a-z]+(?:_[a-z0-9]+)+", line)) <= names]
        while len("\n".join(lines).encode()) > 2048:
            lines.pop()
        guide["text"] = "\n".join(lines)
        guide["prepared"] = True

    @asynccontextmanager
    async def guide_lifespan(server):
        await prepare_guide()
        server.instructions = guide["text"]
        yield {}

    class GuidedServer(Server):
        async def run(self, read_stream, write_stream, initialization_options, raise_exceptions=False):
            await prepare_guide()
            initialization_options.instructions = guide["text"]
            await super().run(read_stream, write_stream, initialization_options, raise_exceptions)

    async def list_tools(ctx, params):
        # Every tool at once (live, or the copy saved while signed in); never wait.
        if guide["catalog_pending"]:
            backend, guide["catalog_pending"] = guide["backend"], False
        else:
            backend, status["readiness"] = await availability.fetch_tools(connector)
        tools = schema.tools() + (with_ui_domain(backend) if backend is not None else [])
        status["listed"] = backend is not None
        tools = presentation.tools_for_client(aliases.expose(visible(tools)), presentation.client_name(ctx))
        return types.ListToolsResult(tools=[types.Tool.model_validate(t) for t in tools])

    async def call_tool(ctx, params):
        result = await _call_tool(ctx, params)
        shaped = presentation.for_client(result.model_dump(by_alias=True, exclude_none=True),
                                         presentation.client_name(ctx))
        return types.CallToolResult.model_validate(shaped)

    async def _call_tool(ctx, params):
        call_id = str(uuid.uuid4())
        try:
            call_id = str(uuid.UUID((ctx.meta or {}).get("mixar/request-id", call_id)))
            args = params.arguments or {}
            params = params.model_copy(update={"name": aliases.internal_name(params.name)})  # lampway_* -> the connector's own name
            if params.name in schema.SCHEMAS:
                schema.validate(params.name, args)
            if params.name == "mixar_tool_quote" and args.get("tool") in schema.SCHEMAS:
                if set(args) != {"tool"}:
                    raise ValueError("Specify only the tool to quote")
                payload = {"result": {"tool": args["tool"], "invocation_credits": 0,
                    "generation_credits": None, "generation_billing": "existing_job_queue",
                    "surface": "local_ui"}, "usage": {"request_id": call_id, "credits_charged": 0}}
                return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload))],
                                            structured_content=payload, meta={"mixar/request-id": call_id})
            if params.name == "mixar_ui_context":
                if args.get("instance"):
                    available = await asyncio.to_thread(instances)
                    if args["instance"] not in {r["instance_id"] for r, _ in available}:
                        raise ValueError("Selected Lampway instance is unavailable")
                    await asyncio.to_thread(connector.cancel)
                    with connector.lock:
                        connector.instance, connector.record = args["instance"], None
                        connector.upstream_version = None
                        connector.bound_session = connector.session
                    args = {k: v for k, v in args.items() if k != "instance"}
                elif connector.record is None:
                    available = await asyncio.to_thread(instances)
                    if (len(available) > 1 and usable(available) is None) or (connector.instance and available and
                            connector.instance not in {r["instance_id"] for r, _ in available}):
                        result = {"instances": [{"instance": r["instance_id"], "scene_name": h.get("scene_name"),
                                                 "signed_in": signed_in(h), "connected": bool(h.get("connected"))}
                                                for r, h in available]}
                        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result))],
                                                    structured_content=result)
                if args.get("session"):
                    _, health = await asyncio.to_thread(connector.attach)
                    if args["session"] != health.get("session_id"):
                        raise ValueError("Select the current Lampway scene session returned by context")
                    connector.bound_session = args["session"]
                    args = {k: v for k, v in args.items() if k != "session"}
            if params.name == "mixar_tool_catalog" and args.get("domain") in LOCAL_DOMAINS:
                entries = ui_index(args.get("query", ""), args["domain"])
                payload = {"result": {"domains": {args["domain"]: len(entries)}, "tools": entries},
                           "usage": {"request_id": call_id, "credits_charged": 0}}
                return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload))],
                                            structured_content=payload, meta={"mixar/request-id": call_id})
            connector.client = presentation.client_info(ctx)
            result = await asyncio.to_thread(connector.call, params.name, args, call_id)
            payload = result.get("structuredContent") or {}
            if params.name == "mixar_ui_context" and isinstance(payload.get("result"), dict):
                # Say whether scene work is possible in THIS session, and why not;
                # also when the interface controller itself is still starting.
                readiness, _ = await asyncio.to_thread(connector.readiness)
                payload["result"].update(availability.scene_tools(status["listed"], readiness, connector.health))
                result["content"][0] = {"type": "text", "text": json.dumps(payload)}
            if params.name == "mixar_tool_catalog" and not result.get("isError"):
                payload = result["structuredContent"]["result"]
                if "domains" in payload:
                    entries = ui_index(args.get("query", ""), args.get("domain"))
                    payload["tools"].extend(entries)
                    for entry in entries:
                        payload["domains"][entry["domain"]] = payload["domains"].get(entry["domain"], 0) + 1
                else:  # An older backend returns full tool definitions.
                    query = args.get("query", "").casefold()
                    payload["tools"].extend(t for t in schema.tools() if query in t["name"].casefold()
                                           or query in t["description"].casefold())
                result["content"][0] = {"type": "text", "text": json.dumps(payload)}
            return types.CallToolResult.model_validate(result)
        except asyncio.CancelledError:
            await asyncio.shield(asyncio.to_thread(connector.cancel, call_id))
            raise
        except Exception as exc:
            return failure(exc, call_id)

    async def list_resources(ctx, params):
        return types.ListResourcesResult(resources=[types.Resource(uri="lampway://guide", name="Lampway guide",
                                                                   mime_type="text/markdown")])

    async def read_resource(ctx, params):
        if str(params.uri) not in ("lampway://guide", "mixar://guide"):  # the old URI stays readable for one release
            raise ValueError("Unknown Lampway resource")
        return types.ReadResourceResult(contents=[types.TextResourceContents(
            uri=params.uri, mime_type="text/markdown", text=guide["text"])])

    async def list_prompts(ctx, params):
        return types.ListPromptsResult(prompts=[types.Prompt(name="build-and-verify",
            description="Inspect, build with scene tools and native UI, and verify the result.",
            arguments=[types.PromptArgument(name="goal", required=True)])])

    async def get_prompt(ctx, params):
        args = params.arguments or {}
        goal = args.get("goal", "")
        if (params.name != "build-and-verify" or set(args) != {"goal"}
                or not goal.strip() or len(goal) > 8000):
            raise ValueError("Specify build-and-verify with a nonempty goal of at most 8000 characters")
        return types.GetPromptResult(messages=[types.PromptMessage(role="user",
            content=types.TextContent(type="text", text="Complete this task in Lampway: " + goal +
                "\n\n" + guide["text"] + "\nInspect the scene before and after editing. "
                "Report any unverified outcomes."))])

    return GuidedServer("Lampway", version="1", instructions=GUIDE, lifespan=guide_lifespan,
                  on_list_tools=list_tools, on_call_tool=call_tool,
                  on_list_resources=list_resources, on_read_resource=read_resource,
                  on_list_prompts=list_prompts, on_get_prompt=get_prompt)


async def run(instance=None, session=None):
    connector = Connector(instance, session)
    server = create_server(connector)
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        for task in list(connector.tasks):
            task.cancel()
        if connector.tasks:
            await asyncio.gather(*connector.tasks, return_exceptions=True)
        await asyncio.to_thread(connector.cancel)
