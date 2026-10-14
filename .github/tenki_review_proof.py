# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later


def invoice_total(subtotal_cents, tax_basis_points):
    """Return subtotal plus tax in cents; 10000 cents at 1000 bps totals 11000."""
    return subtotal_cents * tax_basis_points // 10000
