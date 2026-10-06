"""The MCP client for Higgsfield: the generic ``mcp_client.McpClient`` on Lampway's own Higgsfield sign-in (higgsfield_auth), never a
claude.ai connector."""

from .higgsfield_auth import MCP_URL, HiggsfieldAuth
from .mcp_client import PROTOCOL, MCPError, McpClient, ToolError, TransportTimeout  # noqa: F401  (re-exported)


class HiggsfieldMCP(McpClient):
    def __init__(self, auth: HiggsfieldAuth, *, transport=None, timeout: float = 60.0, url: str = MCP_URL):
        super().__init__(auth, url=url, label="Higgsfield", page="/app/higgsfield", transport=transport, timeout=timeout)
