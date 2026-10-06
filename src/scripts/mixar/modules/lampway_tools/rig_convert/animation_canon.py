# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the TITAN project, same author (tools/animation_canon.py, sha256 631107e1333e), on 2026-10-06. Pure python; the wire ids are unchanged.
"""Pure, reversible sampled-animation normalization; world runtimes are adapters.

Hamilton xyzw rotations, component-space transforms, explicit centimetre scale.
Reference alignment creates processing data; it never edits a native skeleton.
"""
import copy
from fractions import Fraction
import hashlib
import json
import math

SCHEMA = "titan.animation/1"            # a stable wire contract shared with TITAN (the game reads it): never renamed
PROFILE_SCHEMA = "titan.animation-profile/1"
IDENTITY = [0, 0, 0, 1]


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected a finite number")
    return float(value)


def _vector(value, count):
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError("incorrect vector length")
    return [_number(x) for x in value]


def _round(value):
    rounded = round(value, 9)
    return 0 if rounded == 0 else rounded


def qnorm(value):
    q = _vector(value, 4)
    norm = math.sqrt(sum(x*x for x in q))
    if norm < 1e-12:
        raise ValueError("zero quaternion")
    q = [x / norm for x in q]
    # w==0 has two equivalent signs too; use a fixed lexicographic tie break.
    sign = next((x for x in reversed(q) if abs(x) > 1e-15), 1)
    return [x if sign > 0 else -x for x in q]


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw*bx + ax*bw + ay*bz - az*by,
            aw*by - ax*bz + ay*bw + az*bx,
            aw*bz + ax*by - ay*bx + az*bw,
            aw*bw - ax*bx - ay*by - az*bz]


def qinv(q):
    x, y, z, w = qnorm(q)
    return [-x, -y, -z, w]


def rotate(q, vector):
    q = qnorm(q)
    return qmul(qmul(q, [*vector, 0]), qinv(q))[:3]


# A UNIFORM scale is a similarity transform: it composes with rotation and translation exactly, and a pack that authors
# one means it (a weapon pack scales `head` to 0.999). A NON-UNIFORM one does not compose through a quaternion
# and still needs an explicit affine adapter. The tolerance is float32 evaluation noise: a sampled scale of 1 comes back
# as 1 +/- a few ulps, and the canonical value is the mean at six decimals so two runs agree byte for byte.
UNIFORM_SCALE_TOLERANCE = 1e-5


def _scale(value):
    scale = _vector(value, 3)
    factor = sum(scale) / 3
    if factor <= 1e-6 or max(scale) - min(scale) > UNIFORM_SCALE_TOLERANCE * max(1.0, abs(factor)):
        raise ValueError("non-uniform or non-positive scale requires an explicit affine animation adapter")
    factor = _round(round(factor, 6))
    return [factor, factor, factor]


def _transform(value):
    if not isinstance(value, dict) or set(value) != {"translation", "rotation", "scale"}:
        raise ValueError("transform requires translation, rotation and scale only")
    return {"translation": [_round(x) for x in _vector(value["translation"], 3)],
            "rotation": [_round(x) for x in qnorm(value["rotation"])],
            "scale": _scale(value["scale"])}


def _name(name):
    if not isinstance(name, str) or not name or name.strip() != name:
        raise ValueError("expected a nonempty exact bone/profile name")
    return name


def _hierarchy(bones):
    seen = set()
    if not isinstance(bones, list) or not bones:
        raise ValueError("complete ordered bone table required")
    for i, bone in enumerate(bones):
        name = _name(bone["name"])
        parent = bone["parent"]
        if name in seen or (i == 0 and parent is not None) or (i and parent not in seen):
            raise ValueError("bone hierarchy must have one root, unique names and parents before children")
        seen.add(name)
    return seen


def _compose(parent, local):
    # Similarity composition: the parent's uniform scale carries the child's offset, and the scales multiply.
    factor = parent["scale"][0]
    offset = rotate(parent["rotation"], [x*factor for x in local["translation"]])
    return {"translation": [a+b for a, b in zip(parent["translation"], offset)],
            "rotation": qnorm(qmul(parent["rotation"], local["rotation"])),
            "scale": [a*b for a, b in zip(parent["scale"], local["scale"])]}


