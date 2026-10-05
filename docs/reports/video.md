# Video generation and Higgsfield in Lampway (branch lp/video, from lp/studios b691b0b1)

Worktree `<workspace>/wt-video`; its own build copy at **`wt-video/build/Prod`** (python synced at the head). Nothing of the user's session
(wt-harden, 8787, 19881, ~/.local/share/lampway) was touched. Tests at the head: **server 414 passed, 3 skipped; client tools (real binary) 327 passed, 11 skipped**.

## 1. Video on OpenRouter (`server/lampway_server/videogen.py`, `videojobs.py`)
- **Catalogue**: `GET /api/v1/videos/models` (the 29-model snapshot is the test fixture). Each model's supported_resolutions / aspect_ratios / durations / frame_images /
  generate_audio / upscale_factor / creativity fill the client catalogue rows (`parameters` with enums + defaults from the per-purpose settings) and validate every request;
  a value the model does not list is refused with what it lists.
- **Estimate before submit** from pricing_skus: HeyGen per-second per-resolution (+ the reference rate with references), Seedance video tokens
  (tokens = W x H x 24 x s / 1024, SKU chosen by audio / video-input case; 854x480 from the model's supported_sizes), per-second cents with the per-generation minimum, the
  upscaler per megapixel-second of the OUTPUT (precise 7.5c / creative 10.5c), `text_to_video_*` families. A SKU family that fits nothing = price unknown = refused unless the caller accepts.
- **Budget**: per-job cap (setting `video_max_job_usd`, default $2) and the ledger's remaining budget, both BEFORE anything is sent; a job is never re-submitted
  (a second submit is a second charge); the actual `usage.cost` goes on the ledger (label `video`) and is returned beside the estimate and the token count.
- **Inputs**: `frame_images` (first_frame / last_frame; first_last_frame with ONE image = a loop), `input_references` with images and video (`video_url`, as in the OpenAPI schema).
  Video goes as a data URL: the docs show https URLs only, so whether the API accepts data URLs for video is **unverified** (images are known to work this way).
- **Video Upscale**: `black-forest-labs/flux-video-upscale` as the `video_upscale` service, source clip staged, probed with ffprobe (duration, size) for the price.
- **Client surface**: the services + `input_spec` as `moodboard/core/video_generation_catalog.py` expects; `POST /api/v1/uploads/<image|video>` -> `data{s3_key, duration_seconds}`
  (what `common/job_queue/core/generic_jobs.py` StreamingVideoJob posts); payload keys `reference_image_s3_keys` / `reference_video_s3_keys` / `video_s3_key`;
  result as `result_files[{type: "VIDEO", url}]` (`job_queue/core/queue_download.py` prefers VIDEO) and the file is also saved under `<project root>/video/<job>.mp4`.
  With no OpenRouter key and no Higgsfield sign-in the capability is not advertised (the client's own kill switch).
- **Agent tool** `lampway_video_gen` (dry run by default: validated params + price; `dry_run:false` on an OpenRouter model runs within the cap and saves an .mp4) and `lampway_video_models`.
- **Providers dialog / settings**: per-purpose video models: bulk = heygen/heygen-video-1 768p 10 s; loop = seedance-1-5-pro 720p first_last_frame; motion = seedance-2.0-mini with a
  reference video; plus the per-job cap. Same validated, saved, live-applied settings as the image purposes.

### Live check (allowed, own in-process server, own spend log, cap $5)
HeyGen 480p, 5 s, 16:9 through the job queue: **succeeded in 15 s**, an 832x480 h264+aac clip (137 KB) saved under the project root. **Estimate $0.10, actual billed $0.05**: the
HeyGen estimate formula (SKU $/s x seconds) is 2x the bill at 480p/5 s. Estimates stay conservative; I did not change the formula from one sample. Seedance's token formula was
NOT checked (no Seedance job was run; the record of estimate vs actual is on every result so the first real Seedance job answers it). Total spend: $0.05.

## 2. Higgsfield in the Client (`higgsfield_auth.py`, `higgsfield_mcp.py`, `higgsfield.py`, `higgsfield_diff.py`)
- **Own MCP client with its own sign-in** (not the claude.ai connector). OAuth per the MCP spec through Clerk: discovery from the protected-resource metadata, dynamic client
  registration as "Lampway" (once per redirect URI), authorization code + S256 PKCE on this server's loopback port (`/auth/higgsfield/callback`), tokens 0600 in the state dir,
  **one `HiggsfieldAuth` per server** with a serialised refresh (six concurrent callers share one refresh; the rotated token is saved), a revoked session says "sign in again",
  no code / state / verifier / token in any log line (tested through the log record factory). Pages: `/app/higgsfield` (POST + loopback Origin to start, like /app/chatgpt), `/status`, `/signout`.
- **MCP client**: streamable HTTP JSON-RPC (initialize + `Mcp-Session-Id`, `tools/list` cached, `tools/call`), JSON or SSE answers, a 401 refreshes once and retries, a lost session re-initialises once,
  tool errors raise with the server's words, a **transport timeout is its own error** ("NOT resubmitted").
- **Provider of `video_gen` and `image_gen`** next to OpenRouter, routed by the model slug `higgsfield/<id>`: the catalogue from `models_explore` (durations, resolutions, aspect ratios,
  media roles), uploads `media_upload` -> PUT -> `media_confirm` (medias take ids), `generate_video` / `generate_image` in the roles each model takes (start_image/end_image for loops,
  image/video/audio references), `jobs_wait` (<= 15 s each, bounded; a timeout while waiting polls the same ids), the result downloaded into the project and delivered as result_files.
- **Motion transfer** as `video_gen` modes: Genjutsu `hf_mult_motion_control` (character image + driving video to the model's reference roles) and Kling 3.0 `motion_control`
  (`{image_id, motion_video_id, resolution, scene_control}`), selectable in the client's Video Gen dropdown.
- **Spend gate** (the SAME one as the Studios): a Higgsfield job runs `get_cost` first, then **waits PENDING** ("N credits on Higgsfield. Confirm it in the Studios panel") on an approval in the shared
  store; only the user's click (price must equal the one shown; one-shot; expires) starts it, a reject cancels it, and nothing but `get_cost` is called before. The credits go into the job record
  (`result.credits`). The agent tool can only submit-and-wait (`needs_approval`), never confirm; `lampway.studio_confirm` / `studio_answer` refuse while any script runs (agent, worker, bridge).
  **`unlim_choice`** comes back as a SECOND approval ("Higgsfield asks: ...") needing the user's Yes/No (an answer without `answer` is refused); `use_unlim` is never sent unless he answers.
  **A submit timeout fails the job** with "NOT resubmitted" (one attempt only); jobs we already have ids for are polled again, never resubmitted.
- **Client UI** (Studios panel): Sign in to Higgsfield button (opens `/app/higgsfield`), question cards with Yes / No, credit prices shown as credits (fractional prices are sent exactly, rounded to 2 dp).

### Tests with a fake MCP built from the SPEC (`tests/fake_higgsfield.py`)
Clerk register/authorize/token with PKCE verification and refresh-token rotation; the MCP tools. Mutation-checked: the gate (6 tests fail without it), the unlim auto-answer, plus the videogen cap,
unknown-price refusal and the ledger record. **The tool RESPONSE shapes (credits key, jobs list, result URLs, media_upload body, models_explore rows) are assumptions from the SPEC's parameter lists;
they are read leniently, and `media_upload` adapts to the tool's own inputSchema (files[] or filename).**

### Not done / what you run
- **Live diff after the user signs in** (read-only; calls only tools/list, balance, models_explore): `LAMPWAY_STATE_DIR=<the server's state dir> python -m lampway_server.higgsfield_diff`
  (run with the server venv, from `wt-video/server`). It prints the tools present/missing, each tool's inputSchema vs the arguments we send, the balance and how many models parsed. I could not run it: no sign-in was available to me.
- No Higgsfield generation was run by me. The first Seedance clip: sign in (`/app/higgsfield`), submit from the Video Gen surface (or the agent tool), read the credits on the card in the Studios panel, confirm, answer unlim if asked.
- Higgsfield image_gen results go through the same gate; `gpt_image_2_5` is in the catalogue once signed in.
- Not built: audio references from the client, `generate_video_batch`, `show_generation_by_ids` recovery of a job whose submit timed out (the job fails and says to check Higgsfield).

## 3. Run it
Server env as before; set `LAMPWAY_PROJECT_ROOT` (videos and uploads live under it). Launch from `wt-video` (`scripts/lampway/lampway --env Prod ...`). The Providers dialog has the video rows; `video_max_job_usd` is the cap.
