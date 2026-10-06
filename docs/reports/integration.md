# Integration log (branch lp/wave5)

Role: the implementer became the integrator; lanes lp/vault-ops, lp/vault-ui, lp/facelift and lp/docs merge `origin/lp/wave5` themselves; this log records each merge into lp/wave5.

## Integration glue

### F8: OpenRouter follows the cloud D1 click rule (found by the coordinator's site truth-check)
- Was: `DEFAULT_SPEND_POLICY["openrouter"] == {"click": "off"}`: no per-call click; only the $3 session ceiling and the per-request token cap gated spend.
- Now: `{"click": "above", "above": 0.25}` (configurable in provider prefs; `off` still works). The session ceiling is unchanged.
- Consequence found while doing it: the job queue asked the policy about an UNKNOWN price for every image job, which under any "above" rule means a click for every image. The queue now passes an estimate (`IMAGE_USD_ESTIMATE = 0.07` per image, from the spike's measured ~$0.067, times `number_of_images`); only the click decision uses it, never a charge. One to three images run untouched; four or more wait for the click.
- RED first: `test_openrouter_defaults_to_the_d1_rule_a_click_above_25_cents` failed on the old default; the three existing job-queue tests then hung on the unknown-price click, which is what drove the estimate; `test_image_jobs_follow_the_d1_click_rule_by_estimated_price` pins both sides (mutant: dropping the per-image multiplier fails it).

## Merges
(none yet: this section is appended per merge with lane, range, conflicts, suite and gate results)

## Requests to lanes
(none yet)

## Lane overlap and duplication seen
- The asset_mcp tool family (`lampway_vault_*`) was drafted by the previous implementer but not committed: a test draft is at `scratch/test_library_vault_tools.draft.py` for lane lp/vault-ui (asset_mcp is its contract). Its design: server-run tools (`agent/vault_tools.py`), a `Vault` facade (lib + ingest + embed + spool + project root), origin `agent|mcp`, rater `agent:<id>`, no SQL tool and no import tool, `scan` restricted to the project root or a user-registered source.
