# Wave 1: infrastructure (branch lp/wave1 from lp/wave0, 2 commits)

Build path: <workspace>/wt-wave1/build/Prod (hardlinked copy; python synced from wt-wave1).
Tests: server full suite green (rc 0); client lampway_tools 353 passed, 11 skipped (real binary).

| tool | where | evidence |
|---|---|---|
| prompt library | lp/prompts (done) | reports/prompts.md |
| experiment_ledger | server/lampway_server/ledger.py; /app/ledger routes; agent tools lampway_ledger_* | tests/test_ledger.py (9): append-only + supersede, 8 threads + 4 processes lose no row, agent can never choose a spend result (mutant fails), price needs its source, four quantities summed separately, compare |
| prompt run log merged | prompts/runlog.py is a view of the same file <project root>/ledger/runs.jsonl | one file, both kinds, neither confused by the other; prompt dollars count on a piece |
| job_services registry | server/lampway_server/services.py + JobQueue + tool lampway_job_services | tests/test_job_services.py (8): 21 wire keys, catalog from the registry, files result `result_files` GLB with a resolving URL, spend waits for the captain's click (one shot; gate-off mutant fails), unknown key and spend-without-price refused, unbacked listed |
| asset_lineage | client features/lineage.py + api tool + lampway_asset_lineage | test_wave1_lineage.py (4) |
| workflow_graph | client workflow_graph.py + api tool + lampway_workflow_graph | test_wave1_graph.py (7 pure) + test_wave1_graph_tool.py (real tools in the app) |

## Honest limits
- Registry: only the files result shape is added (`result_files`); the client's `result.textures` (PBR) and `result.objects` (scene_gen) shapes are not built yet, and no real backend is registered by this wave (each later tool registers its own). Not driven against the live Client under Xvfb.
- The previous prompt_runs.jsonl under the server state dir is no longer read: the log moved to <project root>/ledger/runs.jsonl. No migration was written (nothing in the repo's tests or the captain's stated work depends on old rows).
- workflow_graph does not append ledger rows yet, and asset_lineage is not yet called by mesh_prep/retopo/etc. nor consumed by asset_acceptance (wiring belongs to the tools that mutate; Wave 2 wires mesh_prep and the pipeline).
- The in-app workflow_graph test was green on its first run (its pure logic was observed RED/mutated in the pure tests).
- Hash of a "mesh" in lineage is vertex coords + loop indices (workflows.mesh_hash); anchor choice is the captain's: the tool never proposes anchors.
