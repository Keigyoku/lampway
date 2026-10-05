# Lampway features pass (branch lp/features, 23 commits over lp/harden)

Built on proven algorithmic code with a model/studio slot behind the same tool interface. Every feature is an `api.tool` returning
`ok` plus data, mirrored as a server agent tool (`lampway_*`). `engine="studio:<name>"` never clicks: it returns
`{ok: False, needs_approval, studio, action, price, how}`.

| Feature | Built on (proven) | Slot | Tests |
|---|---|---|---|
| Retopology | Blender QuadriFlow, voxel-remesh fallback, measured report | studio:tripo (answer only) | test_feature_retopo |
| UV unwrap | angle seams, Blender solvers and packer, islands/overlap/texel-density report | studio:tripo | test_feature_uv |
| Segmentation | shells, sharp-edge region growing, UV islands, small-region merge | studio:tripo | test_feature_segment |
| Auto-rig, bind, pose test | landmark skeleton (UE names), heat weights + proximity fill, Data Transfer, edge-stretch measurement | studio:tripo | test_feature_rig |
| Image to 3D / multi-view | visual-hull space carving, rounded extrusion, relief | studio:tripo (Smart Mesh, 4 views) | test_feature_image3d |
| Splats | 3DGS PLY decode, point object + geometry-nodes view | none | test_feature_splat |
| Video | Workbench/EEVEE turntable and camera-path frames, FFmpeg H.264 | none | test_feature_video |
| Texture Gen, AI Render, texture repair | UV-texel projection with occlusion ray test, patch/feather repair | studio:tripo (texture+PBR); image slot = OpenRouter image_gen | test_feature_texture, test_feature_jobs_client |
| Semantic asset search | BM25 text + colour-histogram image + hybrid; 7 endpoints | embedding model could slot into the index | server/tests/test_asset_search |
| MCP eligibility | JSON-RPC server, tools mirrored | n/a | server/tests/test_mcp |
| Dictation | RMS energy gate, PCM framing, WAV wrap, duration cap; WS /api/v1/dictation/ws | OpenRouter audio-input model (google/gemini-3.8-flash) on the spend ledger | server/tests/test_dictation |
| MatGen auto-apply | headless-safe landing on named objects | n/a | test_matgen_apply |
| Sandbox RNA-path residual | `guard_file_attr` gates datablock file methods (bpy.data.images.load, reload) | n/a | test_sandbox_paths_in_app |
| Wiki workflows | mesh_prep, asset_acceptance, rig_armor composed from the above | n/a | test_feature_workflows |
| UI | Features panel + `lampway.feature_run` | n/a | test_ui |

Also done: the ChatGPT log leak (`logredact.py`, record-factory redaction of code/state/client_id/token query values incl. uvicorn's
access log; callback and provider error bodies capped and redacted), and the resource audit (`docs/lampway/resource-audit.md`, NOTICE).

## Test counts (run at head 5142b9d5)
- server: 307 passed, 3 skipped (pytest in the host venv).
- client tools (real Prod binary, host): 311 passed, 11 skipped. The skips were not investigated one by one this pass; none are the new tests.

## Live evidence
- Dictation: espeak speech through the real OpenRouter audio model, returned 'Make the ramp rough and add a bevel' (espeak's own
  "lamp brass" is mangled; the path works, the accuracy is the TTS source's), cost $0.000483 on a scratch ledger. Total OpenRouter spend this pass: under $0.001 of the $15 cap.
- Feature tests run inside the real binary on synthetic shapes, not on a production asset.
- ChatGPT live test and the server-with-bridge live walk were not re-run in this half of the pass.

## Still open (named, not hidden)
- Studio slot beyond the refusal: only Tripo drivers exist on the shelf; the meshy and hi3d driver folders are EMPTY. Any credit-spending click is the coordinator's approval first; none was made. The Tripo Texture dry run refuses because the selected model has no Smart UV step yet.
- The splat geometry-nodes view is not render-verified.
- AutoRemesher (MIT) is a candidate retopo engine; it needs a native build approval.
- Panel is one generic operator, not a per-feature UI.
- Search engines refused automated queries; research went to the projects directly.
