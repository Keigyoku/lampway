# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The "UE Default Lit" node group and the material preview (specs/ue_parity/contracts/ue_material.md §6), EEVEE only.

UE's legacy Default Lit (energy conservation off, no multiscatter) is Lambert ADDED to one single-scatter GGX lobe whose
Fresnel is Schlick with F90 = saturate(50 * F0.g) (SHD-02, SHD-04). EEVEE evaluates every GGX lobe as F0 * A + F90 * B (its
split-sum LUT terms A and B), so the lobe is realised EXACTLY by an EEVEE Specular BSDF (F90 fixed at 1, F0 unclamped above)
whose specular colour is F0 / a and whose closure is scaled by a = saturate(50 * F0.g): a * (F0 / a * A + B) = F0 * A + a * B.
(The Metallic BSDF clamps F0 to 1 and the F82 model cannot lower F90, so neither can express it.) a is floored at 1e-4, so the
worst error is 1e-4 * B. The normal reads R and G of a DirectX map and rebuilds Z as sqrt(1 - x^2 - y^2), as UE's BC5 decode
does (NRM-02), then hands Blender's Normal Map node (DirectX convention) a unit vector; masked opacity keeps alpha >= 0.3333.

``preview`` never edits the original material: it builds ``<name> [UE]`` beside it, so the original stays exactly as it was."""

import bpy

from . import material_map as MM
from . import profile as PR

A_FLOOR = 1e-4
_SOCKETS = (("Base Color", "NodeSocketColor", (0.8, 0.8, 0.8, 1.0)), ("Metallic", "NodeSocketFloat", 0.0), ("Specular", "NodeSocketFloat", 0.5),
            ("Roughness", "NodeSocketFloat", 0.5), ("Emission Color", "NodeSocketColor", (0.0, 0.0, 0.0, 1.0)), ("Emission Strength", "NodeSocketFloat", 0.0),
            ("Alpha", "NodeSocketFloat", 1.0), ("Masked", "NodeSocketFloat", 0.0), ("Normal Map", "NodeSocketColor", (0.5, 0.5, 1.0, 1.0)),
            ("Normal Strength", "NodeSocketFloat", 1.0))


class GroupError(ValueError):
    pass


def _math(nt, op, a, b=None, clamp=False):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _mix(nt, data_type, blend="MIX"):
    """A Mix node and its (factor, a, b, result) sockets for ``data_type``: the node carries one socket set per type under the
    same display names, so the sockets are taken by identifier."""
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = data_type
    n.blend_type = blend
    suffix = {"RGBA": "Color", "FLOAT": "Float", "VECTOR": "Vector"}[data_type]
    pick = lambda coll, ident: next(s for s in coll if s.identifier == ident)
    fac = pick(n.inputs, "Factor_Float" if data_type != "VECTOR" else "Factor_Vector")
    return fac, pick(n.inputs, "A_" + suffix), pick(n.inputs, "B_" + suffix), pick(n.outputs, "Result_" + suffix)


def ensure_group():
    """The node group, built once per file and versioned in its name: a second call returns the same group."""
    g = bpy.data.node_groups.get(MM.GROUP_NAME)
    if g is not None:
        return g
    g = bpy.data.node_groups.new(MM.GROUP_NAME, "ShaderNodeTree")
    for name, kind, default in _SOCKETS:
        s = g.interface.new_socket(name, in_out="INPUT", socket_type=kind)
        s.default_value = default
    g.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    nt = g
    gin = nt.nodes.new("NodeGroupInput")
    gout = nt.nodes.new("NodeGroupOutput")
    I = gin.outputs

    def mad(v, mul, add):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = "MULTIPLY_ADD"
        nt.links.new(v, n.inputs[0])
        n.inputs[1].default_value = mul
        n.inputs[2].default_value = add
        return n.outputs[0]

    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(I["Normal Map"], sep.inputs[0])
    x = _math(nt, "MULTIPLY", mad(sep.outputs[0], 2.0, -1.0), I["Normal Strength"])
    y = _math(nt, "MULTIPLY", mad(sep.outputs[1], 2.0, -1.0), I["Normal Strength"])
    xx_yy = _math(nt, "ADD", _math(nt, "MULTIPLY", x, x), _math(nt, "MULTIPLY", y, y))
    z = _math(nt, "SQRT", _math(nt, "MAXIMUM", _math(nt, "SUBTRACT", 1.0, xx_yy), 0.0))
    comb = nt.nodes.new("ShaderNodeCombineColor")
    for i, v in enumerate((x, y, z)):
        nt.links.new(mad(v, 0.5, 0.5), comb.inputs[i])
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.convention = "DIRECTX"
    nt.links.new(comb.outputs[0], nmap.inputs["Color"])
    N = nmap.outputs["Normal"]

    # diffuse: Lambert, colour = BaseColor * (1 - Metallic), not attenuated by the specular lobe (SHD-02)
    one_minus_m = _math(nt, "SUBTRACT", 1.0, I["Metallic"])
    dfac, da, db, dres = _mix(nt, "RGBA", "MULTIPLY")
    dfac.default_value = 1.0
    nt.links.new(I["Base Color"], da)
    gray = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(one_minus_m, gray.inputs[i])
    nt.links.new(gray.outputs[0], db)
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Roughness"].default_value = 0.0
    nt.links.new(dres, diff.inputs["Color"])
    nt.links.new(N, diff.inputs["Normal"])

    # F0 = lerp(0.08 * Specular, BaseColor, Metallic); a = saturate(50 * F0.g)
    f0d = _math(nt, "MULTIPLY", I["Specular"], MM.UE_MAX_F0)
    f0dc = nt.nodes.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(f0d, f0dc.inputs[i])
    ffac, fa, fb, f0 = _mix(nt, "RGBA")
    nt.links.new(I["Metallic"], ffac)
    nt.links.new(f0dc.outputs[0], fa)
    nt.links.new(I["Base Color"], fb)
    f0sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(f0, f0sep.inputs[0])
    a = _math(nt, "MULTIPLY", f0sep.outputs[1], 50.0, clamp=True)
    a_safe = _math(nt, "MAXIMUM", a, A_FLOOR)
    inv = nt.nodes.new("ShaderNodeVectorMath")
    inv.operation = "DIVIDE"
    nt.links.new(f0, inv.inputs[0])
    nt.links.new(a_safe, inv.inputs[1])
    spec = nt.nodes.new("ShaderNodeEeveeSpecular")
    spec.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    nt.links.new(inv.outputs["Vector"], spec.inputs["Specular"])
    nt.links.new(I["Roughness"], spec.inputs["Roughness"])
    nt.links.new(N, spec.inputs["Normal"])
    scaled = nt.nodes.new("ShaderNodeMixShader")                     # shader 1 empty: the result is a * Specular BSDF
    nt.links.new(a_safe, scaled.inputs["Fac"])
    nt.links.new(spec.outputs["BSDF"], scaled.inputs[2])

    emis = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(I["Emission Color"], emis.inputs["Color"])
    nt.links.new(I["Emission Strength"], emis.inputs["Strength"])
    lit = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(diff.outputs["BSDF"], lit.inputs[0])
    nt.links.new(scaled.outputs["Shader"], lit.inputs[1])
    surf = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(lit.outputs[0], surf.inputs[0])
    nt.links.new(emis.outputs["Emission"], surf.inputs[1])

    # opacity: Masked keeps alpha >= 0.3333 (UE discards alpha - clip < 0); otherwise alpha as given
    keep = _math(nt, "SUBTRACT", 1.0, _math(nt, "LESS_THAN", I["Alpha"], MM.OPACITY_MASK_CLIP))
    afac, aa, ab, alpha = _mix(nt, "FLOAT")
    nt.links.new(I["Masked"], afac)
    nt.links.new(I["Alpha"], aa)
    nt.links.new(keep, ab)
    cut = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(alpha, cut.inputs["Fac"])
    nt.links.new(nt.nodes.new("ShaderNodeBsdfTransparent").outputs[0], cut.inputs[1])
    nt.links.new(surf.outputs[0], cut.inputs[2])
    nt.links.new(cut.outputs["Shader"], gout.inputs["Shader"])
    return g


def _bsdf(mat):
    if not mat.use_nodes or mat.node_tree is None:
        return None
    out = next((n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
    if out is None or not out.inputs["Surface"].is_linked:
        return None
    node = out.inputs["Surface"].links[0].from_node
    return node if node.type == "BSDF_PRINCIPLED" else None


def _image_source(socket):
    """The image texture feeding a socket directly or through one Separate Color (an ORM channel)."""
    if not socket.is_linked:
        return None
    node = socket.links[0].from_node
    if node.type == "SEPARATE_COLOR" and node.inputs[0].is_linked:
        node = node.inputs[0].links[0].from_node
    return node if node.type == "TEX_IMAGE" else None


def _val(sock):
    v = sock.default_value
    return [float(c) for c in v] if hasattr(v, "__len__") else float(v)


def read_spec(mat) -> dict:
    """The plain-data spec ``material_map.translate`` takes, read from the material's active Principled BSDF."""
    b = _bsdf(mat)
    spec = {"material": mat.name, "shader": "principled" if b is not None else "other", "surface_render_method": mat.surface_render_method,
            "use_backface_culling": bool(mat.use_backface_culling), "inputs": {}, "linked": {}, "normal": None}
    if b is None:
        return spec
    for name in MM.PRINCIPLED_DEFAULTS:
        sock = b.inputs[name]
        spec["inputs"][name] = _val(sock)
        if sock.is_linked:
            tex = _image_source(sock)
            spec["linked"][name] = {"file": bpy.path.basename(tex.image.filepath) if tex and tex.image else None,
                                    "colorspace": tex.image.colorspace_settings.name if tex and tex.image else None}
    ns = b.inputs["Normal"]
    if ns.is_linked and ns.links[0].from_node.type == "NORMAL_MAP":
        nm = ns.links[0].from_node
        tex = _image_source(nm.inputs["Color"])
        spec["normal"] = {"file": bpy.path.basename(tex.image.filepath) if tex and tex.image else None,
                          "colorspace": tex.image.colorspace_settings.name if tex and tex.image else None,
                          "strength": float(nm.inputs["Strength"].default_value), "convention": nm.convention, "space": nm.space}
    return spec


