"""seed_catalog: the typed catalogue of every seed (a Tripo generation variant, a banked Edit Mesh reroll) with its stage, model version and settings, its proportion score
and its verdicts. One SQLite file under the project root, the same ``seeds`` table the shelf's seed_db.py keeps (the bundled studios/tripo/seed_db.py CLI shares it) plus four
columns: stage, model_version, settings_json, seed (a seed is stage + model + settings, never a style token; ``not_exposed`` when the Studio shows none).

NEVER a signed URL: a per-file signature is a credential, so it is stripped (and said). Only the user picks a seed; an agent's ``usable`` is a proposal. Every verdict
is also a row of decisions.jsonl (the typed log that trains a decision model later); a correction is a new row, the latest wins."""

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

try:
    import fcntl
except ImportError:                                  # pragma: no cover
    fcntl = None

VERDICTS = ("pick", "reroll", "reject", "usable", "fix")
SCHEMA = """CREATE TABLE IF NOT EXISTS seeds (
  id TEXT PRIMARY KEY, piece TEXT, kind TEXT, parent_id TEXT, project_id TEXT, created_at INTEGER, topology TEXT, faces INTEGER,
  url TEXT, file TEXT, sha256 TEXT, bytes INTEGER, plates_json TEXT, score_rms REAL, score_json TEXT, verdict TEXT, verdict_note TEXT,
  audit_path TEXT, added_at INTEGER, source TEXT)"""
EXTRA = {"stage": "TEXT", "model_version": "TEXT", "settings_json": "TEXT", "seed": "TEXT", "studio": "TEXT", "action": "TEXT"}
_UUID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


class SeedError(ValueError):
    pass


def default_path() -> Path:
    return Path(os.environ.get("LAMPWAY_SEED_DB") or Path(os.environ.get("LAMPWAY_PROJECT_ROOT") or Path.home() / ".local/share/lampway/projects") / "seeds" / "seeds.sqlite")


def _sha(path) -> Optional[str]:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path and Path(path).exists() else None


