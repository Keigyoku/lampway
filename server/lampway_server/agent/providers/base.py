"""The provider interface: one neutral message shape in, a stream of text deltas
and tool calls out. Each provider translates to its own wire format."""

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, Union


@dataclass
class Text:
    """A text delta from the model."""
    text: str


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Stop:
    """Why the model stopped, when it was NOT the ordinary end (``length``, ``content_filter``, an error subtype...).
    Providers yield it last, only for those; the model gateway turns it into the finish reason the engine is told."""
    reason: str


ProviderEvent = Union[Text, ToolCall, Stop]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema


@dataclass
class Message:
    """Parts: {type:'text', text} | {type:'tool_call', id, name, arguments}
    | {type:'image', source:{type:'base64', media_type, data}|{type:'url', url}}
    | {type:'tool_result', tool_call_id, content, is_error}. Tool result content may be typed text/image parts."""
    role: str
    content: list[dict] = field(default_factory=list)

    def text(self) -> str:
        return "".join(part.get("text", "") for part in self.content if part.get("type") == "text")

    @classmethod
    def user_text(cls, text: str) -> "Message":
        return cls("user", [{"type": "text", "text": text}])


@dataclass
class ModelRequest:
    system: str
    messages: list[Message]
    tools: list[ToolSpec]
    session_id: str = ""        # the Lampway session the request belongs to (a provider may key per-conversation state on it)
    supports_vision: bool | None = None  # request admission metadata; explicit False always withholds images


class Provider(Protocol):
    name: str
    supports_vision: bool | None  # only an explicit True admits images; missing/unknown capabilities fail closed

    def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        """Yield Text deltas and ToolCalls for one model call, then return."""
        ...


def image_url(part: dict) -> dict:
    """A neutral image as an OpenAI image part, without fetching or reencoding it."""
    source = part["source"]
    url = (f"data:{source['media_type']};base64,{source['data']}"
           if source["type"] == "base64" else source["url"])
    return {"type": "image_url", "image_url": {"url": url, **({"detail": part["detail"]} if "detail" in part else {})}}