def _relative(parent, world):
    inv = qinv(parent["rotation"])
    factor = parent["scale"][0]
    return _transform({"translation": [x/factor for x in rotate(inv, [a-b for a, b in zip(world["translation"], parent["translation"])])],
                       "rotation": qmul(inv, world["rotation"]),
                       "scale": [a/b for a, b in zip(world["scale"], parent["scale"])]})


def _worlds(bones, locals_by_name):
    result = {}
    for b in bones:
        local = locals_by_name[b["name"]]
        result[b["name"]] = (_compose(result[b["parent"]], local)
                             if b["parent"] is not None else copy.deepcopy(local))
    return result


def _between(start, end):
    a, b = _vector(start, 3), _vector(end, 3)
    na, nb = math.sqrt(sum(x*x for x in a)), math.sqrt(sum(x*x for x in b))
    if min(na, nb) < 1e-9:
        raise ValueError("reference alignment requires nonzero directions")
    a, b = [x/na for x in a], [x/nb for x in b]
    dot = max(-1, min(1, sum(x*y for x, y in zip(a, b))))
    if dot < -1 + 1e-10:
        raise ValueError("antiparallel alignment requires an authored rotation axis")
    return qnorm([a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
                  a[0]*b[1]-a[1]*b[0], 1+dot])


def align_reference(bones, rules):
    """Rotate named chains to authored directions; retain every local offset.

    Native local transforms are extracted by a world adapter. Rules are applied
    in order and must name a direct child. All unmentioned/helper bones remain.
    Returned bind and reference tables are component space, with local tables
    retained for reproducibility. This is not mesh posing or rig replacement.
    """
    names = _hierarchy(bones)
    original = {b["name"]: _transform(b["local"]) for b in bones}
    local = copy.deepcopy(original)
    parents = {b["name"]: b["parent"] for b in bones}
    before = _worlds(bones, original)
    for rule in rules:
        if set(rule) != {"bone", "toward", "direction"}:
            raise ValueError("alignment rule requires bone, toward and direction")
        bone, child = rule["bone"], rule["toward"]
        if bone not in names or child not in names or parents[child] != bone:
            raise ValueError("alignment must name a bone and its direct child")
        world = _worlds(bones, local)
        direction = [a-b for a, b in zip(world[child]["translation"], world[bone]["translation"])]
        delta = _between(direction, rule["direction"])
        wanted = qmul(delta, world[bone]["rotation"])
        parent_q = world[parents[bone]]["rotation"] if parents[bone] else IDENTITY
        local[bone]["rotation"] = qnorm(qmul(qinv(parent_q), wanted))
    after = _worlds(bones, local)
    return [{"name": b["name"], "parent": b["parent"],
             "bind": _transform(before[b["name"]]),
             "reference": _transform(after[b["name"]]),
             "bind_local": original[b["name"]],
             "reference_local": _transform(local[b["name"]])} for b in bones]


