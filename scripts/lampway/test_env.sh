#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# THE test environment, defined in the repository (the reference the gate uses, in a fresh worktree):
#   1. upstream/ checked out at the pinned commit (the gitlink in HEAD), WITHOUT its LFS payload and without lib/ (tests read sources only).
#      A local object source is used when one exists (LAMPWAY_UPSTREAM_REFERENCE, else any sibling worktree's upstream module that has the
#      pinned commit); otherwise a shallow fetch of that one commit from the submodule's URL.
#   2. the test interpreter (LAMPWAY_TEST_PYTHON, default python3) gets tests/requirements-test.txt and the server's declared dependency
#      ranges (dependencies + extras test, local-embeddings). Nothing is installed editable.
#   3. the shelf, READ ONLY: export LAMPWAY_SHELF_DIR (and LAMPWAY_SHELF_SCRATCH when its scratch is not <shelf>/scratch) to the machine's
#      copy of the owner's recorded fixtures; test_all requires its placement fixtures (test_all.py SHELF_FILES), fails a shelf test that
#      would skip, and fails a run that wrote to it. The path is the machine's: it is never written in the repository.
#   4. the i18n template (src/scripts/mixar/modules/common/i18n/locale/mixar.pot, git-ignored) is written from the source and upstream/.
#   5. test_all.py --verify-env must then pass (after the motion-browser notice, 6).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${LAMPWAY_TEST_PYTHON:-python3}"
PIN="$(git -C "$ROOT" rev-parse HEAD:upstream)"
NOLFS=(-c filter.lfs.process= -c filter.lfs.smudge=cat -c filter.lfs.clean=cat -c filter.lfs.required=false)

have_pin() { [ -e "$ROOT/upstream/.git" ] && [ "$(git -C "$ROOT/upstream" rev-parse HEAD 2>/dev/null)" = "$PIN" ]; }

if have_pin; then
  echo "upstream: at the pin $PIN"
else
  REF="${LAMPWAY_UPSTREAM_REFERENCE:-}"
  if [ -z "$REF" ]; then
    COMMON="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)"
    for cand in "$COMMON"/modules/upstream "$COMMON"/worktrees/*/modules/upstream; do
      [ -d "$cand" ] && git -C "$cand" cat-file -e "$PIN^{commit}" 2>/dev/null && { REF="$cand"; break; }
    done
  fi
  rm -rf "$ROOT/upstream" && mkdir -p "$ROOT/upstream"
  if [ -n "$REF" ]; then
    echo "upstream: from the local object source $REF"
    rmdir "$ROOT/upstream"
    git "${NOLFS[@]}" clone -q --shared --no-checkout "$REF" "$ROOT/upstream"
  else
    URL="$(git -C "$ROOT" config -f .gitmodules submodule.upstream.url)"
    echo "upstream: shallow fetch of $PIN from $URL"
    git -C "$ROOT/upstream" init -q
    git -C "$ROOT/upstream" "${NOLFS[@]}" fetch -q --depth 1 "$URL" "$PIN"
  fi
  for kv in "process=" "smudge=cat" "clean=cat" "required=false"; do git -C "$ROOT/upstream" config "filter.lfs.${kv%%=*}" "${kv#*=}"; done
  GIT_LFS_SKIP_SMUDGE=1 git -C "$ROOT/upstream" "${NOLFS[@]}" -c advice.detachedHead=false checkout -q -f "$PIN"
  have_pin || { echo "upstream: could not check out $PIN" >&2; exit 2; }
fi

SERVER_REQS="$(mktemp)"
trap 'rm -f "$SERVER_REQS"' EXIT
"$PY" - "$ROOT/server/pyproject.toml" > "$SERVER_REQS" <<'PYEOF'
import sys, tomllib
d = tomllib.load(open(sys.argv[1], "rb"))["project"]
out = list(d.get("dependencies", []))
for extra in ("test", "local-embeddings"):
    out += d.get("optional-dependencies", {}).get(extra, [])
print("\n".join(out))
PYEOF
"$PY" -m pip install -q -r "$ROOT/tests/requirements-test.txt" -r "$SERVER_REQS"
# the i18n template is git-ignored (generated from the source and upstream/): tests/i18n reads it, so the environment writes it
"$PY" "$ROOT/scripts/i18n/extract_messages.py" > /dev/null
# 6. the motion-graphics real-browser tests need a headless Chromium (BUILD-LAMPWAY.md section 8); without one they skip inside the server's
#    skip count, so say so here. A notice, never a failure: the rest of the suite does not need it.
if [ -n "${LAMPWAY_CHROMIUM:-}" ] && [ -x "$LAMPWAY_CHROMIUM" ]; then
  echo "motion: headless Chromium at LAMPWAY_CHROMIUM=$LAMPWAY_CHROMIUM"
else
  echo "motion: LAMPWAY_CHROMIUM is unset or not executable: the real-browser motion tests will SKIP (BUILD-LAMPWAY.md section 8)" >&2
fi
"$PY" "$ROOT/scripts/lampway/test_all.py" --verify-env
