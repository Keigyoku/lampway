<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Issue 2 scoped reversion evidence

Baseline: `da135c8dc017bc83b545c2e66397018f2c301d24` (`Strengthen real-shape covering tests and regression controls`). This report records 13 covering controls and 14 additional actual source/function reversions. Baseline source consistency was checked against that commit; each restored source fingerprint below matches its baseline Git blob.

These are current fault-injection and reversion proofs: the named covering tests fail when the specified behavior is removed or replaced. They do **not** reconstruct historical RED-first chronology. Historical matching receipts were not located for the additional lanes in the retained immediate receipt inventory. No universal AC02/AC03 completion claim follows from this subset. The full 342-case worker is still in progress; original-asset, hardware-GPU and physical-default acceptance remain separate evidence.

Native runs use a disposable source overlay with isolated configuration and scene fixtures. Additional source edits occur only in a disposable repository copy and are restored after each run. Receipt locations are private: `<evidence-root>/<receipt-id>.log`. Only SHA-256 fingerprints and exact failing test nodes are published here; raw logs and private paths are omitted.

## Covering controls (13)

Source IDs identify the affected baseline implementations and the committed test that implements each control. Runtime function edits and response plants have no claimed full-file mutant hash; their exact control source is the baseline test blob. Every row has a matching assertion failure, with collection, syntax and missing-import failures excluded.

| control | removed/replaced behavior | implementation / control source | FAILED node | log SHA-256 |
|---|---|---|---|---|
| `retopo` | Disable bound retopo source stamp. | S1 / S2 | T1 | `f41615078f5bb60114ea9ff9ba30954ebf29040dbf0d443398025756ef9362e4` |
| `uv` | Disable bound UV source stamp. | S3 / S2 | T1 | `527ccee0e569344a10276eb0015dbc8ecc3a3ac778330d413b79d70754d34eb4` |
| `lod` | Disable bound LOD source stamp. | S4 / S2 | T1 | `bfa0ee075bf9fe637c9084f2778bb2ad3cd98cbb4b57d04e1d93c5714d641dee` |
| `weights` | Disable bound weight-transfer source stamp. | S5 / S2 | T1 | `183c30c42f91d59abd4bd91dc4c0fdba93ac4063d4fe064a38d10f7f1b85b626` |
| `empty-comparison` | Remove zero-comparison refusal guard. | S6 / S7 | T2 | `a177a00d8fd17e47c7f241a30f9fb3dce968efbaaf7f82c658b375ee379ba225` |
| `missing-root` | Remove missing-root refusal reason. | S6 / S7 | T2 | `2b70403e3b91b2d7605e9ddfaf7057bf83e88ad863c508bb1f7d576efbd5e2e4` |
| `lod-ratio-valid-uv` | Disable achieved-ratio miss warning. | S4 / S8 | T3 | `111b405617a955a2f72dbb2bde93de0c7a0c87bb63595e69d2c91c0aaab5d8f4` |
| `lod-previous-valid-uv` | Disable unchanged-previous-count warning. | S4 / S8 | T3 | `367ae9ae1cb0124a97af4792089da33c5ab694fe578a6dcf998a6861051131f7` |
| `retopo-note` | Remove achieved-versus-target note. | S1 / S9 | T4 | `6da51236a732e5a1d92a33f5f28dc5995f65c13214ce5b55d1f8a320fcc1558c` |
| `glb-context` | Remove native import context override. | S10 / S11 | T5 | `4e64feb721bef2333f667b366e5bc2ff1d99faf9ed30032d08d46e58ffa1e1a0` |
| `glb-cleanup` | Disable optimizer cleanup and imported-ID rollback. | S10, S12 / S11 | T5 | `81bee80034b723579a087179489654825008a80230e239a2b8e5298a90c38b3a` |
| `g12-partial` | Return the first workflow sentence cut at its semicolon. | S13 / S14 | T6 | `2ade3115ae9f74fc5136e72bb1208470a83ce6d9995450361ccfe5ecd6cff7d1` |
| `g12-utf8` | Append an oversized multibyte bullet, then slice bytes at the cap. | S13 / S14 | T6 | `2eca2a9d6260c92f1190d91ae8cd8f1d559aeddf50bd802d075103d3fa09d9b6` |

