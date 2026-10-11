# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaging-time provenance from the same repository pin used by the build.

Runtime documentation reads only the packaged manifest. This command deliberately
requires the source checkout and never selects a newer version or uses a network.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess


def source_pin(root):
    def git(path, *arguments):
        return subprocess.check_output(["git", "-C", str(path), *arguments], text=True).strip()

    revision = git(root, "rev-parse", "HEAD:upstream")
    repository = git(root, "config", "--file", ".gitmodules", "--get", "submodule.upstream.url")
    header = git(root / "upstream", "show", revision + ":source/blender/blenkernel/BKE_blender_version.h")
    version = int(re.search(r"^#define BLENDER_VERSION (\d+)$", header, re.MULTILINE)[1])
    patch = int(re.search(r"^#define BLENDER_VERSION_PATCH (\d+)$", header, re.MULTILINE)[1])
    return {"authority": "repository HEAD:upstream", "repository": repository,
            "revision": revision, "version": f"{version // 100}.{version % 100}.{patch}",
            "url": repository.removesuffix(".git") + "/commit/" + revision}


def update(root, manifest):
    pin = source_pin(root)
    if pin["revision"] != manifest["upstream_revision"] or pin["version"] != manifest["core_version"]:
        raise ValueError("documentation corpus differs from build pin; regenerate data before publishing")
    series = ".".join(pin["version"].split(".")[:2])
    provenance = manifest.setdefault("provenance", {})
    provenance["source_pin"] = pin
    provenance["manual"] = {"repository": manifest["manual_repository"],
                            "revision": manifest["manual_revision"],
                            "url": manifest["manual_repository"].removesuffix(".git") + "/commit/" + manifest["manual_revision"]}
    links = provenance.setdefault("documentation_links", {})
    for scope, url in {"api": f"https://docs.blender.org/api/{series}/",
                       "manual": f"https://docs.blender.org/manual/en/{series}/"}.items():
        old = links.get(scope, {})
        links[scope] = {"url": url, "verification": old.get("verification", {}) if old.get("url") == url
                       else {"availability": "unverified"}}
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    path = Path(__file__).with_name("data") / "manifest.json"
    original = json.loads(path.read_text(encoding="utf-8"))
    derived = update(arguments.repository, json.loads(json.dumps(original)))
    if arguments.check:
        if derived != original:
            raise SystemExit("packaged documentation provenance is stale")
        print("packaged documentation provenance matches repository build pin")
    else:
        path.write_text(json.dumps(derived, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
