# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault editor's pump (specs/asset_library/asset_ui_editor.md section 6.3): HTTP runs off the main thread; answers are handed back on the main thread's tick, which is the only
place the view-model changes. A pure test: the worker is a list the test drains."""

from mixar.modules.asset_library.core.pump import Pump
from mixar.modules.asset_library.core.viewmodel import VaultViewModel


class Clock:
    t = 50.0

    def __call__(self):
        return self.t


class FakeClient:
    def __init__(self):
        self.calls = []

    def query(self, payload):
        self.calls.append(("query", payload.get("text")))
        if payload.get("text") == "down":
            raise ConnectionError("the server could not be reached: refused")
        return {"items": [{"id": "a", "kind": "mesh", "name": "A"}], "total": 1, "facets": {}, "cursor": None}

    def get(self, asset_id):
        self.calls.append(("get", asset_id))
        return {"id": asset_id, "name": asset_id.upper()}


def make():
    jobs = []
    vm = VaultViewModel(clock=Clock())
    client = FakeClient()
    pump = Pump(vm, client, spawn=jobs.append)
    return vm, client, pump, jobs


def drain(jobs):
    while jobs:
        jobs.pop(0)()


def test_a_due_query_runs_off_the_main_thread_and_lands_on_the_next_tick():
    vm, client, pump, jobs = make()
    vm.type_text("greaves"); vm.submit()
    assert pump.tick() is False and len(jobs) == 1 and client.calls == []
    drain(jobs)
    assert vm.items == [], "the answer waits for the main thread"
    assert pump.tick() is True and [i["id"] for i in vm.items] == ["a"]


def test_the_active_assets_detail_follows_and_a_failure_goes_offline():
    vm, client, pump, jobs = make()
    vm.submit(); pump.tick(); drain(jobs); pump.tick()
    vm.select("a")
    pump.tick(); drain(jobs); pump.tick()
    assert vm.detail == {"id": "a", "name": "A"} and ("get", "a") in client.calls
    vm.type_text("down"); vm.submit()
    pump.tick(); drain(jobs)
    assert pump.tick() is True and vm.status == "offline" and "could not be reached" in vm.message


def test_a_tick_with_nothing_due_spawns_nothing():
    vm, client, pump, jobs = make()
    assert pump.tick() is False and jobs == []


def test_an_operators_call_runs_off_thread_and_its_answer_lands_on_the_tick():
    vm, client, pump, jobs = make()
    got = []
    pump.later(lambda: {"items": [{"id": "z"}]}, lambda ok, value: got.append((ok, value)))
    pump.later(lambda: 1 / 0, lambda ok, value: got.append((ok, value)))
    assert got == [] and len(jobs) == 2
    drain(jobs)
    assert got == []
    assert pump.tick() is True
    assert got[0] == (True, {"items": [{"id": "z"}]}) and got[1][0] is False and "division" in got[1][1]


def test_the_active_assets_view_products_arrive_and_load_the_flipbook():
    vm, client, pump, jobs = make()
    client.views = lambda aid: (client.calls.append(("views", aid)), {"turntable": [f"/t{i}.jpg" for i in range(36)], "ball": None, "overlay": None, "sheet": None,
                                                                       "thumb": None, "proxy": ["/p0.jpg", "/p1.jpg"], "strip": None})[1]
    vm.submit(); pump.tick(); drain(jobs); pump.tick()
    vm.select("a")
    pump.tick(); drain(jobs); pump.tick()
    assert ("views", "a") in client.calls and vm.products["turntable"][0] == "/t0.jpg"
    assert vm.flipbook.frames[:2] == ["/t0.jpg", "/t1.jpg"]
    vm.set_view("video")
    assert vm.flipbook.frames == ["/p0.jpg", "/p1.jpg"] and vm.view_mode == "video"
    vm.set_view("nonsense")
    assert vm.view_mode == "video"
