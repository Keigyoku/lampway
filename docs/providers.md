<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Providers

Lampway has no hosted backend. Everything that thinks or generates runs on an account or a machine you own, through the server on `127.0.0.1:8787`. Three families:

1. **Inference providers** run the main agent and the swarm workers.
2. **Generation providers** make images and video (OpenRouter and Higgsfield).
3. **Studios** make 3D (Tripo, Meshy, Hi3D, Hyper3D) and are reached through your sign-in or your API key.

Two rules hold for all of them. Every outbound route is **off until you switch it on** ([privacy](privacy.md)), and every spend either waits for your click or stays under a cap you set ([spend](spend.md)). Credentials are never part of the saved provider settings and never logged: they live in the environment, a key file you name, or a sign-in store under the server's state directory (0600).

Status words: **live** = run end to end against the real service; **built** = implemented and tested against a fake or the documented protocol; **unrun** = no live run exists.

## 1. The main agent and the swarm

Pick the main provider with `LAMPWAY_PROVIDER`, the launcher's `--provider`, or the **Providers** dialog (Studios panel, Lampway tab). A saved choice wins over the environment's default; an environment variable set for this session wins over a saved choice.

| `LAMPWAY_PROVIDER` | What it uses | Route (Privacy) | Status |
|---|---|---|---|
| `mock` | no model: lists the scene; a message starting `py:` runs the rest as a Blender script | none (local) | live |
| `anthropic` | the official SDK with `ANTHROPIC_API_KEY` (model `LAMPWAY_ANTHROPIC_MODEL`, default `claude-sonnet-5-5`) | `claude_plan` (api.anthropic.com; the label says "plan" but this is the API-key path) | built; the Anthropic SDK path has not been run against a live model (the live agent runs used OpenRouter) |
| `openai` | any OpenAI-compatible `chat/completions` endpoint: Ollama, LM Studio, llama.cpp, vLLM, OpenAI. `OPENAI_BASE_URL`, `LAMPWAY_OPENAI_MODEL` (required), optional `OPENAI_API_KEY` | none for a loopback URL; `custom_llm` for any other host | built |
| `openrouter` | OpenRouter, main model `anthropic/claude-sonnet-5.5` by default, `max_tokens` on every request, a session budget ceiling (default $3) | `openrouter` | live |
| `chatgpt_plan` | your ChatGPT Plus or Pro plan through OpenAI's documented "Sign in with ChatGPT" flow; default model `gpt-6.1-sol` | `chatgpt_plan` | built to the documented protocol; the maintainer's build order records a live check on 2026-10-05 that is not reproduced in the committed reports |
| `codex_cli`, `claude_cli` | your own `codex` / `claude` binary, run as you; **off unless `LAMPWAY_LOCAL_CLI=1`** | the binary uses its own network | live once each with tiny prompts |
| `codex_app_server` | `codex app-server` over one persistent child, with Lampway's tools registered as dynamic tools; also behind the local-CLI switch | the binary's own | built |

**Sign in with ChatGPT.** Open `http://127.0.0.1:8787/app/chatgpt`, choose *Continue with ChatGPT*, approve in the browser, then set `LAMPWAY_PROVIDER=chatgpt_plan`. The flow is the documented one (dynamic client registration, PKCE S256, a loopback callback, ID-token validation, the `chatgpt.tokens.use.direct` scope). Tokens stay in `<state>/chatgpt_auth.json`, mode 0600, and are never read from Codex's own files. Image generation is not available on this route.

**Local CLI adapters and the terms.** They start the official binary you are already logged into and never read its credential files. They are for personal use on your own machine. Anthropic's terms say they do not permit third-party developers to offer Claude.ai login in their applications or to route requests through Free, Pro or Max plan credentials on behalf of their users; read them before enabling `claude_cli`, and do not ship it enabled for anyone else. The `anthropic` provider (an API key) is the compliant way to use Claude in a product.

