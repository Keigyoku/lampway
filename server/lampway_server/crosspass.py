"""studio_cross_pass (specs/generation/studio_cross_pass.md): a mesh one Studio made, uploaded into another Studio's MESH-TAKING action, through that Studio's
own plan and the user's confirm (one price card per step), and the result recorded in the ONE seed catalogue as a version with its parent.

Only actions that take an uploaded mesh are routes (``CROSS_ACTIONS``: the REST actions whose request carries a ``model`` file); a Tripo Studio browser action
has no upload verb in its driver: never assume a Tripo affordance exists elsewhere. A route needs ``parent_id`` (record the source version first:
``seed_catalog`` or ``record`` with root). The proportion score of a result is the proportion tools' (lampway_mesh_to_npz + lampway_proportion_ratios, then
seed_catalog ingest_scores); a result whose bytes equal its parent's is flagged a no-op pass."""

from .seeds import Catalog, SeedError

CROSS_ACTIONS = ("meshy.remesh", "meshy.uv_unwrap", "meshy.retexture", "hyper3d.texture_only", "hyper3d.bang", "hi3d.texture_only", "hi3d.split",
                 "tripo.rest.texture", "tripo.rest.decimate")
STUDIOS = ("tripo", "meshy", "hi3d", "hyper3d")


class CrossPassError(ValueError):
    pass


def lineage(cat: Catalog, seed_id: str) -> list:
    """The chain from the first source to ``seed_id`` (parents first)."""
    chain, seen, cur = [], set(), cat.get(seed_id)
    if cur is None:
        raise CrossPassError(f"no seed {seed_id!r}")
    while cur is not None and cur["id"] not in seen:
        seen.add(cur["id"])
        chain.append({k: cur.get(k) for k in ("id", "parent_id", "piece", "kind", "studio", "action", "sha256", "file")})
        cur = cat.get(cur["parent_id"]) if cur.get("parent_id") else None
    return list(reversed(chain))


class CrossPass:
    def __init__(self, cat: Catalog, studio):
        self.cat = cat
        self.studio = studio

    async def plan(self, mesh: str, from_studio: str, to_studio: str, action: str, args: dict, parent_id: str, by: str) -> dict:
        if from_studio not in STUDIOS or to_studio not in STUDIOS:
            raise CrossPassError(f"from_studio and to_studio are among {', '.join(STUDIOS)}")
        if not parent_id:
            raise CrossPassError("lineage requires parent_id: record the source version first (seed_catalog, or record with root)")
        if self.cat.get(parent_id) is None:
            raise CrossPassError(f"no seed {parent_id!r} to be the parent: record the source version first")
        if not action.startswith(to_studio + "."):
            raise CrossPassError(f"{action} is not a {to_studio} action")
        if action not in CROSS_ACTIONS:
            if to_studio == "tripo" and not action.startswith("tripo.rest."):
                raise CrossPassError(f"{action} is a Tripo Studio browser action: its driver has no upload verb, so an outside mesh cannot reach it; never assume a "
                                     f"Tripo affordance exists elsewhere (the mesh-taking Tripo routes: tripo.rest.texture, tripo.rest.decimate)")
            raise CrossPassError(f"{action} takes no uploaded mesh; the cross-pass routes are: {', '.join(CROSS_ACTIONS)}")
        path = self.studio.jail(mesh)
        plan = await self.studio.plan(action, {**(args or {}), "model": path}, by)
        return {"plan": plan, "route": f"{from_studio} -> {to_studio} ({action})",
                "record_with": {"verb": "record", "parent_id": parent_id, "studio": to_studio, "action": action,
                                "how": "after the confirmed job finishes, record its result file as the child version"},
                "note": "the upload leaves the machine to the destination studio; use a saved copy as the source, never the original"}

    def record(self, parent_id: str, piece: str, file: str, studio: str, action: str, root: bool = False) -> dict:
        try:
            return self.cat.add_version(parent_id, piece, file, studio, action, root=root)
        except SeedError as exc:
            raise CrossPassError(str(exc)) from None