def _relink(nt, src_socket, dst_socket):
    if src_socket.is_linked:
        nt.links.new(src_socket.links[0].from_socket, dst_socket)
        return True
    return False


def build_preview(mat, translation) -> "bpy.types.Material":
    """``<name> [UE]``: a copy of the material whose output is the group, fed by the original's links and the translation's values."""
    group = ensure_group()
    new = mat.copy()
    new.name = f"{mat.name} [UE]"
    nt = new.node_tree
    b = _bsdf(new)
    ue = translation["ue"]
    node = nt.nodes.new("ShaderNodeGroup")
    node.node_tree = group
    gi = node.inputs
    gi["Base Color"].default_value = ue["vectors"]["BaseColor"]
    gi["Metallic"].default_value = ue["scalars"]["Metallic"]
    gi["Specular"].default_value = ue["scalars"]["Specular"]
    gi["Roughness"].default_value = ue["scalars"]["Roughness"]
    gi["Emission Color"].default_value = ue["vectors"]["EmissiveColor"]
    gi["Emission Strength"].default_value = b.inputs["Emission Strength"].default_value     # Blender units: exposure carries k
    gi["Alpha"].default_value = b.inputs["Alpha"].default_value
    gi["Masked"].default_value = 1.0 if ue["blend_mode"] == "Masked" else 0.0
    for name in ("Base Color", "Metallic", "Roughness", "Alpha", "Emission Strength"):
        _relink(nt, b.inputs[name], gi[name])
    _relink(nt, b.inputs["Emission Color"], gi["Emission Color"])
    ns = b.inputs["Normal"]
    if ns.is_linked and ns.links[0].from_node.type == "NORMAL_MAP":
        nm = ns.links[0].from_node
        gi["Normal Strength"].default_value = nm.inputs["Strength"].default_value
        if nm.inputs["Color"].is_linked:
            src = nm.inputs["Color"].links[0].from_socket
            if nm.convention != "DIRECTX":                                   # an OpenGL map: flip green into the DX the group reads
                sep, comb = nt.nodes.new("ShaderNodeSeparateColor"), nt.nodes.new("ShaderNodeCombineColor")
                flip = nt.nodes.new("ShaderNodeMath")
                flip.operation = "SUBTRACT"
                flip.inputs[0].default_value = 1.0
                nt.links.new(src, sep.inputs[0])
                nt.links.new(sep.outputs[1], flip.inputs[1])
                nt.links.new(sep.outputs[0], comb.inputs[0])
                nt.links.new(flip.outputs[0], comb.inputs[1])
                nt.links.new(sep.outputs[2], comb.inputs[2])
                src = comb.outputs[0]
            nt.links.new(src, gi["Normal Map"])
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
    nt.links.new(node.outputs["Shader"], out.inputs["Surface"])
    new.use_backface_culling = not ue["two_sided"]
    new.surface_render_method = "BLENDED" if ue["blend_mode"] == "Translucent" else "DITHERED"
    return new


def preview(material, profile=None) -> dict:
    """Translate ``material`` (mode preview) and build its UE preview material; the original is left as it was."""
    mat = bpy.data.materials.get(material)
    if mat is None:
        raise GroupError(f"no material named {material!r}; the materials are: {sorted(m.name for m in bpy.data.materials)}")
    prof = profile if isinstance(profile, dict) else PR.load(profile or PR.DEFAULT_PROFILE)
    tr = MM.translate(read_spec(mat), prof, mode="preview")
    new = build_preview(mat, tr)
    return dict(tr, ok=True, preview_material=new.name)
