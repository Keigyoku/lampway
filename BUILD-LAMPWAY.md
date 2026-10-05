<!-- SPDX-FileCopyrightText: 2026 Keigyoku -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Building Lampway on Linux

One script, run inside a clean Ubuntu 24.04 build environment, takes the tree
from a fresh clone to a runnable `build/<env>/bin/mixar`:

```bash
scripts/lampway/build_linux.sh            # deps check, submodules + LFS, build
scripts/lampway/build_linux.sh --plan     # print what a run would use; touches nothing
scripts/lampway/build_linux.sh --check-deps
scripts/lampway/build_linux.sh --sync-only
```

Everything below was measured on 2026-10-04/05 on the machine described in
"Reference run". Numbers are from that run, not estimates.

## 1. Build environment

Blender 5.2 refuses GCC older than 14 and Ubuntu 24.04 ships 13.3 by default,
so the versioned pair is required. Inside the box (a distrobox named
`lampway-build` here; any Ubuntu 24.04 works):

```bash
sudo apt-get install -y --no-install-recommends \
  build-essential gcc-14 g++-14 git git-lfs cmake ninja-build python3 python3-venv rsync pkg-config \
  libx11-dev libxxf86vm-dev libxcursor-dev libxi-dev libxrandr-dev libxinerama-dev \
  libxkbcommon-dev libwayland-dev libdecor-0-dev wayland-protocols libdbus-1-dev \
  libgl-dev libegl-dev libsecret-1-dev libcurl4-openssl-dev libssl-dev zenity
# runtime only (the binary dlopens these; not pulled in by the -dev set above)
sudo apt-get install -y --no-install-recommends libsm6 libice6
```

The first set is upstream's own mandatory list for 5.2
(`upstream/build_files/build_environment/install_linux_packages.py`) plus
what the Mixar overlay adds: `libsecret-1` (the keyring the native token
store uses), `libcurl`/`openssl` (`src/source/creator/CMakeLists.txt`
`find_package(... REQUIRED)` on UNIX), `rsync` and `python3` for the overlay
and config scripts, `pkg-config` for discovery. `zenity` is only shelled out to
by the upstream login gate's error dialogs, which Lampway compiles out; it is
harmless to install.

`scripts/lampway/build_linux.sh --check-deps` names anything missing (exit 2),
including a compiler below 14; it prints this apt line.

## 2. What the script does, in order

| step | what | idempotent because |
|---|---|---|
| `.env` guard | refuses a `.env` whose `MIXAR_ENV` / `MIXAR_CUDA` / URL differs from what you asked for (exit 3). `settings.sh` sources `.env` *after* the environment, so `.env` would silently win. | pure check |
| deps | commands + `pkg-config` modules + compiler major >= 14 (exit 2) | pure check |
| disk floor | stops (exit 4) if free space on the tree's filesystem is below `LAMPWAY_MIN_FREE_GB` (default 100) before each big step | pure check |
| `upstream/` | `git submodule update --init --depth 1` at the gitlink the superproject commits (`git rev-parse HEAD:upstream`); falls back to a direct `fetch --depth 1 origin <sha>` if the server refuses the shallow SHA | skipped when `upstream/` is already at the pin |
| upstream LFS | `git lfs pull` in `upstream/` — `blender.git` keeps `startup.blend` and every bundled asset in LFS; without this the build embeds a 131-byte pointer as the factory startup file and the first window segfaults | no-op once objects are present; verified by upstream's own check (`startup.blend` >= 1024 B) |
| `lib/linux_x64` | upstream marks `lib/*` `update = none`; the script sets `submodule.lib/linux_x64.update=checkout`, shallow-fetches the pinned commit with `GIT_LFS_SKIP_SMUDGE=1`, then `git lfs pull` — the two-stage recipe from `upstream/build_files/utils/make_utils.py::git_update_submodule` | skipped at pin; LFS pull is a no-op when complete; verified by `python/bin/python3.13` being a real ELF |
| compiler | `CC`/`CXX` if set, else `gcc-14`/`g++-14` if present, else `gcc`/`g++`; a CMake cache configured with a *different* compiler is dropped (objects kept) | cache only dropped on mismatch |
| build | exports `MIXAR_ENV` (default `Dev`), `MIXAR_CUDA` (default `0`), `CMAKE_GENERATOR=Ninja` when ninja exists, then runs the repo's own `scripts/unix/build.sh` (overlay -> CMake -> compile -> install -> embedded-Python packages -> `check_python_runtime.py`), tee'd to `build/logs/build-<env>-<stamp>.log` | Ninja; a second run relinks and reinstalls only |
| result | verifies `build/<env>/bin/mixar` is executable (exit 5 otherwise) and prints its path as the last stdout line | — |

