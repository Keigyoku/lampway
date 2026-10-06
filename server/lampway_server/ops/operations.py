"""Operation records: one request id identifies one request. A repeated id returns the recorded (or in-flight) result and never runs the tool again; a record still ``running`` after a restart
becomes ``interrupted`` and is never silently re-run. Append-only JSON lines, the last 150 kept in memory."""
import asyncio
import json
import os
import time
from pathlib import Path

INTERRUPTED = "The coordinator stopped before this operation was confirmed. Inspect the target chat before retrying."
KEEP = 150
ROTATE_BYTES = 10 * 1024 * 1024


class OperationError(ValueError):
    pass


class Operations:
    def __init__(self, path):
        self.path = Path(path)
        self._recent = {}
        self._inflight = {}
        self._load()

    def _load(self):
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                self._recent[r["request_id"]] = r
            while len(self._recent) > KEEP:
                self._recent.pop(next(iter(self._recent)))

    def _append(self, rec):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size > ROTATE_BYTES:
            os.replace(self.path, self.path.with_suffix(".jsonl.1"))
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        self._recent[rec["request_id"]] = rec

    def get(self, request_id):
        return self._recent.get(request_id)

    def recover(self):
        for rid, rec in list(self._recent.items()):
            if rec.get("status") == "running":
                self._append({**rec, "status": "interrupted", "text": INTERRUPTED, "at": time.time()})

    async def run(self, request_id, request_text, route, fn):
        """fn() -> {"text", "result", optional "status"}; returns the record."""
        if not request_id:
            raise OperationError("a request_id is required: one per user request, a retry reuses it")
        if request_id in self._recent:
            return self._recent[request_id]
        if request_id in self._inflight:
            return await self._inflight[request_id]

        async def go():
            t0 = time.monotonic()
            self._append({"request_id": request_id, "status": "running", "route": route, "text": "", "result": None, "at": time.time(), "request_text": str(request_text)[:300]})
            try:
                out = fn()
                if asyncio.iscoroutine(out):
                    out = await out
                out = out or {}
                rec = {"request_id": request_id, "status": out.get("status", "completed"), "route": route, "text": out.get("text", ""), "result": out.get("result"),
                       "at": time.time(), "duration_ms": int((time.monotonic() - t0) * 1000)}
            except Exception as exc:  # noqa: BLE001 - a failed tool is a recorded failure, never a crash of the agent loop
                rec = {"request_id": request_id, "status": "failed", "route": route, "text": f"{exc}", "result": None, "at": time.time(), "duration_ms": int((time.monotonic() - t0) * 1000)}
            self._append(rec)
            return rec
        task = asyncio.get_running_loop().create_task(go())
        self._inflight[request_id] = task
        try:
            return await task
        finally:
            self._inflight.pop(request_id, None)
