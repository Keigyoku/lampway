<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Issue2 RED and regression evidence reconciliation

Update (PR #1 finish, 2026-10-11): every row of the index below (33 rows) now has a current regression control on its maintained real-shape covering test, the 17 formerly unresolved rows by actual pre-fix reversions (section at the end). AC02's historical clause, a RED run recorded before each fix, stays open: it cannot be reconstructed where test and code landed in the same commit (`afcbe66d`, `df50ecd5`, `47fc25df`). The private reconciliation covers all65 literal criteria and34 groups, preserving original receipt identities, source hashes, explicit input shapes and exact remaining evidence. Git history identifies when the maintained cases were committed; commit membership and later source reversion do not establish that a RED run preceded implementation. Aggregate/live statements are not assigned invented standalone RED obligations.

The earlier27 controls comprise14 source reversions and13 geometry controls; two geometry controls plant generated responses. Their evidence is retained with those distinctions. Retained owner REDs with incomplete ordering metadata remain RED evidence rather than becoming a universal historical chronology claim.

Two new disposable controls strengthen maintained regression detection without changing tracked tests or production code:

| Fix | Actual production reversion | Same maintained assertion and restored result |
|---|---|---|
| Numerical frames | Replace the polar factor U@Vt with the source matrix; strict validators stay active. | Float32 precision case1fails; restored8passes. Complete342-parent graph with258synthetic oblique helpers1fails; restored1passes. Authored-matrix preservation and strict shear/reflection assertions remain. |
| Ledger classification | Replace the production unreconciled-row default UNVERIFIED with BUILT. | Maintained identity/no-sweep-upgrade case1fails; restored12passes. Only synthetic fixtures are used. |

The numerical native control uses the existing maintained test with a private runner substitution: a disposable factory-startup child, current source overlay, isolated test home/project/temp directories and no installed-script synchronization. It adjusts only temporary-root setup; assertions remain unchanged. Exact function, test and native-binary hashes and RED/GREEN XML are retained privately. These are current controls after publication, not reconstructed historical RED-first runs.

The per-fix index below distinguishes currently indexed source/response controls from retained REDs whose execution order remains unresolved. Every row still needs its original pre-fix source/test identity, failing command/output and execution-order provenance to close the historical clause. Actual original-asset acceptance and full test_all remain AC04/AC05 evidence, independently.

| Fix group | Maintained covering selection | Indexed evidence |
|---|---|---|
| G1 | [test_axi.py](../../tests/lampway_tools/test_axi.py) | Current regression control |
| G2 | [test_canon_fit_body_package.py](../../tests/lampway_tools/test_canon_fit_body_package.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| G4/G5 | [test_canon_normalize_rigged.py](../../tests/lampway_tools/test_canon_normalize_rigged.py) | Current regression control |
| G7 | [test_wave6_glb_optimize.py](../../tests/lampway_tools/test_wave6_glb_optimize.py) | Current regression control |
| G3 | [test_rig_conform.py](../../tests/lampway_tools/test_rig_conform.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| G6 | [test_wave3_export_checks.py](../../tests/lampway_tools/test_wave3_export_checks.py) | Current regression control |
| G8 | [test_wave6_lod_chain.py](../../tests/lampway_tools/test_wave6_lod_chain.py) | Current regression control |
| G10 | [test_wave3_weights.py](../../tests/lampway_tools/test_wave3_weights.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| G11 | [test_feature_workflows.py](../../tests/lampway_tools/test_feature_workflows.py) | Current regression control |
| G14 | [test_auth.py](../../server/tests/test_auth.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| G15 | [test_lampway_tool_aliases.py](../../tests/mcp/test_lampway_tool_aliases.py) | Current regression control |
| G16 | [test_tool_schema_ratchet.py](../../server/tests/test_tool_schema_ratchet.py) | Current regression control |
| G17 | [test_issue2_gui.py](../../tests/lampway_tools/test_issue2_gui.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| G9 | [test_feature_retopo.py](../../tests/lampway_tools/test_feature_retopo.py) | Current regression control |
| G12 | [test_agent_files.py](../../server/tests/test_agent_files.py) | Current regression control |
| G13 | [test_agent_files.py](../../server/tests/test_agent_files.py) | Current regression control |
| G18 | [test_tool_availability.py](../../tests/mcp/test_tool_availability.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| G19/F13 | [test_refusal_templates.py](../../server/tests/test_refusal_templates.py) | Current regression control |
| G20 | [test_wave4_multiview.py](../../tests/lampway_tools/test_wave4_multiview.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| G21 | [test_library_store.py](../../server/tests/test_library_store.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| G22 | [test_asset_search.py](../../server/tests/test_asset_search.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| F23 | [test_issue2_gui.py](../../tests/lampway_tools/test_issue2_gui.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| F8 | [test_feature_workflows.py](../../tests/lampway_tools/test_feature_workflows.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| F17 | [test_ui_geometry.py](../../tests/mcp/test_ui_geometry.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| F21 | [test_feature_workflows.py](../../tests/lampway_tools/test_feature_workflows.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| F6 envelope | [test_mcp_operation_lease.py](../../server/tests/test_mcp_operation_lease.py) | Current regression control |
| F20 | [test_agent_turn.py](../../server/tests/test_agent_turn.py) | Current regression control |
| F25 | [test_lazy_turn_checkpoint.py](../../tests/checkpoints/test_lazy_turn_checkpoint.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| F10 | [test_feature_uv.py](../../tests/lampway_tools/test_feature_uv.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| browser/routes | [test_sso_desktop_login_url.py](../../tests/network/test_sso_desktop_login_url.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |
| facing parity | [test_wave2_piece_ratios.py](../../tests/lampway_tools/test_wave2_piece_ratios.py) | Current regression control |
| ledger | [test_status_ledger.py](../../tests/test_status_ledger.py) | Current regression control |
| canon decisions | [test_canon_decision_measure.py](../../tests/lampway_tools/test_canon_decision_measure.py) | Current regression control (actual pre-fix reversion, 2026-10-11) |

The main concrete unfinished implementation is AC65: six justified default decisions and complete canon/golden contracts. The LOD covering fixture has many measured nondegenerate UV islands; island count alone does not establish equivalence to the original Tripo failure topology. New controls close regression-evidence gaps for numerical serialization and ledger classification; they do not remove either of these requirements.

No private owner asset was opened, no provider request was sent, and no shared source/test file was modified by this reconciliation.

Published successors7082fa44 and308a1f00 add separately attributed evidence. The source-name guard now scans production files beneath a tests-named ancestor and excludes only test descendants. The existing WezTerm user-config case forces a long runtime root and checks the actual owned shortened socket; its old prefix assertion fails before the corrected assertion passes. The retained combined server selection passes23tests. These are guard/test corrections, with no production terminal behavior change.

The boot-height fix replaces absolute knee height with knee-minus-sole length. Both body-only and joint body/piece translations retain scale1.03and exact1m output covariance. Retained in-memory original-numerator reversion fails2cases; restored root checks pass2and the worker regression selection passes46. This fixes a measured placement invariant while keeping the boots anchor explicit; no physical default is selected. The source hashes, original RED results, current reversion controls and GREEN XML remain separately attributed in the private successor evidence association. AC02's universal historical chronology requirement remains open.


## Pre-fix reversion controls for the 17 groups (PR #1 finish, 2026-10-11)

Each control runs in a disposable clone of `ea85d6ea` with a copy of the gated binary (`BUILT_FROM ea85d6ea`): the maintained covering test PASSES on the restored source, FAILS by assertion with the pre-fix behaviour put back (collection, import and syntax failures excluded), and PASSES again with the file byte-equal to HEAD. Mutations restore the fix commit's pre-fix lines or, where the code has moved since, the same behaviour in the current source. Logs are private; their hashes are below.

| fix group | fix commit | pre-fix behaviour restored (current source) | FAILED node (mutant) | mutant SHA-256 | log SHA-256 |
|---|---|---|---|---|---|
| G2 | `47fc25df` | no 1e-5 m positional identity: UV-split seams count as open boundary (pre-fix G.boundary_edges(T)) | `tests/lampway_tools/test_canon_fit_body_package.py::test_seam_split_topology_and_native_openings_use_winding_without_welding_authored_vertices` | `456c715370de0b0bd7552d83dfc66dfb5d39e60ee9bccd12b378d80de7e98117` | `f095820b41a25b63edf8120203aae245025c3ec6c3c95c6c5ecbf577574dd21a` |
| G3 | `afcbe66d` | hidden working copies are not revealed for Edit Mode (pre-fix: no visibility handling) | `tests/lampway_tools/test_rig_conform.py::test_hidden_rig_conform_restores_visibility_and_reports_actionable_runtime_error` | `0cefa90079a5269dd7c3b495504e4640b8a5d3753a3142d5048a6e5187c2050a` | `6e52e506c102a33d8db092d0ef10f7e7d070dfe78da20173f40a1be0e6e05a65` |
| G10 | `df50ecd5` | no low matched-fraction warning naming lampway_fit_place (pre-fix receipt had none) | `tests/lampway_tools/test_wave3_weights.py::test_three_percent_matched_transfer_names_placement_and_threshold` | `dfea4ce3d89e0057d5a435cc900b185e603a3cc9cc985feb6a8eccde0f07bbbf` | `d658c4ee355688da9f7fe849d60a02f46cd5210546956ca99cdaeeda5d7bb400` |
| G14 | `afcbe66d` | no local /app landing route (pre-fix: the menu's buttons pointed at a missing page) | `tests/test_auth.py::test_local_profile_destinations_resolve_without_paid_actions` | `736b4e071344016591ab1bb312994d981f066ee8fa3aec79f8bd610041c0ca1d` | `710cc6b22930918ec923eca6bbe2963310ae157ea5304bac4ae0430bf7b70024` |
| G17 | `afcbe66d` | modal_active refusal without the ESC recovery next_step (pre-fix UIError.result) | `tests/mcp/test_ui_ownership.py::test_popup_scene_tool_refusal_names_esc_recovery` | `a1c7244e7386ea6e72ccbb770169583db4b18820d9f8abcf644a156c0958b0ab` | `6b3eb1f0d17e274d1fada506f196efba3e3f9d7a52c401ada1c8a31cb89526ef` |
| G18 | `afcbe66d` | pre-fix line: a pre-startup tools/list snapshot keeps the reconnect flag after the relay is up | `tests/mcp/test_tool_availability.py::test_scene_tool_status[ready-False-True-available]` | `30febc2e8c1cfb069714ea7cb10bc628cbc661a7e606c08ed0972b3f879ab7fc` | `f2d26acc730614cb3d5ea32690242d31d49d2cfdbca9da2c588bbbe1a402012e` |
| G20 | `afcbe66d` | nested calibration shapes reach file reads before a shape refusal (pre-fix: no px_per_m check) | `tests/lampway_tools/test_wave4_multiview.py::test_multiview_nested_shapes_refuse_before_reading_missing_files` | `bbb278fcdb8503a87d3bbd5dd4730db891b93852a1c8590baf463b44a202028c` | `51627b7f56572b22087adfc0f3650bf083f1761d6b90be895f50f596643b1553` |
| G21 | `afcbe66d` | pre-fix line: an empty library still gets a migration backup | `tests/test_library_store.py::test_new_empty_library_has_no_migration_backups` | `3e870f1c4b60c2e9803c6ee89fcf5f49fa521448c3e1b5a321dcb8e7454b94fe` | `7fadfa2f5177f1a3cc7d1f1157b100c10c2c4ea221cb8c0df8a77fd7e55b253b` |
| G22 | `afcbe66d` | pre-fix message: names no control to click (both 404 routes) | `tests/test_asset_search.py::test_an_untrained_server_says_so_and_search_is_a_404_the_client_understands` | `8fa5419b48b6e7e750e63c49aa2fc1626c8e0f21535313d0b47a8806ced9c156` | `0b551b1c7ce97249be5ebbd933e094f93156b40c2062edefd536179970392dfe` |
| F23 | `afcbe66d` | pre-fix lines: Back drawn under the step rail, not in the footer beside Continue | `tests/lampway/test_lampway_onboarding.py::test_back_and_continue_share_the_footer_not_the_step_rail` | `8e9c3aa4e0050ef99220b9384393782bf2692c5b394a0e2a6d234c39e86a8d96` | `19f2fa5742bfc4f82d43252cb73f6041728312fa940c5bc70a1a648056615436` |
| F8 | `afcbe66d` | pre-fix: mesh_prep returns its unbounded receipt | `tests/lampway_tools/test_feature_workflows.py::test_mesh_prep_default_receipt_is_compact_with_full_shell_pages` | `3bb8c35d13eb4a9cb9a26d766fa1f86a6b2c445fadc7672302992140976dd2ac` | `20ed9ce3db80bf9305ecd7fdc626a1bca89923046f139fc7d5d4965c94ec2b4e` |
| F17 | `afcbe66d` | pre-fix label: text or tooltip only, so native unlabeled controls stay unnamed | `tests/mcp/test_ui_geometry.py::test_original_unlabeled_controls_receive_native_source_labels[t6]` | `f6d6dfc1f6b55ae55d44e06e465daa959dd47f86d43b8195f3bba3486d65f50d` | `27d153d19b44b0f6a99425c6a2b5b06d9dd1b7060e7f6216f94ed3f5939407d0` |
| F21 | `df50ecd5` | pre-fix (df50ecd5^): no requested-object handling at all; tag layers go on whatever the configuration names | `tests/lampway_tools/test_feature_workflows.py::test_qa_tag_layers_matches_the_requested_object_and_piece_configuration` | `5f43e5f35dca3fba96c43f46b2b8329b778d7cda871dd8d485e29061fb01ff10` | `83a1a97fc47ba34cfa83ba60017c196bc60cc9693a1473952b0038694623b205` |
| F25 | `afcbe66d` | every script, read-only included, takes a full checkpoint copy (the 45 MB per turn) | `tests/checkpoints/test_lazy_turn_checkpoint.py::test_read_turn_writes_zero_snapshot_bytes` | `6e5edc30554e4225e494dd41d4808459a96b29ae07a0fd7ef221ef3be7f7c96d` | `3eb8978be027205a43e23f75dd2b439fb3f3adf1b5aca8add22ec373e0b89b55` |
| F10 | `afcbe66d` | pre-fix receipt: no tiles reported for an atlas outside 0..1 | `tests/lampway_tools/test_feature_uv.py::test_atlas_outside_unit_tile_reports_tiles_and_warning` | `093f2f1fa814ef858896d4c0b854ae5f67290f9e193989754e06f787f47634dc` | `e494bb788ff91956fc257ea210abac5347fbcaeacdb51aa4cf239a0338a114b5` |
| browser/routes | `afcbe66d` | pre-fix: the loopback account also goes through the browser PKCE flow | `tests/network/test_sso_desktop_login_url.py::test_loopback_signin_stores_pair_without_browser_or_callback_server` | `3db17eb2186ea1530677a47d66624419555cfb4fa8ffe3847b5046d7252e4f3b` | `ffc4bbdc8510221242b7d65d9177b8beba6c652c5cfca0cf75ddf465536ee1de` |
| canon decisions | `df50ecd5` | the pair decision measures only the one requested mode, not both candidates | `tests/lampway_tools/test_canon_decision_measure.py::test_owner_measurement_pack_records_plate_gap_and_both_pair_modes` | `e3ed4a41c36b05ccf8dde38e40fe48ebd2a659760abed7d060346d9b77de80f8` | `2ff1bc9d0f9d07ff02f8fa1b03f779c82acf1d7e6c42136dfe46dd2ef84615c5` |

Recorded, not credited: G18's session-level tests (`test_context_after_startup_reports_scene_tools_available_when_relay_is_up`, `test_without_a_saved_list_context_clears_startup_flag_when_relay_is_ready`) still pass with the pre-fix line restored, so only the direct status table detects it; for F21, removing only the configured-object match is masked by the separate missing-object check, so the control restores the whole pre-fix behaviour (no requested-object handling).