The GLB-context control detects an empty optimized mesh payload through actual GLB POSITION accessor counts before the mutant native teardown crashes. The restored active-default-Cube case exits normally. The UV fixture has measured nondegenerate islands; its strict 25% boundary and unchanged-count warnings are checked. Lineage checks compare immediate parent names and hashes at all four stages, rather than accepting copied root stamps. The UTF-8 controls require whole emitted sentences and omission of an oversized bullet while retaining a following short sentence.

## Additional actual reversions (14)

The mutant hash identifies the full modified source file. The source catalogue supplies its restored/baseline hash. The schema whole-registry control deliberately reverts the executable test gate itself to exclude MCP-only tools; the existing negative test then fails to raise, demonstrating that the gate is not vacuous.

| control | source | exact substitution | FAILED node | mutant SHA-256 | log SHA-256 |
|---|---|---|---|---|---|
| `g1-scalars` | S15 | `if type(value).__module__ == 'numpy':` → `if False:` | T7 | `7285247dc9962af97e1913a28eb4d0af60c9b654daaa889c1fdeb6f0271482ba` | `c14bd24ab26af635620565e0f44b9708d546cfa0ff8f5ddfa78be42e3c35a4ed` |
| `g15-public-alias` | S16 | `renamed['name'] = OLD_TO_NEW.get(tool['name'], tool['name'])` → `renamed['name'] = tool['name']` | T8 | `bae22edf38cf00edea0f1516417d5bec992c2bec391997d8d00860a9908485a1` | `e033daa92f4d2dc6cae23a2d3b0bc3dbde5b4fb17c106f4a4dc3484d0a5a35c9` |
| `g16-local-descriptions` | S17 | `{**value, "description": _PARAMETER_DESCRIPTIONS[name]}` → `value` | T9 | `169d69702f88d745d79c2d31193f55f8b705a7fc3884c4c5b381f34864f6bdad` | `42b8f88ba1233ad55eedae7f9e71188458d9de02113d6c1e60597c2fec92a8c5` |
| `g16-whole-registry` | S18 | `return [*TOOLS, *SERVER_TOOLS]` → `return [*TOOLS]` | T10 | `55937f7dbb3fa53e0de381a5c8b7dd33e565723e8900160cf0b19de443dc7884` | `06115945854cdbf43126f9626d553e3fdb7ae438827946cae2e634aa8e2d975a` |
| `g19-refusal-template` | S19 | `Next call: lampway_choices action=list` → `Next call: lampway_choices_list` | T11 | `43655fa11de3f3f2e6f46bd7be3ab7b8f2fb1d89fc7a4a30d669f8efecd62cb0` | `10ce283ecfc032189fbc3f72d4442cb3c0d7f72db8216ee92227b281d5235eac` |
| `f6-failure-envelope` | S20 | `or result.get("ok") is False` → `(remove clause)` | T12 | `6c3eb66b69113edf6179f073e24893b8f2b0fe2b2a901f0df0dada1ecac3a707` | `8688528c39c40343abb0eb5e272be7cf89325b3b44441acae0b3baf3704c7fa0` |
| `ac62-canonical-turn` | S21 | `if float(turn) != 0:` → `if False:` | T13 | `cd70f0284441adba6e19018f023144ac6856d68448a984c987b080bee304e16c` | `f3c7698c8c0303b27a2d5112b35d394b504da6e151e4d3d85154500e749fcd05` |
| `g19-native-model-shape` | S22 | `_SPECIFIC_CALLS.get(api_name, _CALL_TEMPLATES.get(api_name, "lampway_status"))` → `_CALL_TEMPLATES.get(api_name, "lampway_status")` | T14 | `6e4d6a7ce808ef8fe88566d491161d95195de3de09580100ac20397a8ff58fdb` | `f5941082641a0b1f223e2ec700489ea1ddf6e31f78ee218c56f1bc82e0edfe43` |
| `f13-native-batch-template` | S22 | `_BATCH_CALL_TEMPLATES.get(batch, "lampway_status") if isinstance(batch, str) else "lampway_status"` → `"lampway_run_tool name=<name> args=<args>"` | T15 | `d7bfecbc3ef02156436930b160d68455f3c5d7729eb6fe3ba25ad745d978dd90` | `34dae688482a33084140f2d0d4385e57faa35e1de258bf14d0bf1ad502988238` |
| `g15-catalogue-size` | S23 | `"spend_policy": "User confirms."` → `"spend_policy": "No spend; only the user confirms."` | T16 | `dd990071ceff6631db9566cb4f16aa8f247dbcf3aa5d83ae1c90498b6a832e0f` | `3ec67a2e37c56b7afab6c36e1fc171574b043f460006bb4152e09c4f2672c69c` |
| `g1-server-scalars` | S24 | `if type(value).__module__ == 'numpy':` → `if False:` | T17 | `7285247dc9962af97e1913a28eb4d0af60c9b654daaa889c1fdeb6f0271482ba` | `a9b254bda4307357a65863aef72515cb8d18951448be6482f7c9830760c1a290` |
| `g15-description-alias` | S16 | `OLD_TO_NEW.get(match.group(), match.group())` → `match.group()` | T8 | `5ad8070128fe50aeef9a914f7d6bfe8423686baf683d22dc1d364f78b3081573` | `379c66f38be63d49e0f3c3ea88180d10f620b70cac67c57443e467cb61bedb65` |
| `g16-local-numeric-bounds` | S17 | `"items": {"type": "number", "minimum": 0, "maximum": 1}` → `"items": {"type": "number"}` | T9 | `b7b8dd152ce0842378dd44c9a59c3661c8d37e6af11c69f7cbabd9b69c0bb5ff` | `c7251853464ed884c021125d11286694f2d4672290e32136d2cd9f2cd2e7d0c3` |
| `g13-generated-counts` | S13 | `return {'agent_tools': len(registry()), 'mcp_tools': len(offered_tools())}` → `return {'agent_tools': 195, 'mcp_tools': 175}` | T18 | `ec5a8892e5553a2add310dce477e89a5a0969bb09b6308ce45b5c160cc9b5781` | `154e79cbf52fbdf5627d8c627d6bd44419b2b4e118beba38413aea8fcdd51684` |

