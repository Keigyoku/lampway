#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
# THE full test run (server + whole client suite) against the known-red baseline; see scripts/lampway/test_all.py.
exec "${LAMPWAY_TEST_PYTHON:-python3}" "$(dirname "$0")/test_all.py" "$@"