**Swarm.** The agent can start up to 6 parallel workers per swarm, each a headless Blender process with a typed, fenced commit back to your scene. Workers use the main provider's own swarm model, or `claude_cli` or `openrouter` when `LAMPWAY_SWARM_PROVIDER` (or the dialog) says so. Defaults: OpenRouter workers `deepseek/deepseek-v4.1-flash`; ChatGPT workers `gpt-6.1-sol` at effort `low`; Claude CLI workers `claude-sonnet-5-5`. A free OpenRouter stealth model answered 0 of 6 concurrent worker requests, which is why it is not the default. Live: 3 workers on OpenRouter models, all three collections landed. Not run on the Claude CLI adapter. A worker model call is bounded to 300 s.

### OpenRouter

Give the key as `OPENROUTER_API_KEY` or point `LAMPWAY_OPENROUTER_KEY_FILE` (launcher: `--openrouter-key-file`) at a dotenv file or a bare key file. The key is never an argument and never printed, and `redact()` removes it and anything shaped like `sk-or-v1-...` from errors and logs.

- **Budget.** `LAMPWAY_OPENROUTER_BUDGET_USD` (launcher `--budget`, default 3.0) is a session ceiling. Every response's reported `usage.cost` goes on one ledger shared by the main agent, the swarm and the image backend; past the ceiling the next call is refused **before** anything is sent. The launcher starts each session with a fresh spend log (the old one is kept as `.prev`).
- **Per-call click.** Image and video jobs on OpenRouter follow the click rule `above $0.25`: a job whose estimated price is over $0.25 waits for your click (an image is estimated at $0.07 each, so a single image runs without one; a video uses the price estimate computed before submit). The rule is a per-provider spend policy you can change in the Providers dialog, including `off` and `always` ([spend](spend.md)). Chat tokens are not clicked per call: the session budget and `max_tokens` are their limits.
- **Models.** `LAMPWAY_OPENROUTER_MODEL`, `LAMPWAY_OPENROUTER_SWARM_MODEL`, `LAMPWAY_OPENROUTER_IMAGE_MODEL`, `LAMPWAY_OPENROUTER_MAX_TOKENS` (4096).

## 2. Image and video generation

### Images

OpenRouter's images API, with one model **per purpose**, validated against the model's own supported parameters before anything is sent (a parameter the model does not list is refused with what it lists):

| purpose | default model | size or resolution |
|---|---|---|
| `plates` (mesh-paint plates) | `openai/gpt-image-2.5-flare` | 2880x2880 |
| `mask` (material-ID drafts) | `google/gemini-3.1-flash-image` | provider default |
| `concept` | `black-forest-labs/flux-3-image` | 2K |
| `tile` (seamless tiles) | `openai/gpt-image-2.5-flare` | 2048x2048 |

GPT Image takes `size` (about 8.3 MP, at most 3840 per edge; 2880x2880 and 2160x3840 work, 3840x3840 does not); FLUX, Seedream, Gemini and Riverflow take `resolution` plus `aspect_ratio`. Backends for the mesh-paint image step: `tripo` (the Tripo Studio driver), `codex_cli` (your own Codex login; off unless enabled) and `openrouter`. Live: one image, $0.067.

Every image and video job accepts a prompt-library template and variables instead of a raw prompt, stores the rendered prompt, enforces reference order, and is logged with its cost.

### Video

Two providers, routed by the model id (`higgsfield/<id>` goes to Higgsfield):

- **OpenRouter videos** (the 29-model snapshot is the test fixture): catalogue, per-SKU price estimate **before** submit, a per-job cap (`video_max_job_usd`, default $2) and the ledger's remaining budget checked **before** anything is sent, and no resubmit (a second submit is a second charge). Purposes and their defaults: `bulk` HeyGen video 768p 10 s, `loop` Seedance 1.5 Pro 720p first-and-last frame, `motion` Seedance 2.0 Mini with a reference video, `edit` FLUX video edit, `upscale` FLUX video upscale. Live: one 5 s HeyGen clip, $0.05 billed against a $0.10 estimate. Whether the API accepts a video data URL is unverified.
- **Higgsfield** through Lampway's own MCP client and OAuth sign-in (not a connector): sign in at `http://127.0.0.1:8787/app/higgsfield` (or the **Sign in to Higgsfield** button), models from the live catalogue, uploads, `get_cost` first, then the job waits for your click. Motion transfer through Genjutsu and Kling. A transport timeout is its own error and is never resubmitted. Tested against a fake built from the service's specification; **no Higgsfield generation has been run live**, and its tool response shapes are read leniently.