def make_profile(name, bones, *, basis, centimeters_per_unit):
    """Pin a COMPLETE measured T-reference and explicit proper-rotation adapter.

    Handedness reflection belongs in the extracting world adapter; this first
    rotation-only leg refuses scale/shear rather than misapplying quaternions.
    """
    _name(name)
    _hierarchy(bones)
    basis = [_round(x) for x in qnorm(basis)]
    units = _number(centimeters_per_unit)
    if units <= 0:
        raise ValueError("profile units must be positive")
    entries = []
    by_name = {}
    for bone in bones:
        required = {"name", "parent", "bind", "reference"}
        if not required <= set(bone) or set(bone) - required - {"bind_local", "reference_local", "canonical_reference", "canonical_reference_local"}:
            raise ValueError("unsupported profile bone fields")
        entry = {"name": bone["name"], "parent": bone["parent"],
                 "bind": _transform(bone["bind"]), "reference": _transform(bone["reference"])}
        for field in ("bind", "reference"):
            local = _relative(by_name[bone["parent"]][field], entry[field]) if bone["parent"] else copy.deepcopy(entry[field])
            supplied = bone.get(field + "_local")
            if supplied is not None:
                check = compare([{"time": [0, 1], "pose": {"bone": local}}],
                                [{"time": [0, 1], "pose": {"bone": _transform(supplied)}}])
                if check["translation_max"] > 1e-5 or check["rotation_max_degrees"] > 1e-5:
                    raise ValueError("profile local/component reference tables disagree")
                local = _transform(supplied)
            entry[field + "_local"] = local
        entry["canonical_reference"] = {
            "translation": [_round(x * units) for x in rotate(basis, entry["reference"]["translation"])],
            "rotation": IDENTITY[:], "scale": [1, 1, 1]}
        entry["canonical_reference_local"] = (_relative(by_name[bone["parent"]]["canonical_reference"], entry["canonical_reference"])
                                               if bone["parent"] else copy.deepcopy(entry["canonical_reference"]))
        entries.append(entry)
        by_name[bone["name"]] = entry
    if max(abs(x) for x in entries[0]["canonical_reference"]["translation"]) > 1e-6:
        raise ValueError("canonical reference root must be at the origin")
    value = {"schema": PROFILE_SCHEMA, "name": name, "reference_pose": "T",
             "space": {"units": "cm", "forward": "+X", "right": "+Y", "up": "+Z",
                       "handedness": "left", "quaternion": "Hamilton-xyzw"},
             "adapter": {"basis": basis, "centimeters_per_unit": units}, "bones": entries}
    value["sha256"] = digest(value)
    return value


def _check_hash(value, label):
    if not isinstance(value, dict) or "sha256" not in value:
        raise ValueError(label + " hash is missing")
    payload = {k: v for k, v in value.items() if k != "sha256"}
    if digest(payload) != value["sha256"]:
        raise ValueError(label + " hash mismatch")


def _profile(profile):
    _check_hash(profile, "profile")
    if profile.get("schema") != PROFILE_SCHEMA:
        raise ValueError("unsupported profile schema")
    # Verify a hash is not being used as a substitute for structural validation.
    rebuilt = make_profile(profile["name"], profile["bones"], **profile["adapter"])
    if rebuilt != profile:
        raise ValueError("profile is not in canonical form")
    return {b["name"]: b for b in profile["bones"]}


def _duration(value):
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        raise ValueError("duration must be a finite decimal/rational") from None
    if result < 0 or result > 3600:
        raise ValueError("duration outside bounded animation range 0..3600")
    return result


def sample_times(duration):
    """30fps rational keys plus the exact terminal time, without overshooting."""
    end = _duration(duration)
    times = [Fraction(i, 30) for i in range(int(end * 30) + 1)]
    if times[-1] != end:
        times.append(end)
    return [[t.numerator, t.denominator] for t in times]


def _samples(samples, profile, duration):
    expected = sample_times(duration)
    if not isinstance(samples, list) or len(samples) != len(expected):
        raise ValueError("samples must cover 30fps and the exact terminal time")
    names = {b["name"] for b in profile["bones"]}
    for sample, time in zip(samples, expected):
        if set(sample) != {"time", "pose"} or sample["time"] != time:
            raise ValueError("sample time differs from rational 30fps/terminal schedule")
        if not isinstance(sample["pose"], dict) or set(sample["pose"]) != names:
            raise ValueError("sample bone channels must exactly match the complete profile")
        for transform in sample["pose"].values():
            _transform(transform)


def normalize(samples, profile, *, duration=None, channels=None):
    refs = _profile(profile)
    if isinstance(samples, dict) and samples.get("schema") == SCHEMA:
        _packet(samples, profile)
        if duration is not None or channels is not None:
            raise ValueError("canonical input already owns its duration and channels")
        return copy.deepcopy(samples)
    duration = _duration(duration)
    _samples(samples, profile, str(duration))
    if not isinstance(channels, dict):
        raise ValueError("explicit channel document required")
    encode(channels)  # Reject NaN/unsupported values before producing a packet.
    b = profile["adapter"]["basis"]
    units = profile["adapter"]["centimeters_per_unit"]
    result = []
    for sample in samples:
        pose = {}
        for name, native in sample["pose"].items():
            t = _transform(native)
            q = qmul(qmul(qmul(b, t["rotation"]), qinv(refs[name]["reference"]["rotation"])), qinv(b))
            pose[name] = _transform({"translation": [x*units for x in rotate(b, t["translation"])],
                                     "rotation": q, "scale": t["scale"]})
        result.append({"time": sample["time"][:], "pose": pose})
    value = {"schema": SCHEMA, "profile": copy.deepcopy(profile), "duration": str(duration),
             "fps": [30, 1], "samples": result, "channels": copy.deepcopy(channels)}
    value["sha256"] = digest(value)
    return value


