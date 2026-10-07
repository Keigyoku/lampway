# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""T3 offline docs contract: registry first, then pinned source behaviour."""
from lampway_server.agent.tools import TOOLS
import asyncio
import pytest
from lampway_server.agent import blender_docs_tools as docs


def call(**arguments):
    return asyncio.run(docs.call("lampway_blender_docs", arguments))


def test_offline_blender_docs_is_registered():
    matches = [tool for tool in TOOLS if tool.name == "lampway_blender_docs"]
    assert len(matches) == 1, "T3 offline Blender documentation tool is absent"
    assert matches[0].parameters["additionalProperties"] is False


def test_get_object_location_from_own_build():
    result, failed = call(view="get", identifier="bpy.types.Object.location", full=True)
    assert not failed
    assert result["count"] == 1
    assert "Location of the object" in result["data"]["doc"]
    assert ":type: mathutils.Vector" in result["data"]["doc"]
    assert result["data"]["kind"] == "attribute"


def test_manual_bevel_modifier_ranks_first():
    result, failed = call(view="search", query="bevel modifier", scope="manual")
    assert not failed
    assert result["data"]["results"][0]["title"].startswith("Bevel Modifier")
    assert result["data"]["results"][0]["rank"] == 1


def test_manual_search_help_carries_scope_and_get_reads_same_page():
    result, failed = call(view="search", query="bevel modifier", scope="manual")
    assert not failed
    assert "lampway_blender_docs view=get identifier=<id> scope=manual" in result["help"]
    identifier = result["data"]["results"][0]["identifier"]
    page, failed = call(view="get", identifier=identifier, scope="manual", full=True)
    assert not failed and page["count"] == 1
    assert page["data"]["kind"] == "manual"
    assert "Bevel Modifier" in page["data"]["doc"]
    assert page["data"]["children"] == []


@pytest.mark.parametrize("identifier", ["../../private", "/etc/passwd", "modeling\\private", "modeling/../private"])
def test_manual_get_refuses_path_traversal(identifier):
    result, failed = call(view="get", identifier=identifier, scope="manual")
    assert failed and result["code"] == "bad_argument"


def test_missing_identifier_is_definitive_empty_with_search_help():
    result, failed = call(view="get", identifier="bpy.types.DoesNotExistAtAll")
    assert not failed
    assert result["count"] == result["total"] == 0
    assert result["data"]["results"] == []
    assert any("view=search" in template for template in result["help"])


@pytest.mark.parametrize("arguments,code", [
    ({"unknown": True}, "unknown_argument"),
    ({"view": "unknown"}, "bad_argument"),
    ({"limit": 51}, "bad_argument"),
    ({"limit": True}, "bad_argument"),
    ({"context": -1}, "bad_argument"),
    ({"view": "get"}, "bad_argument"),
    ({"view": "search", "query": ""}, "bad_argument"),
    ({"view": "get", "identifier": "../../private"}, "bad_argument"),
])
def test_invalid_arguments_refused(arguments, code):
    result, failed = asyncio.run(docs.call("lampway_blender_docs", arguments))
    assert failed
    assert result["code"] == code
    assert result["help"]


def test_home_reports_real_pinned_versions_and_index_sizes():
    result, failed = call()
    assert not failed
    assert result["tool"] == "lampway_blender_docs"
    assert result["data"]["versions"]["blender"] == "0.1.0"
    assert result["data"]["versions"]["core"] == "5.2.0"
    assert result["data"]["index_sizes"]["api"] > 1900
    assert result["data"]["index_sizes"]["manual"] > 2300


def test_home_backlinks_match_repository_pin_and_report_url_verification():
    from pathlib import Path
    import subprocess
    from lampway_server.blender_docs import index
    root = Path(__file__).resolve().parents[2]
    pin = subprocess.check_output(["git", "rev-parse", "HEAD:upstream"], cwd=root, text=True).strip()
    result, failed = call()
    assert not failed
    provenance = result["data"]["provenance"]
    assert provenance["source_pin"]["revision"] == pin == index.manifest()["upstream_revision"]
    assert provenance["source_pin"]["version"] == result["data"]["versions"]["core"]
    assert provenance["source_pin"]["url"].endswith("/commit/" + pin)
    assert provenance["source_pin"]["authority"] == "repository HEAD:upstream"
    assert provenance["manual"]["revision"] == index.manifest()["manual_revision"]
    assert provenance["manual"]["url"].endswith("/commit/" + provenance["manual"]["revision"])
    links = provenance["documentation_links"]
    assert links["api"]["url"] == "https://docs.blender.org/api/5.2/"
    assert links["manual"]["url"] == "https://docs.blender.org/manual/en/5.2/"
    assert all(link["verification"]["http_status"] == 403 for link in links.values())
    assert all(link["verification"]["availability"] == "unverified_access_refused" for link in links.values())


def test_provenance_derivation_matches_packaged_metadata():
    from pathlib import Path
    from lampway_server.blender_docs import index, provenance
    root = Path(__file__).resolve().parents[2]
    assert provenance.source_pin(root) == index.manifest()["provenance"]["source_pin"]


