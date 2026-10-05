<!-- SPDX-FileCopyrightText: 2026 Keigyoku -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Resource audit (2026-10-05)

Rule applied: audit licence and provenance before integrating, read what the code touches (files, network), keep provenance,
build proven algorithmic code first with a model/studio slot behind it. **No third-party code was copied into Lampway in this
pass**; every row below is either an idea re-implemented from first principles on Blender's own API, a tool to point the owner at,
or a deliberate no.

| Resource | Licence (as read) | What it is | Decision |
|---|---|---|---|
| Robust Weight Transfer (sentfromspacevr) | GPL-2.0-or-later (file headers read) | Weight transfer by robust Laplacian inpainting; needs scipy and robust_laplacian | Not vendored: Lampway's Python has no scipy. `bind_to_armature(mode="transfer")` uses Blender's Data Transfer plus a proximity fill, measured by `pose_test`. Compatible if scipy is ever bundled. |
| TexTools-Blender (franMarz, from renderhjs) | GPL-3.0-or-later (LICENSE.txt read) | UV/texture-bake add-on, last push 2024-12; declares Blender 2.80+ | Not vendored. The UV solvers in `uv_unwrap` are Blender's own; island align/straighten ideas recorded as a follow-up. |
| NifTools Blender add-on and the unofficial 5.1 compatibility fork | BSD-3-Clause upstream (LICENSE.rst read); the fork has no licence file (GitHub: NOASSERTION) | NIF game-format import/export | Not integrated: out of scope for the Mixar feature set; an unlicensed fork is not redistributable. |
| alpaca3d.app | Proprietary Windows application (offline installer, Store build) | Retopo / UV / bake desktop tool | Reference only. Cannot be bundled or driven from Blender here; its three labs match `retopo`, `uv_unwrap` and the planned bake. |
| AutoRemesher 1.1 (Jeremy Hu) | MIT (per 3dxdev page) | Native quad remesher CLI, anisotropy option | Candidate engine for `retopo`: MIT is compatible. It is a native binary, so it needs a build or a release asset the owner approves; the `retopo` tool keeps QuadriFlow until then. |
| UniV (Oxicid) | GPL-3.0-or-later (extensions.blender.org page read) | UV toolkit | Installable by the owner from the Extensions platform; not copied. |
| Mio3 UV (mio3io) | free (licence not stated on the page) | UV straighten / gridify | Not copied: licence unconfirmed. |
| img2mat_pro (stevewarner) | GPL-3.0-or-later | Image palette to materials with Pantone callouts | Compatible; not needed by any Mixar feature. Noted for the game colour work. |
| Auto-Rig Pro alternatives page | n/a (article) | Rigify, CloudRig, BlenRig compared | Informational; `auto_rig` stays landmark-based on the UE skeleton. |
| kimodo-cpp / Kimodo Blender Bridge | open source; model weights gated behind Hugging Face licences | Text-to-motion | Not built: it needs a GPU-class model (about 17 GB VRAM per the page), which the owner's rule routes to his studio subscriptions; I did not check whether Tripo, Meshy or Hi3D offer text-to-motion. |
| Stefan's LLM wiki workflows | Notes (no code) | Checklists | Built as Client tools: `mesh_prep`, `asset_acceptance`, `rig_armor`; local texture repair is `repair_texture`. Not built: animation-cascadeur-motion, animation-facial-avatar, the coding-* and printing-* workflows, subscription-material-experiment (they are about other tools or about spending credits). |

Network and files read of each audited code base: none was executed. The pages and sources were fetched read-only for the audit;
no Mixar service was contacted.
