# Wave 5 (+ job receipts, egress consent, compute wrapper, 03 mcp_inventory, 04 agent_files, decisions_model) on branch lp/wave5

Build path: the real native binary `wt-build/build/Prod/bin/mixar` for client tests; the server suite with `venv-tools`. The code-graph tool was NOT used for exploration (the worktrees are not indexed); bash and python scans read the tree.

## Built (each RED first and observed; mutants run on the guarding lines)
| item | where | evidence |
|---|---|---|
| 06 job_receipts | server/jobreceipts.py | mark_pending before the paid call; submission_unknown is never resent; only the user acknowledges or links |
| egress_consent (contract specs/cloud/egress_consent.md) | server/egress.py, Privacy panel | one choke point at the httpx transport plus `guard` for process launches; every route OFF until opted in; content-free log |
| compute wrapper + Blender offload (D8) | server/compute/* | one AXI CLI over Boat, Modal, RunPod and fal adapters on fakes; caps $1/job, $5/day, click above $0.25; verified teardown; reconcile reports orphans and never deletes |
| 08 clip_classify, 13 video_url_ingest, 12 fal_gateway | see wave4 | fake yt-dlp / fake transport |
| 03 mcp_inventory, 04 agent_files_and_skills | server/mcp_inventory, server/agent_files | the Connections panel; generated files never overwrite a user-owned file |
| tools | features/ scene_cleanup, batch_export, camera_shot, procedural_library (12 materials), layered_material, material_bake_export, segment_image; uv_unwrap extended | real-binary tests |
| Studio REST drivers | studios/rest/*, registered in the action registry | Meshy, Hyper3D, Hi3D, Tripo; armed only by LAMPWAY_STUDIO_ARMED=1; unpublished price needs the user's accept_up_to_credits |
| decisions_model | server/decisions_model.py, decisions_goldens.json | live eligible list; private content = ZDR list + `{"zdr": true, "data_collection": "deny"}`, never `:free`, refused with nothing sent when none is eligible; eval harness scores each candidate against 7 goldens |

## Findings
- The TOOL_FUNCS door defect: five api tools had no server Def; added, and `test_wave5_tool_door.py` now pins every api tool to a Def.
- A child panel registered before its parent LAMPWAY_PT_main failed to register; the `classes` order is fixed and a test asserts no "Error registering class".
- Boat CLI facts measured live: `exec <id> --json --no-update --timeout N "<one shell string>"`; `--detach` cannot combine with `--timeout`; `usage` 404s after a no-snapshot box is erased, so the meter is read before teardown. Spend ledger: docs/reports/compute-spend.md. Every sandbox was deleted and proved by `boat list`.
- herdr isolation and SIGKILL survival: see wave3.
- PII incident: unpushed commits carried the owner's real email as author; rewritten with a reset author, all later commits use the noreply identity. The gate now also caught two test literals shaped as userinfo URLs (split literals).
- A flaky cockpit test (see wave3).

## Not built / honest gaps
- Endpoint adapters (RunPod, Modal) and their tests were written in one pass (no separate RED).
- Surviving or equivalent mutants: the shared-data refusal double guard; approval plan_id redundant with price equality; the CLI backend guard redundant with the runner.
- The "auditor's recommended 12" procedural materials are not written in any spec; I chose the 12 (captain to confirm).
- Not built: the model_compare windowed viewer, an RTMW detector, the UE editor export leg, mask invert in layered_material, a Blender panel for agent_files, a Blender UI for the Studio REST drivers, engine_import_check consuming engine_project.
- decisions_model: the only specs mentioning it are one line each in anim_multiview_fit.md and WORKFLOWS.md, so the contract is mine (a closed-choice judge); the ZDR response shape is [UNVERIFIED], and the goldens are seven authored cases, not a measured benchmark. The live leg is `needs_key`.
- All provider request shapes (fal, Meshy, Hyper3D, Hi3D, Tripo, Modal, RunPod) are [UNVERIFIED]; live legs are `needs_key`. Terms of Boat/Modal/RunPod (decision D9) are unread: every route policy is "unknown". OpenCode config layout and Linux managed-policy paths are unverified.

## Test counts at the head
server: 900 passed, 5 skipped. client tests/lampway_tools (real binary): 753 passed, 46 skipped. Pre-publish gate on a `git archive` export plus origin/lp/wave5..HEAD: 0 findings.
