-- An import is one batch: rollback soft-deletes its assets (rows only, never files).
CREATE TABLE batch(id TEXT PRIMARY KEY, label TEXT, source_id INTEGER REFERENCES source, started_at REAL, finished_at REAL);
ALTER TABLE asset ADD COLUMN batch_id TEXT REFERENCES batch;
CREATE INDEX asset_batch ON asset(batch_id);