G13 also runs the copied documentation generator after reverting `registry_counts` to 195/175; its emitted count paragraph fails the live-registry assertion. G15 restores the actual prior metadata phrase while preserving `spend: false` and the initialization policy: the full catalogue becomes **337,709 bytes**, exceeding the existing **335,000-byte** bound. An unrelated inline-schema expansion stress control and a historical glove-description substitution that still passed are excluded from the 14 credited reversions.

## Exact failing nodes

- **T1**: `tests/lampway_tools/test_feature_workflows.py::test_retopo_uv_lod_weight_chain_records_original_source_and_passes_identity`
- **T2**: `tests/lampway_tools/test_wave3_export_checks.py::test_empty_comparison_and_missing_root_cannot_pass`
- **T3**: `tests/lampway_tools/test_wave6_lod_chain.py::test_many_uv_islands_report_achieved_ratios_and_protection_warnings`
- **T4**: `tests/lampway_tools/test_feature_retopo.py::test_voxel_reports_achieved_count_against_target`
- **T5**: `tests/lampway_tools/test_wave6_glb_optimize.py::test_default_cube_context_and_failed_import_leave_all_ids_unchanged`
- **T6**: `server/tests/test_agent_files.py::test_g12_initialize_cap_omits_whole_bullets`
- **T7**: `tests/lampway_tools/test_axi.py::test_numpy_scalars_in_real_table_and_kv_shapes[mixar.modules.lampway_tools.axi]`
- **T8**: `tests/mcp/test_lampway_tool_aliases.py::test_g15_public_catalogue_excludes_deprecated_names_and_mentions`
- **T9**: `tests/mcp/test_lampway_tool_aliases.py::test_every_local_ui_parameter_is_described_and_numeric_bounds_are_recursive`
- **T10**: `server/tests/test_tool_schema_ratchet.py::test_mcp_only_parameters_are_in_the_whole_registry_ratchet`
- **T11**: `server/tests/test_refusal_templates.py::test_choices_bad_action_names_a_callable_list`
- **T12**: `server/tests/test_mcp_operation_lease.py::test_failed_batch_inside_successful_executor_is_an_mcp_error`
- **T13**: `tests/lampway_tools/test_wave2_piece_ratios.py::test_declared_raw_and_normalized_frame_score_identically_and_cannot_turn_twice`
- **T14**: `tests/lampway_tools/test_refusal_templates_binary.py::test_invalid_model_set_refusal_gives_an_actionable_public_shape`
- **T15**: `tests/lampway_tools/test_refusal_templates_binary.py::test_jailed_batch_refusal_names_the_actual_registered_batch`
- **T16**: `tests/mcp/test_lampway_tool_aliases.py::test_g15_whole_catalogue_size_is_bounded`
- **T17**: `tests/lampway_tools/test_axi.py::test_numpy_scalars_in_real_table_and_kv_shapes[lampway_server.studios.axi]`
- **T18**: `server/tests/test_agent_files.py::test_g13_connect_ai_apps_counts_come_from_the_live_registry`

