# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Studio drivers: browser automation on the owner's own logged-in studio accounts (Tripo Studio today).

SERVER-side only, never reachable from the agent's Blender scripts. They can spend credits, so every command that changes
anything in a studio first calls ``guard.require_armed``: unless ``LAMPWAY_STUDIO_ARMED=1`` is set by the owner for that run,
it refuses before any browser is touched. Invariants kept from the shelf (each is a header comment in its tool): settings
are set and read back right before every generation and a mismatch refuses; maximum value per generation (4 images, 4K, 4
meshes at the topology's top polycount); a price that is not the expected one refuses; Edit Mesh runs on originals only and
other tools on saved copies; never overwrite a record; no signed URL is ever stored.
"""
