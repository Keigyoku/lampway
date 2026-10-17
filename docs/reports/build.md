# Lampway Linux build pipeline — implementer report (vellum-implementer, 2026-10-04/05)

Worktree: `<workspace>/wt-build` (branch `lp/build`). Box: distrobox `lampway-build` (Ubuntu 24.04, 16 cores, 30 GB).
Every log cited is under `<workspace>/wt-build/build/logs/` (gitignored).

## Outcome in one paragraph

The forked client builds and runs on this machine from one idempotent script, `scripts/lampway/build_linux.sh`, with
`BUILD-LAMPWAY.md` beside it. The stock `lp/build` tree compiled clean in **41 min 17 s** (Dev, `MIXAR_CUDA=0`, 5 jobs);
a no-change re-run takes 1 min 4 s. `origin/lp/fork-patches` merged without conflicts and rebuilt incrementally in
10 min 18 s. Smoke: `--version` and `import mixar` pass; the layered-paint UI cannot import because
`procedural_materials` is withheld (details below). A windowed start under Xvfb succeeds after a defect I introduced
and then fixed (upstream's LFS payload was not pulled; the embedded `startup.blend` was a pointer and the first window
segfaulted). The Prod-style build and its no-keyring start test are in the last section.

## Commits on lp/build (author Keigyoku, no trailers)

| sha | what |
|---|---|
| `d181de36` | `scripts/lampway/build_linux.sh` + `tests/lampway/test_build_linux.py` — testable `--plan` surface, `.env` guard, deps check, shallow pinned submodules, disk floor |
| `6649a3f9` | default service URLs to `https://lampway.invalid` (superseded by `4805a3ca`, see "Decisions") |
| `764cb567` | GCC >= 14 gate, `gcc-14`/`g++-14` selection, stale-compiler cache drop |
| `0c7f6a21` | merge `origin/lp/fork-patches` (tip `c7b0190f`) into `lp/build` — clean |
| `4805a3ca` | `git lfs pull` in `upstream/` with upstream's own `startup.blend` sentinel; service URLs left to the tree |
| `7bfdb27a` | `BUILD-LAMPWAY.md`, this report's companion |

Pushed: `git push origin lp/build` -> `origin/lp/build` = `7bfdb27afd0e5ddc44eeaac9b7718cdeecf27329` (= local HEAD; new
branch on github.com/Keigyoku/lampway, no auth problem). Tests at HEAD: `pytest tests/lampway` -> 56 passed (14 mine,
42 from lp/fork-patches). Nothing merged anywhere else; `lp/fork-patches` and `lp/server` untouched.

## Steps, in order, with evidence

1. **Read**: README (build section), CLAUDE.md, Makefile, `scripts/unix/{build,settings,overlay,init}.sh`,
   `.env.example`, `cmake/mixar_overrides.cmake`, `audit/report.md`, upstream's `make_update.py` / `make_utils.py` /
   `install_linux_packages.py` once the submodule existed.
