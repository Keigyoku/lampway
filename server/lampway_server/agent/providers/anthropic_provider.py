"""Claude through the official Anthropic SDK (streaming Messages API).

The API key is resolved by the SDK from the environment (ANTHROPIC_API_KEY or an
``ant auth login`` profile); this module never reads, stores or logs it.
"""

from typing import AsyncIterator, Optional

from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

from .base import Message, ModelRequest, ProviderEvent, Text, ToolCall, ToolSpec

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 32000
_REPLAYABLE_BLOCKS = {"thinking", "redacted_thinking", "text", "tool_use"}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL, *, client: Optional[AsyncAnthropic] = None,
                 transport=None, max_tokens: int = MAX_TOKENS):
        if client is None:
            if transport is not None:
                client = AsyncAnthropic(http_client=DefaultAsyncHttpxClient(transport=transport))
            else:
                client = AsyncAnthropic()
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        # Assistant turns as Claude produced them, keyed by their first tool_use id,
        # so thinking blocks are echoed back unchanged when the tool results go up.
        self._raw_assistant: dict[str, list[dict]] = {}

    async def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": request.system,
            "messages": [self._message(m) for m in request.messages],
        }
        if request.tools:
            kwargs["tools"] = [self._tool(t) for t in request.tools]
        async with self.client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "text":
                    yield Text(event.text)
            final = await stream.get_final_message()
        calls = [block for block in final.content if block.type == "tool_use"]
        if calls:
            raw = [block.model_dump(exclude_none=True) for block in final.content
                   if block.type in _REPLAYABLE_BLOCKS]
            self._raw_assistant[calls[0].id] = raw
        for block in calls:
            arguments = block.input if isinstance(block.input, dict) else {"__invalid_json__": block.input}
            yield ToolCall(id=block.id, name=block.name, arguments=arguments)

    # ------------------------------------------------------------ translation
    @staticmethod
    def _tool(tool: ToolSpec) -> dict:
        return {"name": tool.name, "description": tool.description, "input_schema": tool.parameters}

    def _message(self, message: Message) -> dict:
        if message.role == "assistant":
            calls = [p for p in message.content if p.get("type") == "tool_call"]
            if calls and calls[0]["id"] in self._raw_assistant:
                return {"role": "assistant", "content": self._raw_assistant[calls[0]["id"]]}
            content = []
            for part in message.content:
                if part.get("type") == "text" and part.get("text"):
                    content.append({"type": "text", "text": part["text"]})
                elif part.get("type") == "tool_call":
                    content.append({"type": "tool_use", "id": part["id"], "name": part["name"],
                                    "input": part.get("arguments") or {}})
            return {"role": "assistant", "content": content}
        content = []
        for part in message.content:
            if part.get("type") == "text":
                content.append({"type": "text", "text": part.get("text", "")})
            elif part.get("type") == "tool_result":
                content.append({"type": "tool_result", "tool_use_id": part["tool_call_id"],
                                "content": part.get("content", ""), "is_error": bool(part.get("is_error"))})
        return {"role": "user", "content": content}
