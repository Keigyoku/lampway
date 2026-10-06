-- Asset Vault schema v1 (specs/asset_library/asset_schema.md section 5.2). Deviations from the spec text, on purpose:
--   source.root and relation.role are NOT NULL DEFAULT '' so the UNIQUE constraints bite (SQLite treats NULLs as distinct);
--   texset_stats / map_channel were named but not defined by the spec: minimal columns here.
CREATE TABLE blob(sha256 TEXT PRIMARY KEY, bytes INTEGER NOT NULL, mime TEXT, cas_path TEXT, first_seen REAL NOT NULL);
CREATE TABLE location(sha256 TEXT NOT NULL REFERENCES blob, path TEXT NOT NULL, storage TEXT NOT NULL CHECK(storage IN('cas','external')),
  mtime REAL, size INTEGER, last_verified REAL, missing INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(sha256,path));
CREATE TABLE source(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, root TEXT NOT NULL DEFAULT '', label TEXT, config_json TEXT, enabled INTEGER NOT NULL DEFAULT 1, UNIQUE(kind,root));
CREATE TABLE license(id TEXT PRIMARY KEY, name TEXT, url TEXT, attribution_required INTEGER NOT NULL DEFAULT 0, commercial_ok INTEGER, redistribute_ok INTEGER);
CREATE TABLE asset(id TEXT PRIMARY KEY, kind TEXT NOT NULL, subtype TEXT, name TEXT NOT NULL, slug TEXT, description TEXT,
  source_id INTEGER REFERENCES source, source_key TEXT,
  license_id TEXT REFERENCES license, attribution TEXT, current_version INTEGER, status TEXT NOT NULL DEFAULT 'active'
  CHECK(status IN('active','archived','deleted')), rating INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  UNIQUE(source_id, source_key));
CREATE TABLE version(id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES asset, n INTEGER NOT NULL, content_key TEXT NOT NULL,
  created_at REAL NOT NULL, note TEXT, attrs_json TEXT NOT NULL DEFAULT '{}', UNIQUE(asset_id,n), UNIQUE(asset_id,content_key));
CREATE TABLE version_file(version_id TEXT NOT NULL REFERENCES version, role TEXT NOT NULL, ord INTEGER NOT NULL DEFAULT 0,
  sha256 TEXT NOT NULL REFERENCES blob, PRIMARY KEY(version_id,role,ord));
CREATE TABLE mesh_stats(version_id TEXT PRIMARY KEY, verts INTEGER, faces INTEGER, tris INTEGER, quads INTEGER, topology TEXT,
  bbox_min_json TEXT, bbox_max_json TEXT, dim_x REAL, dim_y REAL, dim_z REAL, unit_scale REAL, watertight INTEGER, open_loops INTEGER,
  shells INTEGER, materials INTEGER, uv_sets INTEGER, skinned INTEGER, bones INTEGER, texel_density_px_per_m REAL, texture_bytes INTEGER);
CREATE TABLE mesh_lod(version_id TEXT, level INTEGER, faces INTEGER, sha256 TEXT, PRIMARY KEY(version_id,level));
CREATE TABLE uv_set(version_id TEXT, name TEXT, islands INTEGER, coverage REAL, overlap REAL, texel_min REAL, texel_median REAL, texel_max REAL,
  udim INTEGER, score REAL, layout_sha256 TEXT, PRIMARY KEY(version_id,name));
CREATE TABLE mesh_part(version_id TEXT, part TEXT, class TEXT, faces INTEGER, bbox_json TEXT, material TEXT, PRIMARY KEY(version_id,part));
CREATE TABLE image_stats(version_id TEXT PRIMARY KEY, width INTEGER, height INTEGER, channels INTEGER, bit_depth INTEGER, colorspace TEXT,
  has_alpha INTEGER, dhash TEXT, mean_rgb_json TEXT, palette_json TEXT, tileable REAL, normal_convention TEXT);
CREATE TABLE material_stats(version_id TEXT PRIMARY KEY, shader TEXT, inputs_json TEXT, metallic_mean REAL, roughness_mean REAL, tileable INTEGER,
  build_ms REAL, generator TEXT, role TEXT);
CREATE TABLE texset_stats(version_id TEXT PRIMARY KEY, maps_json TEXT, resolution INTEGER, colorspace TEXT);
CREATE TABLE map_channel(version_id TEXT PRIMARY KEY, channel TEXT, convention TEXT, bit_depth INTEGER);
CREATE TABLE rig_stats(version_id TEXT PRIMARY KEY, bones INTEGER, naming TEXT, humanoid INTEGER, has_fingers INTEGER);
CREATE TABLE anim_stats(version_id TEXT PRIMARY KEY, frames INTEGER, fps REAL, duration_s REAL, loops INTEGER, root_motion INTEGER, rig TEXT, motion_type TEXT);
CREATE TABLE prompt_stats(version_id TEXT PRIMARY KEY, template_id TEXT, template_version TEXT, vars_json TEXT, chars INTEGER);
CREATE TABLE video_stats(version_id TEXT PRIMARY KEY, container TEXT, codec TEXT, profile TEXT, pix_fmt TEXT, width INTEGER, height INTEGER, sar TEXT,
  rotation INTEGER, container_fps REAL, avg_fps REAL, frame_count INTEGER, duration_s REAL, bitrate INTEGER, has_audio INTEGER, audio_codec TEXT,
  audio_silent INTEGER, motion_fps REAL, motion_fps_confidence REAL, dup_frames INTEGER, dup_ratio REAL, longest_hold INTEGER, blend_suspect INTEGER,
  panel_layout TEXT, panels_json TEXT, view TEXT, camera_template TEXT, motion_type TEXT, loop_score REAL, analyzed_with TEXT);