## Baseline source fingerprints

| source | repository path | SHA-256 at baseline / after restoration |
|---|---|---|
| S1 | `src/scripts/mixar/modules/lampway_tools/features/retopo.py` | `252c7979d0f476ca60d0d7579c7e12b08b6ccf7601ad5ded66eae59b58dbe954` |
| S2 | `tests/lampway_tools/test_feature_workflows.py` | `58568d197b037f7a3846bb67727428e41735948c0fc65bfc11415e90e1441e2b` |
| S3 | `src/scripts/mixar/modules/lampway_tools/features/uv.py` | `3c8a873155f9f3021e1f759021277c270633a0eb0f2ddfe01bdbd3dd50711fb4` |
| S4 | `src/scripts/mixar/modules/lampway_tools/features/lod_chain.py` | `0b84b39e729bbbf640ff3127270fdb5ddd1422243f46527f5631b07e9960d6fc` |
| S5 | `src/scripts/mixar/modules/lampway_tools/features/weights.py` | `67d65bd26adf2c8d28e61ab1459c70a271dd48ad2b48933e4e0e863f8a98d678` |
| S6 | `src/scripts/mixar/modules/lampway_tools/features/export_checks.py` | `1623c437150fc2a4245436854967769a0ff486e913063d12906d560437df157a` |
| S7 | `tests/lampway_tools/test_wave3_export_checks.py` | `bb864afa2ad325f2ce04e146773623682575b933286f50e5a0f25483e617b6ec` |
| S8 | `tests/lampway_tools/test_wave6_lod_chain.py` | `20f6fde954830ac9be0fbd9c8248bf80590678df8f35570d4c2cf39233a162aa` |
| S9 | `tests/lampway_tools/test_feature_retopo.py` | `2d490a858cde257c8d9ac95d98b94e6ece874078f8a009cfddd36c62b7c319fc` |
| S10 | `src/scripts/mixar/modules/lampway_tools/features/glb_optimize.py` | `f224683d24a4ba778f6acb19439e121857e7cae9b87340ebd8302d2887944c69` |
| S11 | `tests/lampway_tools/test_wave6_glb_optimize.py` | `d57b8bd075e31c13d2ac73f05b8fbc01d3a72e526b2859cd6d2358af50547c0c` |
| S12 | `src/scripts/mixar/modules/lampway_tools/canon_io.py` | `ad31574642fc5dc664b3b0526c13a03b11db1dd9d6bff0f3a7e6f79ad054e675` |
| S13 | `server/lampway_server/agent_files/generate.py` | `21ee9b8b39ddb707fce2c7718792b66999a03103dbf1d5911f03781c3cbd8fed` |
| S14 | `server/tests/test_agent_files.py` | `918afe8d133a62a834b9023d7ae6f8b818cec732f46de0eadc3a71c0d1707b24` |
| S15 | `src/scripts/mixar/modules/common/toon/codec.py` | `a0066102d8a741ce39daec721931a85852fdb5bf3ecbd0d63cab458cdb1524e9` |
| S16 | `src/scripts/mixar/modules/mcp_bridge/core/aliases.py` | `567590632f8484d372c465008764b32acf6b9a437754941cce2617744253e92d` |
| S17 | `src/scripts/mixar/modules/common/ui_control/core/schema.py` | `72889990355382cf33d12329982f2221904582595e71723a3a24e49d14f32588` |
| S18 | `server/tests/test_tool_schema_ratchet.py` | `fdc0c0e1730707d72347ac788b9dd971988e696890c5648aca183498ad1546e0` |
| S19 | `server/lampway_server/agent/choices_tools.py` | `3f1c1e1d551eda91b0a6337614b5ee1c04427dc45d1ebf3310d22da14e664c39` |
| S20 | `server/lampway_server/agent/tools.py` | `bac1777a96b6d65169869129544e9f5c2d2ef4c2fb02c45226cc9241202bb00e` |
| S21 | `src/scripts/mixar/modules/lampway_tools/scripts/proportion/frame.py` | `3e041a25b961cfe5e0fd74147986612db0331c8dffeb94ec5d2ea5cc8e85a35e` |
| S22 | `src/scripts/mixar/modules/lampway_tools/api.py` | `ca21f2f680b13f5151b7cd2a40cd99650e94cd0b02a3d957437b4b6e70eb59e9` |
| S23 | `server/lampway_server/mcp.py` | `233ece95c8de5e2c2e9e09e4e8dd53de346e538c2ccb6161643c21fc25332e8b` |
| S24 | `server/lampway_server/compute/toon_out.py` | `a0066102d8a741ce39daec721931a85852fdb5bf3ecbd0d63cab458cdb1524e9` |

