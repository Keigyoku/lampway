"""Sign in to Higgsfield's MCP server: the standard MCP authorization flow through Clerk, by configuration of the generic module
(``mcp_oauth.HIGGSFIELD``; the flow, the locks and the refresh rules are there).

Measured facts (scratch/subs/higgsfield/SPEC.md): the MCP endpoint is https://mcp.higgsfield.ai/mcp; an unauthenticated call answers 401
with a ``resource_metadata`` URL; the protected-resource metadata names Clerk (https://clerk.higgsfield.ai) as authorization server, which
offers dynamic client registration and S256 PKCE. Tokens stay where they always were, ``<state>/higgsfield_auth.json`` (0600), in the
same format. Nothing here logs a code, state, verifier or token.
"""

import time
from pathlib import Path
from typing import Optional

import httpx

from .mcp_oauth import (HIGGSFIELD, Attempt, FileSession, LoginDeclined, LoginError, McpOAuth, NotSignedIn,  # noqa: F401  (re-exported)
                        TemporaryAuthError)

MCP_URL = HIGGSFIELD.mcp_url
METADATA_URL = HIGGSFIELD.metadata_url
SCOPE = HIGGSFIELD.scope
CALLBACK_PATH = HIGGSFIELD.callback_path


class HiggsfieldAuth(McpOAuth):
    def __init__(self, state_dir, *, http: Optional[httpx.Client] = None, redirect_port: int = 8787, clock=time.time):
        self.dir = Path(state_dir)
        super().__init__(HIGGSFIELD, FileSession(self.dir / "higgsfield_auth.json"), http=http, redirect_port=redirect_port, clock=clock)

    @property
    def path(self) -> Path:
        return self.session.path
