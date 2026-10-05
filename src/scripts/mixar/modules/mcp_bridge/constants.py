# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later
"""External tool execution protocol limits."""

from mixar.config.brand import docs_url

CAPABILITY = "mcp_operations_v1"
BEGIN_OPERATION = "mcp.begin_operation"
END_OPERATION = "mcp.end_operation"
OPERATION_CONTEXT_KEY = "mcp_operation_id"
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 600
MAX_ACTIVE_OPERATIONS = 32
RETIRED_OPERATION_SECONDS = 3600
#: Per-app setup lives in our docs; the dialog copies the standard JSON.
SETUP_GUIDE_URL = docs_url("connect-ai-apps")
#: The MCP server name apps list this connector under, and the launcher's file name. LEGACY_* are the names a pre-Lampway install used (migrated, then retired).
SERVER_NAME = "lampway"
LAUNCHER_NAME = "lampway-mcp"
LEGACY_SERVER_NAME = "mixar"
LEGACY_LAUNCHER_NAME = "mixar-mcp"
