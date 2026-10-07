#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# What a native build was compiled from (build/<env>/BUILT_FROM). build_linux.sh reads the state before it compiles and
# stamps after it succeeds; a bare sha is written only for a clean, pushed tree that held still for the whole build.
#
#   built_from.sh state <repo>                      one line: <sha> | UNCLEAN <sha>: <paths> | UNPUSHED <sha>
#   built_from.sh stamp <repo> <build dir> <start>  writes <build dir>/BUILT_FROM from <start> and the state now
#
# "Native" is what the compiler reads: src/source, src/CMakeLists.txt, src/build_files and src/release/datafiles
# (tracked edits and untracked files alike). "Pushed" means some remote-tracking branch contains the commit.

set -euo pipefail

NATIVE=(src/source src/CMakeLists.txt src/build_files src/release/datafiles)

state() {
    local repo="$1" sha dirty
    sha="$(git -C "$repo" rev-parse HEAD)"
    dirty="$(git -C "$repo" status --porcelain --untracked-files=all -- "${NATIVE[@]}" | cut -c4- | head -n 5 | paste -sd ' ' -)"
    if [[ -n "$dirty" ]]; then
        echo "UNCLEAN $sha: native sources differ from the commit ($dirty)"
    elif [[ -z "$(git -C "$repo" branch -r --contains "$sha" 2>/dev/null)" ]]; then
        echo "UNPUSHED $sha"
    else
        echo "$sha"
    fi
}

stamp() {
    local repo="$1" out="$2" start="$3" now
    now="$(state "$repo")"
    if [[ "$now" != "$start" ]]; then
        printf 'UNCLEAN %s: the native tree changed during the build (at the start: %s; at the end: %s)\n' \
            "$(git -C "$repo" rev-parse HEAD)" "$start" "$now" > "$out/BUILT_FROM"
    else
        echo "$start" > "$out/BUILT_FROM"
    fi
    cat "$out/BUILT_FROM"
}

case "${1:-}" in
    state) state "$2" ;;
    stamp) stamp "$2" "$3" "$4" ;;
    *) sed -n '9,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 1 ;;
esac
