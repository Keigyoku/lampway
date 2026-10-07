# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon 19: R04 bytes must not depend on BLAS's near-unit dot rounding."""
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GOLDENS = ROOT / "docs/canon/goldens"


def generated_r04(core):
    code = "import json,gen_rig_goldens as G; print(json.dumps(G.r9(G.r04()),sort_keys=True))"
    env = {**os.environ, "OPENBLAS_CORETYPE": core, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.check_output([sys.executable, "-c", code], cwd=GOLDENS, env=env, text=True)


def test_r04_is_byte_identical_across_blas_kernels():
    # Prescott selects the non-FMA kernel that reproduced CI's zero vs 8.54e-7
    # along-angle discrepancy. The existing byte comparison remains exact.
    assert generated_r04("Prescott") == generated_r04("Haswell")


def test_r04_keeps_real_small_direction_error_and_falsifiers():
    import importlib.util

    spec = importlib.util.spec_from_file_location("r04_generator", GOLDENS / "gen_rig_goldens.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    a = np.array([0.0, 1.0, 0.0])
    theta = np.radians(1e-6)
    b = np.array([np.sin(theta), np.cos(theta), 0.0])
    assert abs(gen.direction_angle_deg(a, b) - 1e-6) < 1e-12
    assert abs(gen.direction_angle_deg(a, -a) - 180.0) < 1e-12
    case = json.loads(generated_r04("Prescott"))
    assert case["expected"]["max_along_error_deg"] < 1e-4
    assert case["falsifier"]["local_copy_max_error_deg"] > 55.0
    assert case["falsifier"]["copy_transforms_pose_space_length_drift_m"] > 0.01