class Catalog:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_path()
        self.decisions = self.path.parent / "decisions.jsonl"

    # ------------------------------------------------------------------ storage
    def _con(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute(SCHEMA)
        have = {r[1] for r in c.execute("pragma table_info(seeds)")}
        for col, typ in EXTRA.items():
            if col not in have:
                c.execute(f"ALTER TABLE seeds ADD COLUMN {col} {typ}")
        return c

    def _locked(self):
        class Lock:
            def __enter__(s):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                s.fh = open(str(self.path) + ".lock", "a")
                if fcntl:
                    fcntl.flock(s.fh, fcntl.LOCK_EX)
                return s

            def __exit__(s, *a):
                if fcntl:
                    fcntl.flock(s.fh, fcntl.LOCK_UN)
                s.fh.close()
        return Lock()

    @staticmethod
    def _upsert(c, row: dict) -> None:
        row = {k: v for k, v in row.items() if v is not None}
        row.setdefault("added_at", int(time.time()))
        cols, marks = ",".join(row), ",".join("?" * len(row))
        upd = ",".join(f"{k}=excluded.{k}" for k in row if k != "id")
        c.execute(f"INSERT INTO seeds ({cols}) VALUES ({marks}) ON CONFLICT(id) DO UPDATE SET {upd}", list(row.values()))

    # ------------------------------------------------------------------ ingest
    def ingest_variants(self, json_path, piece: str, plates=None, settings: Optional[dict] = None, model_version: Optional[str] = None) -> dict:
        jp = Path(json_path)
        if not jp.exists():
            raise SeedError(f"{jp} not found: tripo.fetch writes variants.json")
        data = json.loads(jp.read_text())
        rows = data["variants"] if isinstance(data, dict) else data
        plates_json = json.dumps(json.loads(Path(plates).read_text()).get("inputs")) if plates else None
        warnings, k = [], 0
        with self._locked():
            c = self._con()
            n0 = c.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]
            for o in rows:
                url = o.get("url")
                if not url:
                    continue                                                      # no URL: skipped and counted below, never invented
                if "?" in url:
                    warnings.append(f"{Path(o.get('file') or '?').name}: the URL carried a query (Signature): stored without it")
                f = Path(o["file"]) if os.path.isabs(o["file"]) else jp.parent / o["file"]
                k += 1
                self._upsert(c, dict(id=(_UUID.search(url) or [None, None])[1], piece=piece, kind="generation",
                                     topology=o.get("topology_shown") or ("Quad" if url.split("?")[0].endswith(".fbx") else "Triangle"), faces=o.get("faces_shown"),
                                     url=url.split("?")[0], file=str(f.resolve()), sha256=o.get("sha256") or _sha(f), bytes=o.get("bytes"), plates_json=plates_json,
                                     source=str(jp.resolve()), stage="mesh", seed="not_exposed", model_version=model_version,
                                     settings_json=json.dumps(settings) if settings else None))
            c.commit()
            new = c.execute("SELECT COUNT(*) FROM seeds").fetchone()[0] - n0
            c.close()
        return {"ingested": k, "new_rows": new, "skipped_no_url": len(rows) - k, "warnings": warnings}

    def ingest_harvest(self, json_path, piece: str, model_version: Optional[str] = None) -> dict:
        jp = Path(json_path)
        if not jp.exists():
            raise SeedError(f"{jp} not found: tripo_regen harvest writes harvest.json")
        k = 0
        with self._locked():
            c = self._con()
            n0 = c.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]
            for run in json.loads(jp.read_text()):
                ver = {x["id"]: x for x in run.get("history", [])}
                orig = min((x for x in run.get("history", []) if x["type"] != "local_edit"), key=lambda x: x["created_at"], default=None)
                for g in run.get("downloaded", []):
                    if not g.get("file"):
                        continue
                    hv = ver.get(g["id"], {})
                    f = Path(g["file"])
                    if not f.is_absolute():
                        cands = [self.path.parent / f, jp.parent / f.name]
                        f = next((x for x in cands if x.exists()), cands[-1])
                    self._upsert(c, dict(id=g["id"], piece=piece, kind=g["type"], parent_id=(orig["id"] if orig and g["type"] == "local_edit" else None),
                                         created_at=hv.get("created_at"), topology="Quad" if str(g["file"]).endswith(".fbx") else "Triangle", faces=g.get("faces_shown"),
                                         file=str(f.resolve()), sha256=g.get("sha256"), bytes=g.get("bytes"), source=str(jp.resolve()), stage="mesh", seed="not_exposed",
                                         model_version=model_version))
                    k += 1
            c.commit()
            new = c.execute("SELECT COUNT(*) FROM seeds").fetchone()[0] - n0
            c.close()
        return {"ingested": k, "new_rows": new}

    def ingest_scores(self, json_path) -> dict:
        jp = Path(json_path)
        if not jp.exists():
            raise SeedError(f"{jp} not found: proportion_ratios / piece_ratios write the scores")
        data = json.loads(jp.read_text())
        n, miss = 0, []
        with self._locked():
            c = self._con()
            for name, r in data["pieces"].items():
                p = Path(r["file"])
                key = f"{p.parent.name}/{p.stem}"                                        # dir/stem: a bare stem recurs across pieces (variant2)
                hits = c.execute("SELECT id FROM seeds WHERE file LIKE ?", (f"%/{p.parent.name}/{p.stem}.%",)).fetchall()
                if len(hits) != 1:
                    miss.append(f"{name} ({key})")
                    continue
                c.execute("UPDATE seeds SET score_rms=?, score_json=? WHERE id=?", (r["rms_logdev"], json.dumps({k: r.get(k) for k in ("ratios", "dev_pct", "placed")}), hits[0][0]))
                n += 1
            c.commit()
            c.close()
        out = {"scores_attached": n, "unmatched": miss}
        if miss:
            out["hint"] = "run ingest_harvest/ingest_variants for this piece first"
        return out

    # ------------------------------------------------------------------ read
    def list(self, piece: Optional[str] = None, by: str = "score") -> list:
        c = self._con()
        q = "SELECT id,piece,kind,topology,faces,score_rms,verdict FROM seeds" + (" WHERE piece=?" if piece else "")
        q += " ORDER BY score_rms IS NULL, score_rms" if by == "score" else " ORDER BY created_at"
        rows = [{"id": r[0][:8], "piece": r[1], "kind": r[2], "topology": r[3], "topo": r[3], "faces": r[4], "score": r[5], "verdict": r[6]} for r in c.execute(q, (piece,) if piece else ())]
        c.close()
        return rows

    def _one(self, c, prefix: str) -> sqlite3.Row:
        rows = c.execute("SELECT * FROM seeds WHERE id LIKE ?", (prefix + "%",)).fetchall()
        if len(rows) != 1:
            raise SeedError(f"{len(rows)} seeds match {prefix!r}; give a longer id prefix")
        return rows[0]

    def show(self, prefix: str) -> dict:
        c = self._con()
        row = dict(self._one(c, prefix))
        c.close()
        return row

    # ------------------------------------------------------------------ versions (cross-studio passes, crosspass.py)
    def add_version(self, parent_id, piece: str, file: str, studio: str, action: str, root: bool = False, settings: Optional[dict] = None) -> dict:
        """One version of a piece made by ``action`` in ``studio``: a child of ``parent_id`` (``root`` only for a source with no parent). Its sha256 equal to its
        parent's flags a no-op pass. A decisions.jsonl row records it."""
        import uuid
        if not root and not parent_id:
            raise SeedError("lineage requires parent_id: record the source version first")
        f = Path(file)
        if not f.exists():
            raise SeedError(f"{file} not found")
        sha = _sha(f)
        with self._locked():
            c = self._con()
            parent = None
            if parent_id:
                rows = c.execute("SELECT * FROM seeds WHERE id = ?", (parent_id,)).fetchall()
                if len(rows) != 1:
                    c.close()
                    raise SeedError(f"no seed {parent_id!r} to be the parent: record the source version first")
                parent = dict(rows[0])
            row = dict(id=str(uuid.uuid4()), piece=piece, kind="source" if root else "cross_pass", parent_id=parent_id or None, file=str(f.resolve()), sha256=sha,
                       bytes=f.stat().st_size, created_at=int(time.time()), studio=studio, action=action, stage="mesh", seed="not_exposed",
                       settings_json=json.dumps(settings) if settings else None, source=f"studio:{studio}")
            self._upsert(c, row)
            c.commit()
            c.close()
        no_op = bool(parent and parent.get("sha256") == sha)
        self.decisions.parent.mkdir(parents=True, exist_ok=True)
        with self.decisions.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "cross_pass", "t": time.time(), "id": row["id"], "parent_id": parent_id or None, "studio": studio, "action": action,
                                 "sha256": sha, "no_op_pass": no_op}) + "\n")
        return {**row, "no_op_pass": no_op}

    def get(self, seed_id: str) -> Optional[dict]:
        c = self._con()
        rows = c.execute("SELECT * FROM seeds WHERE id = ?", (seed_id,)).fetchall()
        c.close()
        return dict(rows[0]) if rows else None

    # ------------------------------------------------------------------ verdicts
    def verdict(self, prefix: str, verdict: str, note: str = "", audit: str = "", by: str = "agent") -> dict:
        if verdict not in VERDICTS:
            raise SeedError(f"verdict is one of {', '.join(VERDICTS)}")
        if by not in ("captain", "agent", "rule"):
            raise SeedError("by is captain, agent or rule")
        if verdict == "pick" and by != "captain":
            raise SeedError("only the user picks a seed")
        with self._locked():
            c = self._con()
            row = self._one(c, prefix)
            text = (note or "")[:300]
            if by != "captain":
                text = ("proposal by " + by + (": " + text if text else "") + " (not a ruling until the user confirms)")
            c.execute("UPDATE seeds SET verdict=?, verdict_note=?, audit_path=? WHERE id=?", (verdict, text, audit or None, row["id"]))
            c.commit()
            c.close()
            self.decisions.parent.mkdir(parents=True, exist_ok=True)
            with self.decisions.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"kind": "decision", "t": time.time(), "question": "seed_verdict", "options": list(VERDICTS), "answer": verdict, "decider": by,
                                     "how": "captain" if by == "captain" else "proposal", "note": text,
                                     "descriptor": {"id": row["id"], "piece": row["piece"], "faces": row["faces"], "score": row["score_rms"], "stage": row["stage"]}}) + "\n")
        return {"id": row["id"][:8], "verdict": verdict, "by": by}
