# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault editor's view-model (specs/asset_library/asset_ui_editor.md section 6.2): pure Python, no bpy, so every rule of the browser is testable without Blender.

It owns the query state (text, kind, facet terms, sort), the debounce (typing waits 250 ms; Enter sends at once), the request tokens (an answer for an older request is dropped,
so a slow page never overwrites a newer one), the paging cursor stack, the selection (click, ctrl toggle, shift range), the offline state and the empty-state text. The panels
read it; the worker thread sends what ``due()`` hands out and gives the answer back through ``receive`` / ``fail`` on the main thread."""

from collections import OrderedDict

from .. import constants as K


class VaultViewModel:
    def __init__(self, clock, page_size: int = K.PAGE, debounce: float = K.DEBOUNCE_S):
        self.clock, self.page_size, self.debounce = clock, page_size, debounce
        self.text, self.kind, self.sort = "", None, None
        self.terms: dict = {}
        self.items: list = []
        self.total = 0
        self.facets: dict = {}
        self.status, self.message = "idle", ""
        self.selected: list = []
        self.active = None
        self._anchor = None
        self._cursors = [None]                # cursor of each page shown so far; the last is the page asked for
        self._next_cursor = None
        self._token = 0
        self._pending_at = None               # when the debounced request is due (None: nothing pending)
        self.detail = None                    # the active asset's full record
        self.banner = ""                      # what the list shows when it is not the query ("Like <name>")
        self.compare: list = []               # at most two ids for the compare view
        self.importing: dict = {"state": "idle"}   # Initial import: idle -> scanning -> preview -> importing -> done (the user's confirm moves preview on)
        self._detail_sent = None              # the id whose record was last asked for

    # ---- the query
    def type_text(self, text: str) -> None:
        self.text = text
        self._restart(self.clock() + self.debounce)

    def submit(self) -> None:
        self._restart(self.clock())

    def set_kind(self, kind) -> None:
        self.kind = kind
        self._restart(self.clock())

    def set_sort(self, by) -> None:
        self.sort = by
        self._restart(self.clock())

    def toggle_facet(self, facet: str, label: str) -> None:
        chosen = self.terms.setdefault(facet, [])
        if label in chosen:
            chosen.remove(label)
        else:
            chosen.append(label)
        if not chosen:
            del self.terms[facet]
        self._restart(self.clock())

    def _restart(self, at: float) -> None:
        self._cursors = [None]
        self._pending_at = at

    def payload(self) -> dict:
        p = {"limit": self.page_size, "facets": list(K.FACETS), "include": ["thumb", "tags"]}
        if self.text.strip():
            p["text"] = self.text.strip()
        if self.kind:
            p["kinds"] = [self.kind]
        if self.terms:
            p["terms"] = {f: list(v) for f, v in self.terms.items()}
        if self.sort:
            p["sort"] = [{"by": self.sort}]
        if self._cursors[-1]:
            p["cursor"] = self._cursors[-1]
        return p

    def due(self):
        """The request to send now ({token, payload}), or None while the debounce runs or nothing changed."""
        if self._pending_at is None or self.clock() < self._pending_at:
            return None
        self._pending_at = None
        self._token += 1
        self.status = "loading"
        return {"token": self._token, "payload": self.payload()}

    def receive(self, token: int, page: dict) -> bool:
        if token != self._token:
            return False
        self.items, self.total, self.facets = list(page.get("items") or []), int(page.get("total") or 0), dict(page.get("facets") or {})
        self._next_cursor = page.get("cursor")
        self.status, self.message, self.banner = "ready", "", ""
        visible = {i["id"] for i in self.items}
        self.selected = [s for s in self.selected if s in visible]
        if self.active not in visible:
            self.active = self.selected[-1] if self.selected else None
        return True

    def fail(self, token: int, message: str) -> bool:
        if token != self._token:
            return False
        self.status, self.message = ("offline" if "could not be reached" in message or "not signed in" in message else "error"), message
        return True

    # ---- paging
    @property
    def page_index(self) -> int:
        return len(self._cursors) - 1

    @property
    def can_next(self) -> bool:
        return bool(self._next_cursor)

    @property
    def can_prev(self) -> bool:
        return len(self._cursors) > 1

    def next_page(self) -> None:
        if self._next_cursor:
            self._cursors.append(self._next_cursor)
            self._pending_at = self.clock()

    def prev_page(self) -> None:
        if len(self._cursors) > 1:
            self._cursors.pop()
            self._pending_at = self.clock()

    # ---- selection
    def select(self, asset_id: str, mode: str = "set") -> None:
        order = [i["id"] for i in self.items]
        if mode == "toggle":
            if asset_id in self.selected:
                self.selected.remove(asset_id)
                self.active = self.selected[-1] if self.selected else None
            else:
                self.selected.append(asset_id)
                self.active = asset_id
            self._anchor = asset_id
            return
        if mode == "range" and self._anchor in order and asset_id in order:
            a, b = sorted((order.index(self._anchor), order.index(asset_id)))
            self.selected = order[a:b + 1]
            self.active = asset_id
            return
        self.selected, self.active, self._anchor = [asset_id], asset_id, asset_id

    # ---- Initial import: a preview first, the import only on the user's confirm
    def import_scanning(self, paths) -> None:
        self.importing = {"state": "scanning", "paths": list(paths)}

    def import_previewed(self, scan: dict) -> None:
        self.importing = {"state": "preview", "scan_id": scan["scan_id"], "report": scan["report"]}

    def import_confirmable(self):
        return self.importing.get("scan_id") if self.importing["state"] == "preview" else None

    def import_started(self) -> None:
        self.importing = {**self.importing, "state": "importing"}

    def import_done(self, result: dict) -> None:
        self.importing = {"state": "done", "report": result["report"]}
        self._restart(self.clock())

    def import_failed(self, message: str) -> None:
        self.importing = {"state": "failed", "message": message}

    def import_summary(self) -> str:
        st, rep = self.importing["state"], self.importing.get("report") or {}
        if st == "preview":
            kinds = sorted((rep.get("by_kind") or {}).items(), key=lambda kv: (-kv[1], kv[0]))
            left = len(rep.get("unknown") or []) + len(rep.get("skipped") or []) + len(rep.get("failed") or [])
            notes = [f"{rep['deduped']} already in the Vault" if rep.get("deduped") else "", f"{left} not imported" if left else ""]
            notes = [n for n in notes if n]
            return f"{sum(n for _, n in kinds)} files: " + ", ".join(f"{n} {k}" for k, n in kinds) + (f" ({', '.join(notes)})" if notes else "")
        if st == "done":
            return f"Imported {rep.get('new_assets', 0)} new assets ({rep.get('deduped', 0)} duplicates, {len(rep.get('failed') or [])} failed)"
        if st == "scanning":
            return f"Reading {len(self.importing['paths'])} folder(s)"
        if st == "importing":
            return "Importing"
        if st == "failed":
            return self.importing["message"]
        return ""

    # ---- find like this, compare
    def show_similar(self, name: str, items: list) -> None:
        self.items, self.total, self._next_cursor = list(items), len(items), None
        self.banner, self.status = f"Like {name}", "ready"

    def compare_add(self, asset_id: str) -> None:
        if asset_id not in self.compare:
            self.compare = (self.compare + [asset_id])[-2:]

    # ---- the detail column
    def detail_due(self):
        """The id whose record to fetch now (the active asset, once), or None."""
        if self.active is None or self.active == self._detail_sent:
            return None
        self._detail_sent = self.active
        return self.active

    def receive_detail(self, asset_id: str, record: dict) -> bool:
        if asset_id != self.active:
            return False
        self.detail = record
        return True

    def refresh_detail(self) -> None:
        self._detail_sent = None

    # ---- what the body says when there is nothing to show
    def empty_text(self) -> str:
        if self.status == "offline":
            return f"Library server not reachable: {self.message}"
        if self.items:
            return ""
        filters = [f"{f}: {', '.join(v)}" for f, v in self.terms.items()] + ([f"kind: {self.kind}"] if self.kind else [])
        if filters:
            return f"0 results: remove the filter {filters[0]}"
        if self.text.strip():
            return f"0 results for {self.text.strip()!r}"
        return "The Vault is empty: Initial import adds your folders"


class ThumbLRU:
    """Thumbnail handles by asset id, at most ``capacity``; ``put`` returns the keys it evicted (their previews are freed by the caller)."""

    def __init__(self, capacity: int = K.THUMB_LRU):
        self.capacity = capacity
        self._d: OrderedDict = OrderedDict()

    def get(self, key):
        if key not in self._d:
            return None
        self._d.move_to_end(key)
        return self._d[key]

    def put(self, key, value) -> list:
        self._d[key] = value
        self._d.move_to_end(key)
        evicted = []
        while len(self._d) > self.capacity:
            evicted.append(self._d.popitem(last=False)[0])
        return evicted

    def keys(self):
        return list(self._d.keys())
