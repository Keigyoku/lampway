"""The generation job-service registry: which of the Client's job types this server can run, with its catalog row and its spend gate. A backend registers
once (``register``); the catalog, the submit path and the ``lampway_job_services`` tool all read the same registry, so a service that is not registered is
neither advertised nor runnable (the Client's own kill switch for a tab).

``spend=True`` services never start until the captain confirms the price in the Studios panel (the same approvals store the Studios use); registering one
without ``confirm_price`` is refused, so there is no spend service without a price to show him."""

from dataclasses import dataclass
from typing import Callable, Optional

# The job types the Mixar client sends (audit/protocol.json job_services: 18 entries covering 21 keys).
WIRE_KEYS = ("image_gen", "model_3d", "image_to_3d", "hunyuan_rapid", "retopology", "retopology_tripo", "hunyuan_uv", "hunyuan_part", "tripo_rig",
             "tripo_retarget", "tripo_segment", "tripo_smart_segment", "mesh_segment", "pbr_gen", "scene_reconstruction", "scene_gen",
             "scene_gen_exp_labels", "world_labs", "video_gen", "video_upscale", "depth_to_image")


@dataclass
class Service:
    key: str
    backend: Callable
    row: dict
    spend: bool = False
    confirm_price: Optional[Callable] = None
    backend_name: str = ""


class ServiceRegistry:
    def __init__(self):
        self._items: dict[str, Service] = {}

    def register(self, key: str, backend: Callable, catalog_row: dict, spend: bool = False, confirm_price: Optional[Callable] = None, backend_name: str = "") -> None:
        if key not in WIRE_KEYS:
            raise ValueError(f"service {key!r} is not a Mixar client job type; the client sends: {', '.join(WIRE_KEYS)}")
        if spend and confirm_price is None:
            raise ValueError(f"service {key!r} spends: register it with confirm_price(payload) -> the price the captain confirms")
        if not isinstance(catalog_row, dict) or not catalog_row.get("models"):
            raise ValueError(f"service {key!r} needs a catalog row with at least one model")
        self._items[key] = Service(key, backend, catalog_row, bool(spend), confirm_price, backend_name)

    def unregister(self, key: str) -> None:
        self._items.pop(key, None)

    def get(self, key: str) -> Optional[Service]:
        return self._items.get(key)

    def keys(self) -> list:
        return sorted(self._items)

    def capabilities(self, first_sort: int = 10) -> list:
        """Catalog capabilities for the registered services (the Client reads capabilities[].services[]; an empty list hides its tabs)."""
        out = []
        for i, key in enumerate(self.keys()):
            row = self._items[key].row
            out.append({"key": key, "label": row.get("label") or key, "sort_order": row.get("sort_order", first_sort + i),
                        "services": [{"key": key, "surface": row.get("surface", "moodboard"), "sort_order": 1, "models": row["models"],
                                      **({"input_spec": row["input_spec"]} if row.get("input_spec") else {})}]})
        return out
