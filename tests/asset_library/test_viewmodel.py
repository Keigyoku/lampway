# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault editor's view-model (specs/asset_library/asset_ui_editor.md section 6.2, tests section 10.2): pure Python, no bpy. Query state, debounce, request tokens that
discard stale answers, paging, selection, facet toggles, offline transitions, the thumbnail LRU."""

from mixar.modules.asset_library.core.viewmodel import ThumbLRU, VaultViewModel


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def page(ids, total=None, facets=None, cursor=None):
    return {"items": [{"id": i, "kind": "mesh", "name": i} for i in ids], "total": len(ids) if total is None else total, "facets": facets or {}, "cursor": cursor}


def test_ten_keystrokes_coalesce_into_one_request_after_the_debounce():
    clock = Clock()
    vm = VaultViewModel(clock=clock)
    sent = []
    for i, ch in enumerate("gold embro"):
        clock.t += 0.05
        vm.type_text("gold embro"[: i + 1])
        req = vm.due()
        if req:
            sent.append(req)
    assert sent == []
    clock.t += 0.249
    assert vm.due() is None
    clock.t += 0.002
    req = vm.due()
    assert req is not None and req["payload"]["text"] == "gold embro" and vm.due() is None


def test_enter_sends_at_once():
    vm = VaultViewModel(clock=Clock())
    vm.type_text("greaves")
    vm.submit()
    req = vm.due()
    assert req and req["payload"]["text"] == "greaves"


def test_a_stale_answer_is_discarded_and_the_latest_one_lands():
    clock = Clock()
    vm = VaultViewModel(clock=clock)
    vm.type_text("bro"); vm.submit(); old = vm.due()
    vm.type_text("bronze"); vm.submit(); new = vm.due()
    assert vm.receive(new["token"], page(["b1", "b2"])) is True
    assert vm.receive(old["token"], page(["x"])) is False
    assert [i["id"] for i in vm.items] == ["b1", "b2"] and vm.status == "ready"


def test_the_payload_carries_kinds_facets_sort_and_the_page_size():
    vm = VaultViewModel(clock=Clock())
    vm.set_kind("material")
    vm.toggle_facet("material_role", "metal")
    vm.toggle_facet("material_role", "leather")
    vm.toggle_facet("material_role", "leather")
    vm.set_sort("rating")
    vm.submit()
    p = vm.due()["payload"]
    assert p["kinds"] == ["material"] and p["terms"] == {"material_role": ["metal"]} and p["sort"] == [{"by": "rating"}] and p["limit"] == 96
    assert set(p["facets"]) >= {"kind", "material_role", "piece_type", "rating"}
    vm.set_kind(None)
    vm.submit()
    assert "kinds" not in vm.due()["payload"]


def test_paging_follows_the_cursor_and_back_returns_to_the_page_before():
    vm = VaultViewModel(clock=Clock())
    vm.submit(); r = vm.due()
    vm.receive(r["token"], page([f"a{i}" for i in range(96)], total=200, cursor="c1"))
    assert vm.can_next and not vm.can_prev
    vm.next_page(); r = vm.due()
    assert r["payload"]["cursor"] == "c1"
    vm.receive(r["token"], page([f"b{i}" for i in range(96)], total=200, cursor="c2"))
    assert vm.page_index == 1 and vm.can_prev
    vm.prev_page(); r = vm.due()
    assert "cursor" not in r["payload"] and vm.page_index == 0
    vm.type_text("x"); vm.submit(); r = vm.due()
    assert "cursor" not in r["payload"], "a new query starts at the first page"


def test_selection_click_toggle_and_range():
    vm = VaultViewModel(clock=Clock())
    vm.submit(); r = vm.due()
    vm.receive(r["token"], page(["a", "b", "c", "d", "e"]))
    vm.select("b")
    assert vm.selected == ["b"] and vm.active == "b"
    vm.select("d", mode="range")
    assert vm.selected == ["b", "c", "d"]
    vm.select("c", mode="toggle")
    assert vm.selected == ["b", "d"]
    vm.select("a", mode="toggle")
    assert vm.selected == ["b", "d", "a"] and vm.active == "a"
    vm.select("e")
    assert vm.selected == ["e"]


def test_offline_and_back():
    vm = VaultViewModel(clock=Clock())
    vm.submit(); r = vm.due()
    vm.fail(r["token"], "the server could not be reached: connection refused")
    assert vm.status == "offline" and "could not be reached" in vm.message
    vm.submit(); r = vm.due()
    assert vm.status == "loading"
    vm.receive(r["token"], page([]))
    assert vm.status == "ready" and vm.items == []


def test_the_empty_state_names_the_filter_to_remove():
    vm = VaultViewModel(clock=Clock())
    vm.toggle_facet("piece_type", "greaves")
    vm.submit(); r = vm.due()
    vm.receive(r["token"], page([], facets={"piece_type": [{"value": "greaves", "count": 0}]}))
    assert vm.empty_text() == "0 results: remove the filter piece_type: greaves"
    vm.toggle_facet("piece_type", "greaves")
    vm.submit(); r = vm.due()
    vm.receive(r["token"], page([]))
    assert vm.empty_text() == "The Vault is empty: Initial import adds your folders"


def test_the_thumbnail_lru_evicts_the_least_recently_used():
    lru = ThumbLRU(capacity=3)
    for k in "abc":
        lru.put(k, k.upper())
    assert lru.get("a") == "A"
    evicted = lru.put("d", "D")
    assert evicted == ["b"] and lru.get("b") is None and set(lru.keys()) == {"a", "c", "d"}


def test_the_detail_of_the_active_asset_is_fetched_once_and_a_stale_detail_is_dropped():
    vm = VaultViewModel(clock=Clock())
    vm.submit(); r = vm.due()
    vm.receive(r["token"], page(["a", "b"]))
    assert vm.detail_due() is None
    vm.select("a")
    assert vm.detail_due() == "a" and vm.detail_due() is None
    vm.select("b")
    assert vm.detail_due() == "b"
    assert vm.receive_detail("a", {"id": "a"}) is False and vm.detail is None
    assert vm.receive_detail("b", {"id": "b", "name": "B"}) is True and vm.detail["name"] == "B"
    vm.select("b")
    assert vm.detail_due() is None, "the shown detail is not fetched again"
    vm.refresh_detail()
    assert vm.detail_due() == "b"


def test_find_like_this_shows_the_similar_list_until_the_next_search():
    vm = VaultViewModel(clock=Clock())
    vm.submit(); r = vm.due()
    vm.receive(r["token"], page(["a", "b"]))
    vm.show_similar("Bronze greaves", [{"id": "s1", "name": "S1", "score": 0.9}])
    assert [i["id"] for i in vm.items] == ["s1"] and vm.banner == "Like Bronze greaves" and vm.total == 1
    vm.submit(); r = vm.due()
    vm.receive(r["token"], page(["a"]))
    assert vm.banner == ""


def test_compare_keeps_the_last_two():
    vm = VaultViewModel(clock=Clock())
    vm.compare_add("a"); vm.compare_add("b")
    assert vm.compare == ["a", "b"]
    vm.compare_add("c")
    assert vm.compare == ["b", "c"]
    vm.compare_add("c")
    assert vm.compare == ["b", "c"]


def test_initial_import_previews_first_and_imports_only_on_the_users_confirm():
    vm = VaultViewModel(clock=Clock())
    assert vm.importing["state"] == "idle"
    vm.import_scanning(["/home/u/Armour", "/home/u/Plates"])
    assert vm.importing == {"state": "scanning", "paths": ["/home/u/Armour", "/home/u/Plates"]}
    vm.import_previewed({"scan_id": "s1", "report": {"by_kind": {"mesh": 5, "image": 12}, "deduped": 2, "new_assets": 15, "seen": 19, "unknown": [{"path": "x"}], "skipped": [{"path": "y"}]}})
    assert vm.importing["state"] == "preview" and vm.import_summary() == "17 files: 12 image, 5 mesh (2 already in the Vault, 2 not imported)"
    assert vm.import_confirmable() == "s1"
    vm.import_done({"report": {"new_assets": 15, "deduped": 2, "failed": []}})
    assert vm.importing["state"] == "done" and vm.import_summary() == "Imported 15 new assets (2 duplicates, 0 failed)"
    assert vm.due() is not None, "the page refreshes after an import"
    assert vm.import_confirmable() is None