def _packet(packet, profile):
    _check_hash(packet, "animation")
    if set(packet) != {"schema", "profile", "duration", "fps", "samples", "channels", "sha256"}:
        raise ValueError("unsupported animation packet fields")
    if packet["schema"] != SCHEMA or packet["fps"] != [30, 1]:
        raise ValueError("unsupported animation schema/frame rate")
    _profile(profile)
    if packet["profile"] != profile:
        raise ValueError("animation/profile mismatch; cross-rig transfer is a separate operation")
    _samples(packet["samples"], profile, packet["duration"])


def adapt(packet, profile):
    """Invert normalization onto the ORIGINAL native profile, never a new rig."""
    _packet(packet, profile)
    refs = {b["name"]: b for b in profile["bones"]}
    b = profile["adapter"]["basis"]
    units = profile["adapter"]["centimeters_per_unit"]
    result = []
    for sample in packet["samples"]:
        pose = {}
        for name, t in sample["pose"].items():
            q = qmul(qmul(qmul(qinv(b), t["rotation"]), b), refs[name]["reference"]["rotation"])
            pose[name] = _transform({"translation": [x/units for x in rotate(qinv(b), t["translation"])],
                                     "rotation": q, "scale": t["scale"]})
        result.append({"time": sample["time"][:], "pose": pose})
    return result


def compare(expected, actual):
    """Independent transform comparison in the supplied world's position units."""
    if len(expected) != len(actual) or not expected:
        raise ValueError("comparison needs matching nonempty sample sets")
    rows = []
    for source, output in zip(expected, actual):
        if source["time"] != output["time"] or set(source["pose"]) != set(output["pose"]):
            raise ValueError("comparison time/bone roster mismatch")
        for bone, a in source["pose"].items():
            b = output["pose"][bone]
            qa, qb = qnorm(a["rotation"]), qnorm(b["rotation"])
            # atan2 is stable near zero unlike acos(dot) after float rounding.
            delta = qnorm(qmul(qa, qinv(qb)))
            angle = math.degrees(2 * math.atan2(math.sqrt(sum(x*x for x in delta[:3])), abs(delta[3])))
            distance = math.sqrt(sum((x-y)**2 for x, y in zip(a["translation"], b["translation"])))
            scale = max(abs(x-y) for x, y in zip(a["scale"], b["scale"]))
            rows.append({"bone": bone, "time": source["time"], "translation": distance,
                         "rotation_degrees": angle, "scale": scale})
    return {"translation_max": max(r["translation"] for r in rows),
            "rotation_max_degrees": max(r["rotation_degrees"] for r in rows),
            "scale_max": max(r["scale"] for r in rows), "measurements": rows}


