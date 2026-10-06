-- The read-only SQL view surface (asset_query section 6.8). Power users and agents with a grant query these, never the tables.
CREATE VIEW v_assets AS
  SELECT a.id, a.kind, a.subtype, a.name, a.status, a.rating, a.license_id, a.created_at, a.updated_at, a.current_version, a.batch_id, s.kind AS source_kind, a.source_key,
         m.verts, m.faces, m.tris, m.topology, m.dim_x, m.dim_y, m.dim_z, m.materials, m.uv_sets, m.skinned, m.bones,
         i.width, i.height, i.dhash, vs.duration_s, vs.avg_fps, vs.motion_fps, vs.dup_frames
  FROM asset a
  LEFT JOIN source s ON s.id = a.source_id
  LEFT JOIN version v ON v.asset_id = a.id AND v.n = a.current_version
  LEFT JOIN mesh_stats m ON m.version_id = v.id
  LEFT JOIN image_stats i ON i.version_id = v.id
  LEFT JOIN video_stats vs ON vs.version_id = v.id;
CREATE VIEW v_versions AS SELECT v.id, v.asset_id, v.n, v.content_key, v.created_at, v.note, v.attrs_json, (a.current_version = v.n) AS is_current FROM version v JOIN asset a ON a.id = v.asset_id;
CREATE VIEW v_files AS
  SELECT f.version_id, v.asset_id, v.n AS version, f.role, f.ord, f.sha256, b.bytes, b.mime, l.path, l.storage, l.missing
  FROM version_file f JOIN version v ON v.id = f.version_id JOIN blob b ON b.sha256 = f.sha256 LEFT JOIN location l ON l.sha256 = f.sha256;
CREATE VIEW v_relations AS
  SELECT r.id, r.src, sa.name AS src_name, r.type, r.role, r.dst, da.name AS dst_name, r.by, r.created_at
  FROM relation r JOIN asset sa ON sa.id = r.src JOIN asset da ON da.id = r.dst;
CREATE VIEW v_provenance AS
  SELECT g.id, v.asset_id, a.name, v.n AS version, g.studio, g.provider, g.model, g.action, g.prompt_text, g.template_id, g.seed, g.cost_usd, g.cost_credits, g.cost_basis, g.job_id,
         g.started_at, g.finished_at, g.approved_by, g.tool
  FROM generation g JOIN version v ON v.id = g.version_id JOIN asset a ON a.id = v.asset_id;
CREATE VIEW v_gates AS
  SELECT gr.id, v.asset_id, a.name, v.n AS version, gr.gate, gr.value, gr.threshold, gr.passed, gr.run_id, gr.ts
  FROM gate_result gr JOIN version v ON v.id = gr.version_id JOIN asset a ON a.id = v.asset_id;
CREATE VIEW v_video_clips AS
  SELECT a.id, a.name, a.status, vs.container, vs.codec, vs.width, vs.height, vs.container_fps, vs.avg_fps, vs.motion_fps, vs.frame_count, vs.duration_s, vs.has_audio, vs.dup_frames, vs.dup_ratio,
         vs.panel_layout, vs.view, vs.camera_template, vs.motion_type, vs.loop_score
  FROM asset a JOIN version v ON v.asset_id = a.id AND v.n = a.current_version JOIN video_stats vs ON vs.version_id = v.id WHERE a.kind = 'video';
CREATE VIEW v_ratings_latest AS
  SELECT r.asset_id, r.rater, r.stars, r.flag, r.note, r.ts FROM rating r
  WHERE r.ts = (SELECT max(r2.ts) FROM rating r2 WHERE r2.asset_id = r.asset_id AND r2.rater = r.rater);
CREATE VIEW v_terms AS
  SELECT at.asset_id, a.name, t.facet, t.label, at.by, at.confidence FROM asset_term at JOIN term t ON t.id = at.term_id JOIN asset a ON a.id = at.asset_id;
