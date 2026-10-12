# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Nine-decimal quaternion publication must rebuild to exactly its bytes."""
import copy
import importlib.util
import random
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("fixed_point_animation", Path(__file__).parents[2] /
    "src/scripts/mixar/modules/lampway_tools/rig_convert/animation_canon.py")
AC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AC)


def oblique_rotation():
    rng = random.Random(1729)
    for _ in range(241):
        value = [rng.uniform(-1, 1) for _ in range(4)]
    return value


def profile():
    transform = {"translation": [0, 0, 0], "rotation": oblique_rotation(), "scale": [1, 1, 1]}
    return AC.make_profile("synthetic", [{"name": "root", "parent": None,
        "bind": transform, "reference": copy.deepcopy(transform)}],
        basis=oblique_rotation(), centimeters_per_unit=100)


def test_generated_profile_rebuild_is_an_exact_fixed_point():
    first = profile()
    for _ in range(20):
        rebuilt = AC.make_profile(first["name"], first["bones"], **first["adapter"])
        assert AC.encode(rebuilt) == AC.encode(first)
        assert rebuilt["sha256"] == first["sha256"]
    assert AC._profile(first)


def test_sign_and_scale_equivalent_inputs_publish_identical_profile_bytes():
    first = profile()
    bones = copy.deepcopy(first['bones'])
    for bone in bones:
        for field in ('bind', 'reference', 'bind_local', 'reference_local'):
            bone[field]['rotation'] = [-x * 2 for x in bone[field]['rotation']]
    basis = [-x * 2 for x in first['adapter']['basis']]
    assert AC.encode(AC.make_profile(first['name'], bones, basis=basis, centimeters_per_unit=100)) == AC.encode(first)


@pytest.mark.parametrize('mutation', ['digest', 'rehash', 'reference', 'roster'])
def test_fixed_point_does_not_admit_corrupted_or_noncanonical_profiles(mutation):
    p = profile()
    if mutation == 'roster': p['bones'].append(copy.deepcopy(p['bones'][0]))
    else: p['bones'][0]['bind']['rotation'][0] += .001
    if mutation in ('rehash', 'reference', 'roster'):
        if mutation == 'reference': p['bones'][0]['canonical_reference']['rotation'] = [0, 0, 1, 0]
        p['sha256'] = AC.digest({k: v for k, v in p.items() if k != 'sha256'})
    with pytest.raises(ValueError):
        AC._profile(p)


def test_adapter_coupled_publication_has_exact_packet_inverse_without_retained_inputs():
    rng = random.Random(20261009)
    for _ in range(100):
        rotation = lambda: [rng.uniform(-1, 1) for _ in range(4)]
        reference = {'translation': [0, 0, 0], 'rotation': rotation(), 'scale': [1, 1, 1]}
        p = AC.make_profile('oblique', [{'name': 'root', 'parent': None,
            'bind': reference, 'reference': reference}], basis=rotation(), centimeters_per_unit=100)
        native = [{'time': [0, 1], 'pose': {'root': {
            'translation': [rng.uniform(-2, 2) for _ in range(3)],
            'rotation': rotation(), 'scale': [1.125, 1.125, 1.125]}}}]
        original = copy.deepcopy(native)
        packet = AC.normalize(native, p, duration=0, channels={'authored': 'preserved'})
        for _ in range(3):
            # A plain copied wire packet owns no original input or out-of-band cache.
            restored = AC.adapt(copy.deepcopy(packet), copy.deepcopy(p))
            rebuilt = AC.normalize(restored, p, duration=0, channels=packet['channels'])
            assert AC.encode(rebuilt) == AC.encode(packet)
            assert rebuilt['sha256'] == packet['sha256']
            assert set(restored[0]['pose']['root']) == {'translation', 'rotation', 'scale'}
        assert native == original