The agent tools `lampway_video_gen` (a dry run unless `dry_run:false`) and `lampway_video_gate` (deterministic loop, upscale, edit and clip gates with ffmpeg only) sit on top.

## 3. Studios

A studio does 3D work: image or text to mesh, texture, PBR, Smart UV, retopology, segmentation. Lampway reaches each one the way it permits, and always through the same flow: **plan** (the settings and the price are read back; nothing is clicked or spent), then **only your click** in the Client confirms, then a server job runs, then the files land in the `Studio` collection. The agent can plan; it can never confirm. Details and the caps are in [spend](spend.md).

| Studio | How | Needs | Status |
|---|---|---|---|
| **Tripo** | Browser drivers against your signed-in Studio tab (23 actions: image, mesh, texture, PBR, Smart UV clone, unwrap, retries, free rerolls, fetch, texture state/refs/restore), plus a REST path (3 actions) | a persistent tool browser with your login (`LAMPWAY_STUDIO_CDP`, default `http://127.0.0.1:9333`), a Python with patchright (`LAMPWAY_PYTHON_BROWSER`), optionally `LAMPWAY_STUDIO_SHELF`; REST: `TRIPO_API_KEY` | built; **unrun** against a live Studio |
| **Meshy** | REST (6 actions: image, multi-image and text to 3D, remesh, UV unwrap, retexture) | `MESHY_API_KEY` | built on a fake transport; **unrun** |
| **Hi3D** (Hitem3D) | REST (3 actions: image to 3D, texture only, split) | `HITEM3D_CLIENT_ID`, `HITEM3D_CLIENT_SECRET` | built on a fake transport; **unrun** |
| **Hyper3D** (Rodin) | REST (3 actions: generate, texture only, Bang split) | `HYPER3D_API_KEY` or `RODIN_API_KEY` | built on a fake transport; **unrun** |
| **Higgsfield** | MCP, see section 2 | your Higgsfield sign-in | built; **unrun** |

Rules every studio action follows (enforced before a driver runs):

- every setting is read back and a mismatch refuses the run; generations use 4 variants at maximum polycount;
- studio actions land on a saved **copy**; the original stays virgin and regenerable (Edit Mesh and the free rerolls are the only things used on an original);
- **texturing comes last**: Smart UV first, then the texture fills its islands; a geometry or UV step after a texture discards the texture;
- a hung job is never re-clicked until you acknowledge it;
- nothing can change a studio's privacy setting (no action exists for it);
- paths are jailed to the project root;
- the REST drivers need the studio guard armed for the confirmed run (`LAMPWAY_STUDIO_ARMED=1`, set by the confirmed run for that one process), read the balance, create **one** task, and never resend a create whose outcome is unknown. A price the provider does not publish is `None`: you must name the most you accept (`accept_up_to_credits`).

Known prices (credits, read back from Tripo Studio): mesh 100, texture 30, PBR 5, Smart UV 20, image free quota. REST list prices are the providers' own tables dated 2026-10-05, not quotes; every request shape is unverified against the live service.

## 4. Other generation and compute providers

| Provider | Use | Where |
|---|---|---|
| **fal** | a queue gateway behind the job receipts (`server/lampway_server/fal.py`); also a compute adapter | [compute](compute.md); fake transport only, the live leg waits for a key |
| **Boat, Modal, RunPod** | rented boxes for headless work (bakes, thumbnails, silhouettes) | [compute](compute.md) |

## 5. The Providers dialog and its files

`GET/PUT /app/provider-settings` backs the dialog: main provider and model and effort, swarm provider and models, image backend, model, size and quality, the four image purposes, the five video purposes, the video per-job cap, and the spend policy per provider. Values are validated, saved to `<state>/provider_prefs.json` (0600) and applied live: the main provider is swapped for new turns, a refusal changes nothing, and there is no credential field.
