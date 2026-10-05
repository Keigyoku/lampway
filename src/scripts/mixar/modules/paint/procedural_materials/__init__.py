# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Local procedural-material library for the paint module.

Upstream's package of this name is withheld from the published source (it was gitignored), and the
paint UI, the layer helpers and the agent tools all import it. This replacement is small and real:

* ``material_registry`` - the registry the rest of paint reads (id, name, category, script, node group);
* ``matgen_persistence`` - the user's own materials, kept in the user data directory;
* ``matgen_queue`` - AI material generation, which needs a generation backend: it says so.

There is no hosted catalogue: the library is whatever the user (or an agent script) registered.
"""
