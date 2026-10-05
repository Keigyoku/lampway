# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""AI material generation. Upstream sent a prompt to a hosted generation service through the job queue.
Lampway's server (v0) has no generation backend, so asking for one raises ``MatgenUnavailable`` with that
sentence, which the paint operators already show as an error report."""


class MatgenUnavailable(RuntimeError):
    pass


def enqueue_matgen_job(prompt: str = "", **_kwargs):
    raise MatgenUnavailable(
        "Material generation is unavailable: this server has no generation backend. "
        "Register a material script with material_registry.register_material, or add one in the paint library."
    )
