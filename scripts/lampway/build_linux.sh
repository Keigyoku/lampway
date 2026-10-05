#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Lampway: idempotent Linux build of the forked client.
#
#   scripts/lampway/build_linux.sh              # deps, submodules, build, print binary
#   scripts/lampway/build_linux.sh --plan       # resolve and print what WOULD be used
#   scripts/lampway/build_linux.sh --check-deps # exit 2 naming any missing build tool
#   scripts/lampway/build_linux.sh --sync-only  # submodules + libs, no compile
#
# Every step is a no-op when its result is already in place, so re-running after
# a failure (or a `git pull`) only does the remaining work. Run it INSIDE the
# build environment (the lampway-build distrobox); see BUILD-LAMPWAY.md.
#
# Inputs (environment; a .env that contradicts them is refused, see below):
#   MIXAR_ENV            Dev (default) | Prod | UAT   -> build/<MIXAR_ENV>/
#   MIXAR_CUDA           0 (default: no CUDA/OptiX/cubins) | 1
#   MIXAR_BACKEND_URL    baked backend; default https://lampway.invalid (never
#   MIXAR_FRONTEND_URL   resolves, RFC 2606) so a build cannot reach mixar.app
#   CC / CXX             compilers; default gcc-14/g++-14 when present (Blender
#                        5.2 refuses GCC < 14; Ubuntu 24.04's default is 13)
#   BUILD_CORES          parallel jobs (default: nproc, via settings.sh)
#   LAMPWAY_MIN_FREE_GB  refuse to start a big step below this (default 100)
#   LAMPWAY_LOG_DIR      where build logs go (default build/logs)
#
# Exit codes: 0 ok, 2 missing tools, 3 .env conflict, 4 disk floor, 5 pin or
# binary verification failed, 1 anything else.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIXAR_ENV="${MIXAR_ENV:-Dev}"
MIXAR_CUDA="${MIXAR_CUDA:-0}"
MIXAR_BACKEND_URL="${MIXAR_BACKEND_URL:-https://lampway.invalid}"
MIXAR_FRONTEND_URL="${MIXAR_FRONTEND_URL:-https://lampway.invalid}"
LAMPWAY_MIN_FREE_GB="${LAMPWAY_MIN_FREE_GB:-100}"
LAMPWAY_LOG_DIR="${LAMPWAY_LOG_DIR:-$ROOT_DIR/build/logs}"
LIB_SUBMODULE="lib/linux_x64"
BINARY="$ROOT_DIR/build/$MIXAR_ENV/bin/mixar"
MIN_COMPILER_MAJOR=14

# Compiler: an explicit CC/CXX wins; otherwise prefer the versioned GCC 14
# pair Ubuntu 24.04 ships beside its default GCC 13; otherwise the defaults.
pick_compiler() {
    if [[ -n "${CC:-}" ]]; then
        CXX="${CXX:-c++}"
    elif command -v gcc-14 >/dev/null 2>&1 && command -v g++-14 >/dev/null 2>&1; then
        CC=gcc-14; CXX=g++-14
    else
        CC="${CC:-gcc}"; CXX="${CXX:-g++}"
    fi
}
pick_compiler

compiler_major() {
    local v
    v="$("$1" -dumpfullversion 2>/dev/null || "$1" -dumpversion 2>/dev/null || true)"
    echo "${v%%.*}" | tr -dc '0-9'
}

die() { echo "build_linux.sh: $*" >&2; exit "${_rc:-1}"; }
say() { echo "[lampway] $*"; }

# ---------------------------------------------------------------------------
# .env: settings.sh sources it AFTER inheriting our environment, so a value in
# .env silently overrides the one we export. Refuse that instead of building the
# wrong thing. Only the two knobs this script owns are checked.
# ---------------------------------------------------------------------------
check_dotenv() {
    local env_file="$ROOT_DIR/.env" key want have
    [[ -f "$env_file" ]] || return 0
    for key in MIXAR_ENV MIXAR_CUDA MIXAR_BACKEND_URL MIXAR_FRONTEND_URL; do
        want="${!key}"
        have="$(sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$key=//p" "$env_file" \
            | tail -n1 | sed -E 's/[[:space:]]*#.*$//; s/^["'"'"']//; s/["'"'"']$//')"
        if [[ -n "$have" && "$have" != "$want" ]]; then
            _rc=3 die ".env sets $key=$have but this run asked for $key=$want." \
                "Unset it in .env or export the same value."
        fi
    done
}