def test_provenance_derivation_refuses_stale_corpus():
    from pathlib import Path
    from lampway_server.blender_docs import index, provenance
    root = Path(__file__).resolve().parents[2]
    stale = dict(index.manifest(), upstream_revision="0" * 40)
    with pytest.raises(ValueError, match="regenerate data"):
        provenance.update(root, stale)


def test_short_doc_has_full_hint_and_wildcard_children_respect_limit():
    result, failed = call(view="get", identifier="bpy.types.Object")
    assert not failed
    assert "full=true" in result["data"]["doc"]
    result, failed = call(view="get", identifier="bpy.types.*", limit=2)
    assert not failed
    assert result["count"] == 2 < result["total"]
    assert len(result["data"]["children"]) == 2


def test_help_and_server_only_script_guard():
    from lampway_server.agent.tools import script_for, UnknownTool
    result, failed = call(view="help")
    assert not failed
    assert result["data"]["arguments"] == docs.PARAMETERS["properties"]
    with pytest.raises(UnknownTool, match="runs on the server"):
        script_for("lampway_blender_docs", {})


def test_all_bundled_rst_match_pinned_manifest():
    from lampway_server.blender_docs import index
    import hashlib
    manifest = index.manifest()
    actual = {str(path.relative_to(index.DATA)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in index.DATA.rglob("*.rst")}
    assert actual == manifest["files_sha256"]


def test_serialized_manifest_keeps_hashes_and_licenses_as_typed_records():
    from lampway_server.blender_docs import index
    import json
    raw = json.loads((index.DATA / "manifest.json").read_text())
    assert raw.get("format_version") == 2
    assert isinstance(raw["files_sha256"], list)
    assert {row["path"]: row["sha256"] for row in raw["files_sha256"]} == index.manifest()["files_sha256"]
    assert raw["api_generator"]["path"] == "doc/python_api/sphinx_doc_gen.py"
    assert raw["api_generator"]["sha256"] == index.manifest()["api_generator_sha256"]
    assert {row["scope"]: row["identifier"] for row in raw["source_licenses"]} == index.manifest()["source_licenses"]


def test_manifest_normalization_refuses_duplicate_digest_paths():
    from lampway_server.blender_docs import index
    import json
    raw = json.loads((index.DATA / "manifest.json").read_text())
    assert raw.get("format_version") == 2
    raw["files_sha256"].append(raw["files_sha256"][0])
    with pytest.raises(ValueError, match="duplicate"):
        index.normalize_manifest(raw)


def test_publication_derivatives_preserve_provenance_and_documented_operations():
    from lampway_server.blender_docs import index
    import hashlib
    manifest = index.manifest()
    derivatives = manifest.get("publication_derivatives", {})
    assert len(derivatives) == 3, "publication derivatives need original and packaged provenance"
    for path, provenance in derivatives.items():
        content = (index.DATA / path).read_bytes()
        assert provenance["packaged_sha256"] == hashlib.sha256(content).hexdigest()
        assert provenance["packaged_sha256"] == manifest["files_sha256"][path]
        assert provenance["upstream_original_sha256"] != provenance["packaged_sha256"]
        assert len(provenance["upstream_original_sha256"]) == 64
        assert provenance["changed_lines"] == 1
        assert provenance["source_revision"] == manifest[
            "upstream_revision" if path.startswith("api/") else "manual_revision"]
    token_page, failed = call(view="get", scope="manual", full=True,
                             identifier="advanced/extensions/creating_repository/dynamic_repository")
    assert not failed
    assert 'Authorization: Bearer <ACCESS-TOKEN>' in token_page["data"]["doc"]
    fork_page, failed = call(view="get", scope="manual", full=True,
                            identifier="contribute/manual/getting_started/local_editing/pull_requests")
    assert not failed
    assert 'git remote add me <SSH-REMOTE-URL>' in fork_page["data"]["doc"]
    assert 'Click *SSH* to see the correct URL' in fork_page["data"]["doc"]
    api_page, failed = call(view="get", identifier="info_overview", full=True)
    assert not failed
    assert 'blender --python /path/to/my_script.py' in api_page["data"]["doc"]


def test_documentation_search_still_finds_modified_pages():
    searches = [("Authorization header", "manual", "advanced/extensions/creating_repository/dynamic_repository"),
                ("personal fork", "manual", "contribute/manual/getting_started/local_editing/pull_requests"),
                ("run scripts directly", "api", "info_overview")]
    for query, scope, identifier in searches:
        result, failed = call(view="search", query=query, scope=scope, limit=50)
        assert not failed
        assert identifier in {row["identifier"] for row in result["data"]["results"]}


def test_in_app_dispatch_keeps_json_and_never_asks_blender(monkeypatch):
    import json
    from lampway_server.agent.turns import AgentHub
    from lampway_server.agent.providers.base import ToolCall
    hub = AgentHub(None)
    def forbidden(*args, **kwargs):
        raise AssertionError("offline docs must not contact Blender or the network")
    monkeypatch.setattr(hub, "_blender_script", forbidden)
    import socket
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    text, failed = asyncio.run(hub._run_tool(None, None, None, ToolCall("docs", "lampway_blender_docs", {})))
    assert not failed
    assert json.loads(text)["data"]["versions"]["core"] == "5.2.0"