Service URLs: unset means the tree's default (`scripts/unix/settings.sh`,
`src/scripts/mixar/config/brand.py` -> `http://127.0.0.1:8787`, our server).
Set `MIXAR_BACKEND_URL` / `MIXAR_FRONTEND_URL` to bake another host; the
`.env` guard then covers them too. `--plan` shows every resolved value.

`MIXAR_CUDA=0` builds without CUDA/OptiX and without the Cycles GPU kernels
(`cmake/mixar_overrides.cmake`), which is what makes a clean build fit in
under an hour; Cycles renders on CPU only in such a build. Set `MIXAR_CUDA=1`
for a GPU build (needs the CUDA toolkit; not measured here).

The script never writes `.env`, never touches `source/` or `build/` except
through `scripts/unix/build.sh`, and never runs on the host: run it inside the
box. If `distrobox enter` answers `unable to find user <you>` right after a
previous session ended (seen repeatedly on this host; podman drops the
rootless container's mounts between exec sessions), the numeric form still
works:

```bash
podman exec --user 1000:1000 -w "$PWD" lampway-build ./scripts/lampway/build_linux.sh
```

## 3. Reference run (2026-10-04, this machine)

Host: Linux 7.2 (Fedora, `/var/home` on NVMe, shared with other work); box:
Ubuntu 24.04, 16 cores, 30 GB RAM of which 8-11 GB were free during the run
because other builds shared the host — the script's wrapper picked
`BUILD_CORES=5` (free GB / 2). Expect a clean compile to be roughly
proportional to the cores you can give it. Toolchain: gcc 14.2.0, cmake
3.28.3, ninja 1.11.1, git-lfs 3.4.1, Python 3.12 on the box (the app embeds
3.13 from the precompiled libs).

| step | wall time | notes |
|---|---|---|
| `upstream/` shallow fetch at `fbe6228777e7` (= tag v5.2.0) | ~2 min | 15 497 objects |
| `lib/linux_x64` shallow fetch at `30d9f881c4b6` + `git lfs pull` (785 LFS files, 2.0 GB) | 1 min 48 s | fast link; 2.9 MiB/s sustained for the git part |
| `git lfs pull` in `upstream/` (6 659 LFS files) | ~1 min (inside a 2 min 54 s `--sync-only`) | |
| clean build, Dev, `MIXAR_CUDA=0`, 5 jobs, Ninja | **41 min 17 s** | 8 472 build steps; no warnings-as-errors hit |
| second run, nothing changed | 1 min 4 s | overlay rsync + reconfigure + relink + install + pip |
| incremental rebuild after merging `lp/fork-patches` (93 files, a widely included header) | 10 min 18 s | 580 steps, 4 jobs |
| rebuild after the upstream LFS pull (datatoc re-embeds `startup.blend`, assets re-installed) | 1 min 40 s | |

Disk (all under the worktree except git metadata, which git keeps in the main
checkout's `.git/worktrees/<name>/modules/`):

| what | size |
|---|---|
| `upstream/` checkout incl. `lib/linux_x64` (2.3 GB) and LFS assets | 3.4 GB |
| git metadata for `upstream` + `lib/linux_x64` (packs + LFS object stores, under the main checkout's `.git/worktrees/wt-build/modules/`) | 2.9 GB |
| `source/` (generated overlay of upstream + src) | 3.5 GB |
| `build/Dev/` (objects + installed app; `bin/mixar` is 248 MB) | 3.4 GB |
| **total for one environment** | **~13 GB** |

Free space went 234 GB -> 173 GB over the whole session, but most of that was
other work on the same disk; this tree accounts for ~13 GB per built
environment (+3.4 GB per extra `build/<env>`), well inside the 45 GB budget.

## 4. Smoke tests (Dev build, merged `lp/fork-patches`)

Blender returns 0 even when `--python-expr` raises; pass `--python-exit-code 1`
for an honest code.

```bash
B=build/Dev/bin/mixar
$B --background --version                       # "Blender 4.2.2 (hash fbe6228777e7 ...)"  rc=0
$B --background --python-exit-code 1 --python-expr "import mixar; print('addon ok')"   # rc=0
$B --background --python-exit-code 1 --python-expr "import mixar.modules.paint"         # rc=0
$B --background --python-exit-code 1 --python-expr "from mixar.modules.paint.ui import ui"  # rc=1 (see below)
```

`import mixar` works because `scripts/startup/bootstrap/__init__.py` puts
`<install>/5.2/scripts` on `sys.path` at startup; `mixar/__init__.py` itself
imports nothing. The version string says "Blender 4.2.2" because the Mixar
`VERSION` file (4.2.2) replaces Blender's version; the hash is the Blender
commit.

Windowed start without a display server of your own (Mesa llvmpipe):

```bash
sudo apt-get install -y --no-install-recommends xvfb libgl1-mesa-dri libegl-mesa0 libgl1 libegl1
LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a -s "-screen 0 1280x800x24" build/Dev/bin/mixar \
  --python-expr "import bpy; bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=20.0)"
# rc=0 after ~23 s; six non-fatal "EGL Error (0x3009): EGL_BAD_MATCH" lines are llvmpipe config probing
```

### The withheld `procedural_materials` package

`src/scripts/mixar/modules/paint/procedural_materials/` is gitignored
(`.gitignore:197`) and absent from the published source; 23 files import it.
Measured effect on every launch of the built app (background or windowed):

- `paint/__init__.py` wraps its sub-imports in try/except, so startup logs
  four `[ERROR] Failed to import ...` (`modifier_properties`,
  `layer/layer_properties`, `bake_target_properties`, `root_properties`),
  each ending in `ModuleNotFoundError: No module named
  'mixar.modules.paint.procedural_materials'`, then continues and logs
  `Paint module registered successfully`. The app starts and quits cleanly.
- Anything that imports the paint UI directly fails hard:
  `from mixar.modules.paint.ui import ui` -> `ModuleNotFoundError` (rc=1 with
  `--python-exit-code 1`). So the layered-paint UI, its layer/mask/bake
  properties and the procedural-material library are not functional until the
  package is stubbed or rewritten; the rest of the app is.
- Nothing else failed at import. No network was attempted during the smoke
  runs (backend baked to loopback; timers for the update checker / usage meter
  are scheduled but the process exits before they fire).

## 5. Prod-style build and the login gate

Upstream Mixar's `creator.cc` exits before the window opens unless the OS
keyring already holds `MixarSafeStorage/AccessToken`, except in Dev builds
(`MIXAR_ENV_DEV` short-circuits `show_startup_dialog()`). `lp/fork-patches`
wraps the call in `#ifndef LAMPWAY` (`cmake/mixar_overrides.cmake` defaults
`LAMPWAY=ON`), so only a non-Dev build can show whether the gate is really
gone. Measured on the merged tree:

```bash
MIXAR_ENV=Prod scripts/lampway/build_linux.sh         # own build/Prod, full compile: 41 min 30 s, 5 jobs
```

- Baked markers: `mixar_env_config.h` has `#define MIXAR_ENV_PROD`;
  `5.2/scripts/mixar/config/_build_env.py` has `BUILD_ENVIRONMENT = "Prod"`,
  `DEV_BYPASS_ALLOWED = False`; `mixar.json` `environment: Prod`, backend
  `http://127.0.0.1:8787`.
- Start with **no keyring reachable at all** (`DBUS_SESSION_BUS_ADDRESS` pointed
  at a nonexistent socket, so neither libsecret nor Python `keyring` can find a
  token), windowed under Xvfb, quit from a 20 s timer: **rc=0 in 21 s, no crash
  file, no `desktop-login` URL, no `zenity`, no `xdg-open` in the log**. The
  app reaches the UI; login is left to the Python side, which logs
  `Failed to delete pending refresh attempt: No recommended backend was
  available` (keyring has no backend in that environment — expected) and draws
  a panel referencing an operator `mixie_chat.login` that is not registered
  at draw time (11 lines; defined in `space_mixie_chat/ui/operators/auth_ops.py`,
  drawn by `mcp_bridge/ui/operators/connect.py`; also seen in the merged Dev
  windowed run — the stock tree was never run windowed, so whether the fork
  introduced it is not established).
- The Prod binary still *contains* the gate function (`strings` finds the
  `desktop-login` format and four `zenity` commands); the Dev binary does not
  only because `return true` made the body unreachable. The gate is removed at
  its call site, not deleted — build with `-DLAMPWAY=OFF` to restore it.

Second environment cost: `build/Prod` 3.5 GB; the tree with both
environments is 14 GB plus 2.9 GB git metadata.
