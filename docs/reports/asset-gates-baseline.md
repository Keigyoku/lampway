# Asset Vault gates: the first measured baseline (2026-10-06)

Produced by `lampway_server.library.gates.run` over `corpus.build(n=10000, seed=20261005)` (200 planted exact copies, 200 planted near duplicates: 10 200
assets in all). Machine: 16 cores, SQLite 3.51.2, Python 3.14.7. **The box was shared and busy**: load average 19.9 / 20.7 / 19.6 when the run started (eight
lanes building and testing), so the performance numbers are an upper bound for a quiet box, not a measurement of one. Corpus build: 531 s under that load.
Corpus content hash: `143ece1c84a28871ab71fc3a82b289af824942f97b4410ad6b5c08a184f0a348`. Gates took 17.9 s.

| gate | value | threshold | verdict |
|---|---|---|---|
| latency | text+filter p50 4.0 ms, p95 7.6 ms; filter p95 10.1 ms; get p95 5.8 ms; similar (512-d brute force, 10 200 rows) p95 21.2 ms; cold 44.6 ms (200 queries per type) | p95 < 50 / 20 / 100 ms, cold < 300 ms | pass |
| throughput | 89.2 puts/s (300 small puts in one `bulk()`) | >= 200 | **fail** |
| coverage | 9 598 / 9 598 thumbnails | >= 0.99 | pass |
| provenance | 3 423 / 3 423 generation rows complete | 1.0 | pass |
| dedupe | no content in two assets; exact copies 100 % deduped; near duplicates found at dHash <= 4: 200/200; auto-merged 0 | exact 1.0, near >= 0.9, 0 merges | pass |
| fts_parity | 10 200 active = 10 200 FTS rows; 20 prefix-token queries match the source text | exact | pass |
| recall | 1.0 (top-k same cluster, k bounded by the cluster size) | >= 0.9 | pass |
| schema | 0 FK violations, no pending migration, a newer DB refused | pass | pass |
| integrity | `integrity_check` ok; a `VACUUM INTO` backup restores 10 200 / 10 200 | pass | pass |
| privacy | 0 signed URLs or keys in text columns | 0 | pass |
| memory | 91.9 MB peak RSS after loading every space | < 400 MB | pass |
| idle | not run: needs a live render batch's load samples (see the lane report) | load < 0.6 x cores | not-run |

## The one failing gate
`throughput` fails on this box: 44-46 puts/s at load 20 in the suite's runs, 89 puts/s in this run. A profile of 300 puts shows 6.7 of 6.9 s inside
`sqlite3.Connection.execute`, almost all of it in each put's own transaction commit (`asset_store` opens one `BEGIN IMMEDIATE ... COMMIT` per `put`; `bulk()`
batches only the journal's fsync). Not fixed here: it is `asset_store`'s design, outside this lane's contracts. The obvious repair is a `bulk()` that also holds
one transaction across its puts; whether that is wanted (a crash then loses the whole batch, not one asset) is a store-owner decision.

## What the numbers do not show
- The `throughput` and `latency` numbers were taken under load 20: rerun on a quiet box before treating them as the box's capacity.
- `recall` is over the synthetic clustered vectors (planted ground truth), not a real model space; the real CLIP and bge sanity is in the lane report.
- `coverage` here counts the corpus's planted thumbnails; on the user's library it measures what `asset_render` actually produced (run it with `run_on_copy`).
- The suite (`server/tests/test_library_gates.py`) builds 1 500 assets: correctness gates must pass there; performance gates are measured, and their verdicts
  belong to a baseline like this one, not to a shared box's CI. Every gate has a mutant in that file that turns it red.