def retarget(packet, target_profile, rules):
    """Transfer canonical motion with exhaustive rules; both native rigs stay intact.

    The publishing adapter records source/output/profile/rules hashes separately.
    Channels remain unchanged data, never a place for hidden retarget policy.
    """
    source_profile = packet['profile']
    _packet(packet, source_profile)
    source, target = _profile(source_profile), _profile(target_profile)
    if not isinstance(rules, dict) or set(rules) != {'map', 'reference_follow', 'translation_scales', 'anchors'}:
        raise ValueError('retarget requires explicit map, reference followers, translation scales and anchors')
    mapping, followers = rules['map'], rules['reference_follow']
    scales, anchors = rules['translation_scales'], rules['anchors']
    if not isinstance(mapping, dict) or set(mapping) != set(source):
        raise ValueError('retarget map must account for every source bone')
    if any(not isinstance(v, str) for v in mapping.values()) or len(set(mapping.values())) != len(mapping):
        raise ValueError('retarget map must be one-to-one')
    if not isinstance(followers, list) or any(not isinstance(v, str) for v in followers) or len(set(followers)) != len(followers):
        raise ValueError('reference followers must be unique bone names')
    mapped = set(mapping.values())
    if mapped & set(followers) or mapped | set(followers) != set(target):
        raise ValueError('retarget rules must account for every target bone exactly once')
    if not isinstance(scales, dict) or set(scales) != mapped or any(_number(v) <= 0 for v in scales.values()):
        raise ValueError('explicit positive translation scale required for every mapped target bone')
    source_root, target_root = source_profile['bones'][0]['name'], target_profile['bones'][0]['name']
    if mapping[source_root] != target_root:
        raise ValueError('retarget roots must map to each other')
    if not isinstance(anchors, dict) or not set(anchors) <= mapped:
        raise ValueError('anchors must name mapped target helpers')
    order = {b['name']: i for i, b in enumerate(target_profile['bones'])}
    for name, anchor in anchors.items():
        if not isinstance(anchor, dict) or set(anchor) != {'source', 'target', 'scale'}:
            raise ValueError('anchor requires explicit source/target bone and scale')
        if anchor['source'] not in source or anchor['target'] not in target or order[anchor['target']] >= order[name]:
            raise ValueError('anchor must resolve to an earlier evaluated target bone')
        if name == target_root or _number(anchor['scale']) <= 0:
            raise ValueError('root cannot be anchored; anchor scale must be positive')
    inverse_map = {t: s for s, t in mapping.items()}
    sb, tb = source_profile['adapter']['basis'], target_profile['adapter']['basis']
    su, tu = source_profile['adapter']['centimeters_per_unit'], target_profile['adapter']['centimeters_per_unit']
    converted = []
    for canonical, native in zip(packet['samples'], adapt(packet, source_profile)):
        output = {}
        for bone in target_profile['bones']:
            name, parent = bone['name'], bone['parent']
            local = copy.deepcopy(bone['reference_local'])
            if name in inverse_map:
                src = inverse_map[name]
                src_parent = source[src]['parent']
                raw = native['pose'][src]
                raw_local = _relative(native['pose'][src_parent], raw) if src_parent else raw
                delta = [a-b for a, b in zip(raw_local['translation'], source[src]['reference_local']['translation'])]
                source_parent_ref = source[src_parent]['reference']['rotation'] if src_parent else IDENTITY
                target_parent_ref = target[parent]['reference']['rotation'] if parent else IDENTITY
                canonical_delta = rotate(sb, rotate(source_parent_ref, delta))
                target_delta = rotate(qinv(target_parent_ref), rotate(qinv(tb), canonical_delta))
                local['translation'] = [a + d*su*scales[name]/tu for a, d in zip(local['translation'], target_delta)]
                desired = qmul(qmul(qmul(qinv(tb), canonical['pose'][src]['rotation']), tb), bone['reference']['rotation'])
                local['rotation'] = qmul(qinv(output[parent]['rotation']), desired) if parent else desired
            world = _compose(output[parent], local) if parent else local
            if name in anchors:
                anchor = anchors[name]
                src = inverse_map[name]
                offset = [a-b for a, b in zip(canonical['pose'][src]['translation'], canonical['pose'][anchor['source']]['translation'])]
                target_anchor = output[anchor['target']]
                target_anchor_c = qmul(qmul(qmul(tb, target_anchor['rotation']), qinv(target[anchor['target']]['reference']['rotation'])), qinv(tb))
                offset = rotate(target_anchor_c, rotate(qinv(canonical['pose'][anchor['source']]['rotation']), offset))
                offset = rotate(qinv(tb), offset)
                world['translation'] = [a + d*anchor['scale']/tu for a, d in zip(target_anchor['translation'], offset)]
            output[name] = _transform(world)
        converted.append({'time': canonical['time'][:], 'pose': output})
    return normalize(converted, target_profile, duration=packet['duration'], channels=packet['channels'])
