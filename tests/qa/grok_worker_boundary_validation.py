# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""P4-17 condition (i), captain's ruling 2026-10-12: the same hostile same-name MCP updates, sent by the same validator to the
same restricted native Grok, now pass through Lampway's ACP boundary (server/lampway_server/grok_acp_boundary.py) and leave the
canonical lampway_pane enabled, ready, and serving its next owned call; the hostile endpoints are never contacted.

This runs the ORIGINAL validator (tests/qa/grok_worker_validation.py, unchanged) with two differences, both stated here:
* the restricted native agent is started behind the boundary (``grok_worker.acp_boundary_argv``);
* the three update replies that the ORIGINAL expects from native Grok ("native hot reload replied" for the STDIO injection of a
  foreign argv under the canonical name, and the HTTP and SSE "same-name native hot reload replied") must instead be the
  boundary's own refusal, because an update naming the canonical server with another transport or argv no longer reaches native
  Grok.
Every other check, its evidence and its twenty-second budget are the original's. The boundary refuses a mixed update whole, so
through it the STDIO injection's "excludes new foreign identity" and "foreign subprocess blocked" checks hold without native
Grok seeing the foreign entry: here they show the boundary, and native policy filtering of foreign identities is proven by the
ORIGINAL, which runs those checks natively before its line 700 under the CI watch. ``--without-boundary`` is the control: the same
run without the boundary must fail where the original does (line 700).

Scope: the original runs through its restricted ACP stage and the foreign-source and preservation checks after it, then stops
before the stages the boundary does not sit in: the project-source native controls (an untrusted folder's .mcp.json does not
load in Grok 1.0.50 and the validator never grants trust) and, in the loopback phase, the native herdr panes (the production
TUI over its own leader socket). Those stay the original's; while its line 700 fails the CI watch cannot reach them either.

The ORIGINAL validator keeps running unchanged in CI as a watch (tests/qa/grok_native_retention_watch.py); see the boundary
module's REMOVAL note for when this script and the boundary are deleted.
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("grok_worker_validation", HERE / "grok_worker_validation.py")
V = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V)

from lampway_server import grok_worker as G  # noqa: E402

#: The original's three update-reply checks whose update names the canonical server with another argv or transport.
REFUSED_REPLIES = ("native hot reload replied", "http same-name native hot reload replied", "sse same-name native hot reload replied")


def refused_by_boundary(reply) -> bool:
    error = reply.get("error") if isinstance(reply, dict) else None
    return isinstance(error, dict) and (error.get("data") or {}).get("refused_by") == "lampway-acp-boundary"


class BoundaryScopeEnd(Exception):
    """Raised where the stages the boundary does not sit in begin; the run up to here is the proof."""


class BoundaryValidator(V.Validator):
    def __init__(self, options):
        super().__init__(options)
        self.receipt["acp_boundary"] = {"selected": not options.without_boundary, "refused_replies": [],
                                        "scope": "ACP-stdio client in front of the restricted native agent (P4-17 condition i)"}

    def native_panes(self, *args, **kwargs):
        raise BoundaryScopeEnd("native herdr panes (production TUI over its own leader socket)")

    async def acp(self, argv, env, cwd, label, *, expect_owned=True):
        if label == "project-baseline":
            raise BoundaryScopeEnd("project-source native controls")
        if label == "restricted" and not self.options.without_boundary:
            argv = G.acp_boundary_argv(self.connector, [], argv)
            self.receipt["acp_boundary"]["argv"] = argv
            self.save()
        return await super().acp(argv, env, cwd, label, expect_owned=expect_owned)

    def check(self, name, value, evidence=None):
        if name in REFUSED_REPLIES and not self.options.without_boundary:
            self.receipt["acp_boundary"]["refused_replies"].append(name)
            return super().check(name + " (refused by Lampway's ACP boundary, never forwarded)", refused_by_boundary(evidence), evidence)
        return super().check(name, value, evidence)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--fake-mcp":
        return V.fake_mcp(sys.argv[2])
    parser = V.argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--grok", type=Path, required=True); parser.add_argument("--bwrap", type=Path, required=True)
    parser.add_argument("--herdr", type=Path)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--phase", choices=["stdio", "loopback"], required=True)
    parser.add_argument("--cursor-fixture", choices=["absent", "present"], default="absent")
    parser.add_argument("--compatibility-layer", action="store_true")
    parser.add_argument("--without-boundary", action="store_true", help="control: the same run without the boundary must fail")
    options = parser.parse_args()
    validator = BoundaryValidator(options)
    try:
        V.enable_owned_reaping()
        try:
            validator.validate()
        except BoundaryScopeEnd as end:
            validator.receipt["acp_boundary"]["stopped_before"] = str(end); validator.save()
        missing = [n for n in REFUSED_REPLIES if n not in validator.receipt["acp_boundary"]["refused_replies"]]
        validator.check("every same-name update reached the boundary's refusal", options.without_boundary or not missing, missing)
    except Exception:
        validator.receipt["failure"] = V.traceback.format_exc(); validator.save()
        raise
    finally:
        if validator.http:
            validator.http.shutdown(); validator.http.server_close()
            validator.receipt["http_events"] = validator.http.events; validator.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
