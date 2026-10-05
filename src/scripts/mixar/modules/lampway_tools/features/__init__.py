# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Mixar-docs features, rebuilt on proven algorithmic code with a studio slot behind the same tool interface.

Every feature is a function ``feature(object, ..., engine="algorithmic")`` returning a dict (``api.tool`` adds ``ok``). The
algorithmic engine is the default and is real code (Blender's QuadriFlow, angle-based unwrap, region growing, ...), measured
by a report. ``engine="studio:<name>"`` is the slot for the owner's studio subscriptions (Tripo, Meshy, Hi3D): it NEVER
clicks; it answers with the action it would take and the price, so the owner approves the spend first, and the server's
``studio_*`` tools run it (dry run by default, the arming guard on every credit-spending step).
"""