CREATE TABLE generation(id TEXT PRIMARY KEY, version_id TEXT REFERENCES version, studio TEXT, provider TEXT, model TEXT, model_version TEXT,
  action TEXT, prompt_asset TEXT REFERENCES asset, prompt_text TEXT,
  prompt_sha256 TEXT, template_id TEXT, template_version TEXT, params_json TEXT, seed TEXT, seed_not_exposed INTEGER,
  cost_usd REAL, cost_credits REAL, cost_basis TEXT, job_id TEXT, parent_seed_asset TEXT REFERENCES asset,
  start_frame_asset TEXT, end_frame_asset TEXT, reference_video_asset TEXT, reference_image_assets_json TEXT,
  started_at REAL, finished_at REAL, approved_by TEXT, ledger_ref TEXT, tool TEXT, tool_version TEXT);
CREATE TABLE relation(id INTEGER PRIMARY KEY, src TEXT NOT NULL REFERENCES asset, dst TEXT NOT NULL REFERENCES asset, type TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT '', src_version INTEGER, dst_version INTEGER, attrs_json TEXT, by TEXT NOT NULL, created_at REAL NOT NULL,
  CHECK(type IN('derived_from','variant_of','part_of','textured_by','fits_body','rigged_to','generated_from','drives','uses','frame_of','supersedes')),
  UNIQUE(src,dst,type,role));
CREATE TABLE term(id INTEGER PRIMARY KEY, facet TEXT NOT NULL, label TEXT NOT NULL, parent_id INTEGER REFERENCES term, synonyms_json TEXT, UNIQUE(facet,label));
CREATE TABLE asset_term(asset_id TEXT NOT NULL REFERENCES asset, term_id INTEGER NOT NULL REFERENCES term, by TEXT NOT NULL,
  confidence REAL, rule TEXT, ts REAL NOT NULL, PRIMARY KEY(asset_id,term_id));
CREATE TABLE tag(asset_id TEXT NOT NULL REFERENCES asset, tag TEXT NOT NULL, by TEXT NOT NULL, PRIMARY KEY(asset_id,tag));
CREATE TABLE rating(asset_id TEXT NOT NULL REFERENCES asset, rater TEXT NOT NULL, stars INTEGER CHECK(stars BETWEEN 1 AND 5), flag TEXT CHECK(flag IN('pick','reject',NULL)),
  note TEXT, ts REAL NOT NULL, PRIMARY KEY(asset_id,rater,ts));
CREATE TABLE decision(id INTEGER PRIMARY KEY, session TEXT, asset_id TEXT, version_id TEXT, question TEXT NOT NULL, options_json TEXT, answer TEXT NOT NULL,
  decider TEXT NOT NULL, how TEXT, descriptor_json TEXT, descriptor_sha256 TEXT, words TEXT, ts REAL NOT NULL);
CREATE TABLE gate_result(id INTEGER PRIMARY KEY, version_id TEXT NOT NULL, gate TEXT NOT NULL, value REAL, threshold REAL, passed INTEGER NOT NULL,
  detail_json TEXT, run_id TEXT, ts REAL NOT NULL);
CREATE TABLE collection(id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN('board','smart')), query_json TEXT, note TEXT, created_at REAL);
CREATE TABLE collection_item(collection_id TEXT, asset_id TEXT, ord INTEGER, note TEXT, x REAL, y REAL, PRIMARY KEY(collection_id,asset_id));
CREATE TABLE saved_search(id TEXT PRIMARY KEY, name TEXT NOT NULL, query_json TEXT NOT NULL, owner TEXT, created_at REAL);
CREATE TABLE embedding(version_id TEXT NOT NULL, space TEXT NOT NULL, sub_key TEXT NOT NULL DEFAULT '', dim INTEGER NOT NULL, dtype TEXT NOT NULL,
  vec BLOB NOT NULL, model TEXT, model_version TEXT, created_at REAL, PRIMARY KEY(version_id,space,sub_key));
CREATE VIRTUAL TABLE asset_fts USING fts5(name, description, terms, tags, prompt, path_tokens, tokenize='unicode61 remove_diacritics 2', prefix='2 3');
CREATE TABLE event(id INTEGER PRIMARY KEY, ts REAL NOT NULL, actor TEXT NOT NULL, verb TEXT NOT NULL, asset_id TEXT, detail_json TEXT);
