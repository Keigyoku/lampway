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
    Providers yield it last, only for those; the agent loop uses it to explain an empty reply instead of ending the turn silently."""
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
    | {type:'tool_result', tool_call_id, content, is_error}."""
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


class Provider(Protocol):
    name: str

    def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        """Yield Text deltas and ToolCalls for one model call, then return."""
        ...