2. **Pins**: `HEAD:upstream` = `fbe6228777e7d9afefcd61a413844e790ae75db7` = Blender tag `v5.2.0`; upstream's
   `HEAD:lib/linux_x64` = `30d9f881c4b62c52323fd11637eeea56d460e35c` (= lib-linux_x64 tag v5.2.0).
   Added 2026-10-07, pinned the same way (a gitlink at a release tag, fetched shallow at the committed pin):
   - `HEAD:third_party/hermes-agent` = `f97608f178d1ffeca59860195ab7da295f7c8e5f` = Hermes Agent tag `v2026.9.24`, built by
     `scripts/lampway/engine_env.py`;
   - `HEAD:third_party/herdr` = `7b116c05bfda646af39d2524c54e70c751f57ee8` = herdr tag `v0.9.3`, built by
     `scripts/lampway/herdr_env.py` (Rust 1.96.1 from herdr's `rust-toolchain.toml`, Zig 0.16.0).
3. **TDD on the script** (pytest 9.1.1 on the host; `tests/lampway/test_build_linux.py`, 14 tests, all observed RED
   first — log paths in the per-commit sections of my transcript; final run `14 passed in 0.37s`). The tests use a
   throwaway superproject with a gitlink, so they never read the real `.env`. Two real defects the RED/GREEN loop
   caught before any build: `git -C upstream rev-parse HEAD` on an *empty* submodule dir answers with the
   superproject's HEAD (fixed by a `--show-toplevel` identity check); and Blender 5.2's GCC >= 14 floor (first
   configure died 3 000 lines into the log on Ubuntu's gcc 13.3).
4. **Box**: fresh `lampway-build`. First entry spent ~40 min in distrobox's base package install under a host load of
   ~30. Installed (log `apt-install.log`, `apt-gcc14.log`, `apt-runtime.log`): upstream's mandatory 5.2 list +
   `gcc-14 g++-14 git-lfs ninja-build libsecret-1-dev libcurl4-openssl-dev libssl-dev zenity` + runtime `libsm6 libice6`
   (the binary failed to load without them: `ldd` showed exactly those two unresolved).
   **Host quirk**: `distrobox enter lampway-build` fails with `unable to find user <name>: no matching entries in passwd
   file` whenever the previous enter session has ended (reproduced 4 times; `podman stop`+`start` clears it once;
   a holder session did not help). `podman exec --user 1000:1000 -w <dir> lampway-build ...` works every time and is
   what every build/smoke below used. Documented in BUILD-LAMPWAY.md §2.
5. **Submodules**: `git submodule update --init --depth 1 upstream` succeeded directly at the SHA (Gitea served it).
   `lib/linux_x64`: `update=checkout` set, shallow fetch with `GIT_LFS_SKIP_SMUDGE=1`, then `git lfs pull` — 785 LFS
   files, 2.0 GB, 1 min 48 s total (`sync-only.log`). Verified `python/bin/python3.13` is a 40 MB ELF.
6. **Clean Dev build** (`build-run.log`, `build-Dev-20261004T214636.log`): `BUILD_CORES=5` (chosen from 11 GB free RAM
   at launch; other agents' builds held the rest), gcc-14, Ninja, 8 472 steps, **41 min 17 s**, exit 0, no OOM, no
   compile errors. `check_python_runtime.py` passed; embedded pip installed the requirements. Binary:
   `<workspace>/wt-build/build/Dev/bin/mixar` (248 MB).
7. **Idempotency** (`build-rerun-noop.log`): second run, nothing changed, **1 min 4 s**, exit 0 (overlay rsync,
   reconfigure, relink of the two executables, install, pip).
8. **Smoke on the stock tree** (`smoke-dev-stock.log`, `smoke-dev-stock-exitcodes.log`): see table below.
9. **Merge** `origin/lp/fork-patches` (`c7b0190f`, 11 commits, 93 files, +1 613/-20 653) into `lp/build`: clean,
   `0c7f6a21`. Incremental rebuild 580 steps, **10 min 18 s** (`build-incremental-merge.log`); CMake reports
   `Lampway: native login gate OFF (Python SSO owns login)`. `pytest tests/lampway` (theirs + mine): 54 passed after I
   removed the one line of mine their host scanner flagged (my comment named `mixar.app`).
10. **Windowed start, first attempt** (`start-dev-merged-xvfb.*.log`): segfault after 7 s. Cause found in the log:
    `WARNING Unrecognized file format` for every bundled asset `.blend`, and `upstream/release/datafiles/startup.blend`
    was 131 bytes — an LFS pointer. `blender.git` tracks 6 659 files in LFS; my sync only pulled LFS inside
    `lib/linux_x64`. Fix in `4805a3ca` (stage 2 = `make_update.py`'s `blender_lfs_update`); `--sync-only` then took
    2 min 54 s (`sync-upstream-lfs.log`), rebuild 1 min 40 s (`build-dev-lfs.log`).
11. **Windowed start, second attempt** (`start-dev-lfs-xvfb.*.log`): `LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a -s "-screen 0
    1280x800x24" mixar --python-expr "<quit after 20 s timer>"` -> **rc=0 in 23 s, "Blender quit", no crash file**.
    Six non-fatal `EGL Error (0x3009): EGL_BAD_MATCH` lines (llvmpipe config probing).

### Smoke results (Dev, merged tree, after the LFS fix — `smoke-dev-lfs.log`)

| command | result |
|---|---|
| `mixar --background --version` | `Blender 4.2.2 (hash fbe6228777e7 built 2026-10-05 04:57:32)`, rc=0. "4.2.2" is Mixar's `VERSION` file, the hash is Blender v5.2.0 |
| `--background --python-exit-code 1 --python-expr "import mixar; print('addon ok')"` | `addon ok`, rc=0 |
| `... "import mixar.modules.paint"` | `paint pkg ok`, rc=0 |
| `... "from mixar.modules.paint.ui import ui"` | `ModuleNotFoundError: No module named 'mixar.modules.paint.procedural_materials'`, rc=1 |
| `... "import mixar.modules.paint.procedural_materials"` | same `ModuleNotFoundError`, rc=1 |
| `... "from mixar.config import brand; ...get_server_url()"` | `brand: Lampway | backend: http://127.0.0.1:8787`, rc=0 |
| bundled `5.2/config/mixar.json` | `environment: Dev`, `backend_url`/`frontend_url`: `http://127.0.0.1:8787` |

The add-on's import path is simply `import mixar`: `scripts/startup/bootstrap/__init__.py` inserts `<install>/5.2/scripts`
into `sys.path` at startup and `mixar/__init__.py` imports nothing itself.

### The `procedural_materials` impact, measured

- Startup (every launch, background or windowed): four `[ERROR] Failed to import ...` from `paint/__init__.py`'s guarded
  imports — `modifier_properties`, `layer/layer_properties`, `bake_target_properties`, `root_properties` — each a
  `ModuleNotFoundError` for `mixar.modules.paint.procedural_materials` (four tracebacks per launch). Startup then
  continues: `Paint module registered successfully`; the app quits cleanly. So the app runs, degraded.
- Direct import of the paint UI (`paint.ui.ui`, and transitively the layer/mask/bake property modules and the
  procedural-material library) fails hard. The layered painting feature is not usable until the package is stubbed or
  rewritten. 23 files import it (`grep -rl procedural_materials src/scripts/mixar`).
- Nothing else failed at import in any smoke run; no other `ModuleNotFoundError` appeared.

## Decisions and deviations the brief did not settle

- **Service URLs.** The stock tree bakes `https://api.mixar.app`; bootstrap's `register()` starts the API executor at every
  launch. To honour "never contact a Mixar service" during the stock-tree smoke I first defaulted both URLs to
  `https://lampway.invalid` (`6649a3f9`). After the merge the tree's own default is loopback (`brand.py`,
  `settings.sh`), so the script now leaves unset URLs to the tree (`4805a3ca`) — a build script that silently baked a
  host the fork did not choose would have surprised the server implementer. The stock-tree Dev smoke ran with the
  `.invalid` host baked (confirmed in its `mixar.json`); the merged-tree runs bake `http://127.0.0.1:8787`. No run ever
  reached a Mixar host: no DNS/connection error for any `mixar.app` host appears in any log, and the process exits
  before the scheduled update-checker / usage-meter timers fire.
- **`CMAKE_GENERATOR=Ninja`** when ninja exists (the repo leaves the generator default; Ninja is what made the 1-minute
  no-op re-run possible). Honours an existing cache.
- **`BUILD_CORES`**: the script itself defers to `settings.sh` (nproc); I wrapped each launch with `free GB / 2` clamped to
  4..16 because the box's 30 GB were mostly held by other agents' builds (3-11 GB free during the run). Documented, not
  baked into the script.
- **Two `tests/lampway` files share a directory** with the fork-patches tests; no name clash (`test_build_linux.py` vs
  `test_lampway_*.py`).
- The LFS stage has no unit test (needs a real LFS server); its `--plan` state reader does (`pointer` / `materialised`).
  The live proof is step 10-11 above.

## Blockers / open points

- Host-side `distrobox enter` instability (step 4). Not fixed; worked around with `podman exec --user 1000:1000`.
- `procedural_materials` is withheld upstream; see the measured impact. Needs a stub or rewrite (not in this task).
- Six `EGL_BAD_MATCH` warnings under Xvfb/llvmpipe; non-fatal. Not investigated further.
- `SyntaxWarning: invalid escape sequence` in four paint modules (`lib_operations.py:72`, `get_channels.py:126,140`,
  `create_nodes.py:398`) at first import — upstream Mixar code, cosmetic.

## Prod-style build and the keyring question (deliverable 3)

Why a Prod build: upstream's gate is `#ifdef MIXAR_ENV_DEV -> return true`, so a Dev build never exercises it;
`lp/fork-patches` wraps the *call* in `creator.cc` with `#ifndef LAMPWAY` (`cmake/mixar_overrides.cmake`: `LAMPWAY ON`).

- `MIXAR_ENV=Prod scripts/lampway/build_linux.sh` -> own `build/Prod`, full compile **41 min 30 s** (5 jobs), exit 0
  (`build-prod.log`, `build-Prod-20261004T225859.log`). CMake: `Lampway: native login gate OFF (Python SSO owns login)`.
- Baked (`smoke-prod.log`): `mixar_env_config.h` `#define MIXAR_ENV_PROD`, `MIXAR_BASE_URL "http://127.0.0.1:8787"`;
  `_build_env.py` `BUILD_ENVIRONMENT="Prod"`, `DEV_BYPASS_ALLOWED=False`; `mixar.json` `environment: Prod`.
  `--version` rc=0; `import mixar` rc=0 (same four `procedural_materials` startup errors).
- **Start without a keyring token, Prod-style** (`start-prod-nokeyring-xvfb.log`, `.app.log`): run with
  `DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent/...` so no SecretService is reachable (libsecret and Python
  `keyring` cannot return a token by construction — I did not touch the user's real keyring), windowed under Xvfb
  with llvmpipe, quit by a 20 s `bpy.app.timers` callback: **rc=0 after 21 s, "Blender quit", no crash file**. The app
  log has no `desktop-login` URL, no `zenity`, no `xdg-open` — i.e. the browser SSO gate did not run. `xdg-open` and
  `zenity` were both present in the box, so their absence from the log is meaningful.
  Observed in the same log: `[ERROR] Failed to delete pending refresh attempt: No recommended backend was available`
  (Python keyring with no backend — expected given the disabled bus) and 11x `UILayout.operator(): unknown operator
  'mixie_chat.login'` — the operator exists (`space_mixie_chat/ui/operators/auth_ops.py:479`) and is drawn by
  `mcp_bridge/ui/operators/connect.py:78` before it is registered (deferred UI loading is the likely reason). The same
  lines appear in the merged Dev windowed run (`start-dev-lfs-xvfb.app.log`, 6x). The stock tree was never run
  windowed (its only windowed attempt crashed on the LFS pointer), so I cannot say whether `lp/fork-patches`
  introduced it; the fork did touch `space_mixie_chat/ui/login_panel.py` and `topbar.py`. Cosmetic, not a blocker.
- **Caveat on the string probe**: `strings build/Prod/bin/mixar` still contains the gate body (`desktop-login` x1,
  `zenity` x4, `MixarSafeStorage` x3). In the Dev binary they are absent only because `return true` made the body
  unreachable and GCC dropped it. So the fork removes the gate at its call site, not the function; the behavioural
  proof is the live start above, and the source pin is the fork's `tests/lampway/test_lampway_cpp_gate.py`.
- Answer to the brief's question: **yes — after merging `lp/fork-patches`, a Prod-style build starts to the UI with no
  keyring token and never opens the SSO browser flow.**

## Final sizes / disk

`build/Dev` 3.4 GB, `build/Prod` 3.5 GB, `source/` 3.5 GB, `upstream/` 3.4 GB (incl. `lib/linux_x64` 2.3 GB), logs
104 MB -> worktree 14 GB; git metadata for the two submodules 2.9 GB under `app/.git/worktrees/wt-build/modules/`.
Total attributable to this task ~17 GB (budget 45). Host free space: 234 GB at start -> 159 GB at the end; the
difference beyond ~17 GB is other work sharing the disk. The floor of 100 GB was never approached.
