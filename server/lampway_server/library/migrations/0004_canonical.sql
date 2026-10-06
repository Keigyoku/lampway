-- The normalization door (specs/canon/normalization DOOR.md section 4, contracts/canon_migration.md section 6): the Vault keeps raw and
-- canonical apart. A version of a geometry / rig / animation / map / texture kind is 'canonical' (its lampway.canonical-asset/1 document in
-- `canonical`) or 'raw'; every version stored before this migration is raw. `normalized_from` links a canonical version to the raw one.
CREATE TABLE canonical(version_id TEXT PRIMARY KEY REFERENCES version, schema_version INTEGER NOT NULL, kind TEXT NOT NULL, frame TEXT NOT NULL,
  scale_state TEXT NOT NULL, scale_decision TEXT NOT NULL, canonical_sha256 TEXT NOT NULL, raw_sha256 TEXT NOT NULL, receipt_sha256 TEXT NOT NULL,
  doc_json TEXT NOT NULL);
ALTER TABLE version ADD COLUMN canon_state TEXT CHECK(canon_state IN('raw','canonical'));
UPDATE version SET canon_state='raw' WHERE asset_id IN (SELECT id FROM asset WHERE kind IN('mesh','rig','animation','map','texture_set','material'));
DROP VIEW IF EXISTS v_relations;
CREATE TABLE relation_new(id INTEGER PRIMARY KEY, src TEXT NOT NULL REFERENCES asset, dst TEXT NOT NULL REFERENCES asset, type TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT '', src_version INTEGER, dst_version INTEGER, attrs_json TEXT, by TEXT NOT NULL, created_at REAL NOT NULL,
  CHECK(type IN('derived_from','variant_of','part_of','textured_by','fits_body','rigged_to','generated_from','drives','uses','frame_of','supersedes','normalized_from')),
  UNIQUE(src,dst,type,role));
INSERT INTO relation_new SELECT id, src, dst, type, role, src_version, dst_version, attrs_json, by, created_at FROM relation;
DROP TABLE relation;
ALTER TABLE relation_new RENAME TO relation;
CREATE VIEW v_relations AS
  SELECT r.id, r.src, sa.name AS src_name, r.type, r.role, r.dst, da.name AS dst_name, r.by, r.created_at
  FROM relation r JOIN asset sa ON sa.id = r.src JOIN asset da ON da.id = r.dst;