# ---------------------------------------------------------------------------
# Tools. The header set is upstream's install_linux_packages.py "mandatory"
# list (Blender 5.2) plus what the Mixar overlay adds (rsync + python3 for the
# scripts, pkg-config for libsecret/curl/openssl discovery). Checked by command
# and by pkg-config module so the error names the package, not a CMake line.
# ---------------------------------------------------------------------------
REQUIRED_COMMANDS=(git cmake c++ gcc make python3 rsync pkg-config)
REQUIRED_PKGCONFIG=(x11 xxf86vm xcursor xi xrandr xinerama xkbcommon
    wayland-client wayland-protocols libdecor-0 dbus-1 gl egl
    libsecret-1 libcurl openssl)
APT_HINT="sudo apt install build-essential git git-lfs cmake ninja-build python3 rsync \
pkg-config libx11-dev libxxf86vm-dev libxcursor-dev libxi-dev libxrandr-dev \
libxinerama-dev libxkbcommon-dev libwayland-dev libdecor-0-dev wayland-protocols \
libdbus-1-dev libgl-dev libegl-dev libsecret-1-dev libcurl4-openssl-dev libssl-dev zenity"

check_deps() {
    local missing=() c m
    for c in "${REQUIRED_COMMANDS[@]}"; do
        command -v "$c" >/dev/null 2>&1 || missing+=("$c")
    done
    if command -v git >/dev/null 2>&1 && ! git lfs version >/dev/null 2>&1; then
        missing+=("git-lfs")
    fi
    if command -v pkg-config >/dev/null 2>&1; then
        for m in "${REQUIRED_PKGCONFIG[@]}"; do
            pkg-config --exists "$m" 2>/dev/null || missing+=("pkg-config:$m")
        done
    fi
    local compiler major
    for compiler in "$CC" "$CXX"; do
        if command -v "$compiler" >/dev/null 2>&1; then
            major="$(compiler_major "$compiler")"
            if [[ -z "$major" ]] || (( major < MIN_COMPILER_MAJOR )); then
                missing+=("$compiler>=${MIN_COMPILER_MAJOR}(found ${major:-?})")
            fi
        else
            missing+=("$compiler")
        fi
    done
    if (( ${#missing[@]} > 0 )); then
        echo "build_linux.sh: missing build tools: ${missing[*]}" >&2
        echo "  Blender 5.2 needs GCC >= ${MIN_COMPILER_MAJOR} (or clang >= 17); set CC/CXX or install gcc-14 g++-14." >&2
        echo "  on Ubuntu 24.04: $APT_HINT" >&2
        return 2
    fi
    command -v ninja >/dev/null 2>&1 || say "ninja not found; CMake will use Makefiles (slower incremental builds)"
    command -v zenity >/dev/null 2>&1 || say "zenity not found; the Prod login gate's error dialogs will be silent"
    return 0
}

# ---------------------------------------------------------------------------
# Pins. The superproject commits a gitlink for upstream/; upstream commits one
# for lib/linux_x64. Both are read from git, never from a tree that may be
# stale.
# ---------------------------------------------------------------------------
# HEAD of the repository rooted EXACTLY at $1, or nothing. A fresh clone has
# an empty upstream/ directory and `git -C upstream rev-parse HEAD` walks up to
# the superproject and answers with its head, which would look like a
# populated submodule at the wrong commit.
repo_head_at() {
    local dir="$1" top
    [[ -d "$dir" ]] || return 0
    top="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || true)"
    [[ -n "$top" && "$(cd "$top" && pwd -P)" == "$(cd "$dir" && pwd -P)" ]] || return 0
    git -C "$dir" rev-parse HEAD 2>/dev/null || true
}
upstream_pin() { git -C "$ROOT_DIR" rev-parse "HEAD:upstream"; }
upstream_head() { repo_head_at "$ROOT_DIR/upstream"; }
lib_pin() { git -C "$ROOT_DIR/upstream" rev-parse "HEAD:$LIB_SUBMODULE" 2>/dev/null || true; }
lib_head() { repo_head_at "$ROOT_DIR/upstream/$LIB_SUBMODULE"; }

free_gb() { df -BG --output=avail "$1" | tail -n1 | tr -dc '0-9'; }

require_disk() {
    local step="$1" avail
    avail="$(free_gb "$ROOT_DIR")"
    say "disk before $step: ${avail} GB free (floor ${LAMPWAY_MIN_FREE_GB} GB)"
    if (( avail < LAMPWAY_MIN_FREE_GB )); then
        _rc=4 die "only ${avail} GB free before $step; floor is ${LAMPWAY_MIN_FREE_GB} GB. Stopping."
    fi
}

# Shallow fetch of ONE commit into a submodule, with the fallback git itself
# uses when the server will not serve an arbitrary SHA through `submodule
# update --depth`.
sync_submodule_to() {
    local parent="$1" path="$2" want="$3"
    (
        cd "$parent"
        git submodule init -- "$path" >/dev/null
        if ! GIT_LFS_SKIP_SMUDGE=1 git submodule update --init --depth 1 --progress -- "$path"; then
            say "direct SHA fetch for $path"
            git -C "$path" fetch --depth 1 --progress origin "$want"
            GIT_LFS_SKIP_SMUDGE=1 git -C "$path" checkout -q --detach "$want"
        fi
    )
}

sync_upstream() {
    local want have
    want="$(upstream_pin)"
    have="$(upstream_head)"
    if [[ "$have" == "$want" ]]; then
        say "upstream already at pin ${want:0:12}"
    else
        say "upstream: ${have:-absent} -> pin ${want:0:12} (shallow)"
        sync_submodule_to "$ROOT_DIR" upstream "$want"
        have="$(upstream_head)"
        [[ "$have" == "$want" ]] || { _rc=5 die "upstream is at ${have:-?} after sync, pin is $want"; }
    fi
}

sync_libs() {
    local want have sentinel
    want="$(lib_pin)"
    [[ -n "$want" ]] || { _rc=5 die "upstream has no gitlink for $LIB_SUBMODULE"; }
    have="$(lib_head)"
    # upstream/.gitmodules marks lib/* `update = none`; make_update.py flips it
    # to checkout for the host platform. Same here, idempotently.
    git -C "$ROOT_DIR/upstream" config --local "submodule.$LIB_SUBMODULE.update" checkout
    git lfs install --skip-repo >/dev/null
    if [[ "$have" == "$want" ]]; then
        say "$LIB_SUBMODULE already at pin ${want:0:12}"
    else
        say "$LIB_SUBMODULE: ${have:-absent} -> pin ${want:0:12} (shallow, LFS smudge skipped)"
        sync_submodule_to "$ROOT_DIR/upstream" "$LIB_SUBMODULE" "$want"
        have="$(lib_head)"
        [[ "$have" == "$want" ]] || { _rc=5 die "$LIB_SUBMODULE is at ${have:-?} after sync, pin is $want"; }
    fi
    # Stage 2 (make_utils.git_update_submodule): fetch the LFS payloads. A
    # no-op when every object is already present.
    say "git lfs pull in $LIB_SUBMODULE"
    git -C "$ROOT_DIR/upstream/$LIB_SUBMODULE" lfs pull
    # An LFS pointer file is ~130 bytes; the real interpreter is megabytes.
    sentinel="$ROOT_DIR/upstream/$LIB_SUBMODULE/python/bin/python3.13"
    if [[ ! -f "$sentinel" ]] || (( $(stat -c %s "$sentinel") < 4096 )); then
        _rc=5 die "LFS payload not materialised: $sentinel is missing or still a pointer"
    fi
}

print_plan() {
    cat <<EOF
root=$ROOT_DIR
mixar_env=$MIXAR_ENV
mixar_cuda=$MIXAR_CUDA
mixar_backend_url=$MIXAR_BACKEND_URL
mixar_frontend_url=$MIXAR_FRONTEND_URL
cc=$CC
cxx=$CXX
upstream_pin=$(upstream_pin)
upstream_head=$(upstream_head)
lib_submodule=$LIB_SUBMODULE
lib_pin=$(lib_pin)
lib_head=$(lib_head)
build_dir=$ROOT_DIR/build/$MIXAR_ENV
binary=$BINARY
log_dir=$LAMPWAY_LOG_DIR
min_free_gb=$LAMPWAY_MIN_FREE_GB
EOF
}

build() {
    local stamp log start end
    mkdir -p "$LAMPWAY_LOG_DIR"
    stamp="$(date +%Y%m%dT%H%M%S)"
    log="$LAMPWAY_LOG_DIR/build-$MIXAR_ENV-$stamp.log"
    export MIXAR_ENV MIXAR_CUDA MIXAR_BACKEND_URL MIXAR_FRONTEND_URL CC CXX
    # CMake caches the compiler on the first configure and refuses to switch;
    # a cache left by a configure with another compiler (e.g. the GCC 13 that
    # fails Blender's version gate) must go. Object files are untouched.
    local cache="$ROOT_DIR/build/$MIXAR_ENV/CMakeCache.txt" cached_cc want_cc
    if [[ -f "$cache" ]]; then
        cached_cc="$(sed -n 's/^CMAKE_C_COMPILER:[A-Z]*=//p' "$cache" | head -n1)"
        want_cc="$(command -v "$CC")"
        if [[ -n "$cached_cc" && "$(readlink -f "$cached_cc")" != "$(readlink -f "$want_cc")" ]]; then
            say "CMake cache was configured with $cached_cc, this run uses $want_cc: dropping the cache"
            rm -f "$cache"
            rm -rf "$ROOT_DIR/build/$MIXAR_ENV/CMakeFiles"
        fi
    fi
    # Ninja when available: cmake honours CMAKE_GENERATOR for a fresh build dir
    # and ignores it for an existing one, so this never fights a prior configure.
    if command -v ninja >/dev/null 2>&1; then
        export CMAKE_GENERATOR="${CMAKE_GENERATOR:-Ninja}"
    fi
    say "build: MIXAR_ENV=$MIXAR_ENV MIXAR_CUDA=$MIXAR_CUDA BUILD_CORES=${BUILD_CORES:-$(nproc)} CC=$CC CXX=$CXX"
    say "build: MIXAR_BACKEND_URL=$MIXAR_BACKEND_URL MIXAR_FRONTEND_URL=$MIXAR_FRONTEND_URL log=$log"
    start="$(date +%s)"
    "$ROOT_DIR/scripts/unix/build.sh" 2>&1 | tee "$log"
    end="$(date +%s)"
    say "build.sh finished in $(( (end - start) / 60 )) min $(( (end - start) % 60 )) s"
    [[ -x "$BINARY" ]] || { _rc=5 die "build.sh returned 0 but $BINARY is not an executable"; }
    say "disk after build: $(free_gb "$ROOT_DIR") GB free"
    say "binary: $BINARY"
    echo "$BINARY"
}

usage() { sed -n '7,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

main() {
    local mode="build"
    case "${1:-}" in
        "") ;;
        --plan) mode=plan ;;
        --check-deps) mode=deps ;;
        --sync-only) mode=sync ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 1 ;;
    esac

    check_dotenv
    case "$mode" in
        plan) print_plan; exit 0 ;;
        deps) check_deps; exit $? ;;
    esac
    check_deps || exit $?

    require_disk "upstream fetch"
    sync_upstream
    require_disk "precompiled libraries (LFS)"
    sync_libs
    [[ "$mode" == sync ]] && { say "sync complete (no build requested)"; exit 0; }

    require_disk "compile"
    build
}

main "$@"