## Restored GREEN receipts

| receipt ID | result | log SHA-256 |
|---|---|---|
| `covering-native-green` | 6 passed, 29 deselected; 14.02 s | `0a332c0ed216c812b70ba01ae55625527d5c09f8e858f42b64b7165a820bc253` |
| `covering-guidance-green` | 3 passed | `cf426ab35f3b06fccef8290fde5325d90af130a79da1d1752031518df77c4236` |
| `additional-restored-green` | 12 passed, 99 deselected; 5.05 s | `cb33292d893a2063e001ce4dd7872f33576370d2f1b24107346f74f2a8622a17` |

The 12-case restored run includes both scalar-codec parameters, public alias/catalogue checks, local schema debt, the MCP-only ratchet plant, actual server refusal, failed-batch lease transport, declared-frame native parity/refusal, native model/batch refusal shapes, and regenerated registry counts. These passing results support the scoped controls above; they do not certify every issue criterion.

## Successor controls

The item10 existing covering case at `8e47cfe34bc9ad12671017473c53da7ac9edd701` verifies actual achieved faces and the requested target in the fallback note. Its isolated native run passes; reverting the production note expression in a disposable child process makes the same case fail. The production source was not edited for that control. Private receipts: `retopo-cover-root.xml`, `retopo-cover-control/control.xml` and `control-source.json`.

The bounded numerical-frame fix at `f13fa7d9de627bc9e47efa5d3b7c25083ffb8edd` retains the unchanged proper-rotation validator. A complete342-bone oblique native graph fails before correction and passes after it; material shear, reflection, singularity and the producer-budget boundary retain refusal controls. Three supplied owner measurements also pass via an explicitly supplied private fixture; their matrices are not committed. The independent26-test run and13 retained normalization/rig/export checks pass. These component controls do not replace the actual complete-owner normalization/export rerun or establish universal historical RED-first chronology.
