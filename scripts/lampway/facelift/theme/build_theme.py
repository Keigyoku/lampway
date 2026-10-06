#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the Lampway Night (dark) and Lampway Paper (light) Blender themes from tokens.json (v2, the calm pass:
no panel outlines or header bars, borderless fields and buttons, a quieter grid, no amber outline on the active editor).

    python3 build_theme.py            # writes lampway_dark.xml, lampway_light.xml and a provenance file for each

Build the tool, not the output: the XML is generated, never hand-edited. The base is the 0.1.0 build's own default
theme (base/default_theme_0.1.0.xml, dumped by dump_theme.py), so every attribute the 5.2 schema carries is written.
Every colour is either a token from tokens.json (optionally with an alpha, "accent@38"), a Blender domain convention
copied from upstream's preset at the same path ("@upstream": axis colours, keyframe shapes, bone sets, node
categories), or an explicit literal listed in KEPT with its reason. A colour attribute no rule covers stops the build:
the theme cannot silently inherit Mixar's green.
"""
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
PRESETS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "src", "scripts", "presets", "interface_theme"))
TOKENS = json.load(open(os.path.join(HERE, "tokens.json")))
SCHEMA = json.load(open(os.path.join(HERE, "base", "theme_schema_0.1.0.json")))["structs"]
BASE = os.path.join(HERE, "base", "default_theme_0.1.0.xml")
UPSTREAM = os.path.join(HERE, "base", "upstream_Blender_Light_5.2.xml")

# ----------------------------------------------------------------------------------------------- the rules
# key: container path below <Theme> (lower-case tags), e.g. "user_interface/wcol_regular", "view_3d/space/gradients".
# value: {attribute: spec}. spec: "token", "token@AA" (hex alpha), "@upstream", "=literal" (KEPT reason required).

def widget(inner, inner_sel, outline="line", outline_sel="accent", item="muted", text="text", text_sel="text", roundness="0.35"):
    return {"inner": inner, "inner_sel": inner_sel, "outline": outline, "outline_sel": outline_sel, "item": item,
            "text": text, "text_sel": text_sel, "show_shaded": "=FALSE", "shadetop": "=0", "shadedown": "=0", "roundness": "=" + roundness}


GENERIC_SPACE = {"back": "surface", "title": "text", "text": "text", "text_hi": "text_hi", "header": "canvas",
                 "header_text": "muted", "header_text_hi": "text_hi"}

RULES = {
    "user_interface": {
        "menu_shadow_fac": "=0.5", "menu_shadow_width": "=10", "icon_alpha": "=1", "icon_saturation": "=0.3",
        "widget_emboss": "shadow@33", "link": "accent_text", "editor_border": "canvas", "editor_outline": "line@99",
        "editor_outline_active": "line_hi@99", "widget_text_cursor": "accent", "panel_roundness": "=0.4",
        "panel_header": "surface", "panel_title": "text", "panel_text": "text", "panel_back": "surface",
        "panel_sub_back": "canvas@40", "panel_outline": "line@00", "panel_active": "accent",
        "transparent_checker_primary": "=#3A3D45", "transparent_checker_secondary": "=#24272F", "transparent_checker_size": "=8",
        "axis_x": "@upstream", "axis_y": "@upstream", "axis_z": "@upstream", "axis_w": "@upstream",
        "gizmo_hi": "text_hi", "gizmo_primary": "accent", "gizmo_secondary": "agent", "gizmo_view_align": "text",
        "gizmo_a": "agent", "gizmo_b": "stop",
        "icon_scene": "text", "icon_collection": "text", "icon_object": "accent_hi", "icon_object_data": "go",
        "icon_modifier": "agent", "icon_shading": "stop", "icon_folder": "muted", "icon_autokey": "stop",
        "icon_border_intensity": "=0.25",
        # the fork's own slots (interface_mixar_theme.cc:27-117): painted chrome, the island, Cinema, the toolbar
        "mixar_canvas": "canvas", "mixar_panel": "surface", "mixar_input": "well", "mixar_control": "raised",
        "mixar_selected": "accent_bed", "mixar_text": "text", "mixar_text_strong": "text_hi", "mixar_text_secondary": "muted",
        "mixar_border": "line", "mixar_focus": "accent", "mixar_primary": "accent_bed_hi", "mixar_danger": "stop",
        "mixar_warning": "accent", "mixar_action": "surface", "mixar_glyph": "text", "mixar_chip": "raised",
        "mixar_chip_active": "accent_bed", "mixar_gray_800": "well", "mixar_gray_700": "raised",
        "mixar_border_strong": "line_hi", "mixar_bg": "surface", "mixar_fg_1": "text", "mixar_fg_2": "text_dim",
        "mixar_fg_3": "muted", "mixar_fg_4": "muted_dim", "mixar_pane_wash": "surface", "mixar_brand": "accent",
        "mixar_brand_text": "on_accent", "mixar_queue": "line", "mixar_queue_count": "muted_dim",
        "mixar_slider_track": "well", "mixar_slider_thumb": "accent", "mixar_slider_thumb_hover": "accent_hi",
        "mixar_slider_label": "text", "mixar_cinema_pill_border": "line@00", "mixar_cinema_pill_on_a": "accent_bed",  # Cinema: no pill border (contract 03)
        "mixar_cinema_pill_on_b": "accent_bed_hi", "mixar_cinema_pill_border_on": "accent",
        "mixar_cinema_pill_label": "muted_dim", "mixar_cinema_pill_label_on": "text_hi",
        "mixar_viewport_fill": "well", "mixar_viewport_border": "line", "mixar_viewport_label": "muted",
        "mixar_viewport_label_on": "text", "mixar_profile_label": "text", "mixar_profile_avatar": "raised_hi",
        "mixar_profile_glyph": "text_dim", "mixar_cinema_row_top": "raised_hi", "mixar_cinema_row_bottom": "surface",
        "mixar_cinema_row_hover": "raised_hi", "mixar_cinema_row_track": "well", "mixar_cinema_row_text_on": "text_hi",
        "mixar_cinema_row_text_off": "text_dim", "mixar_cinema_row_text_disabled": "muted_dim",
        "mixar_cinema_row_caption": "muted@D9", "mixar_cinema_row_slider_on": "accent",
        "mixar_cinema_card_top": "raised@F5", "mixar_cinema_card_bottom": "surface@F5", "mixar_cinema_label": "muted",
        "mixar_cinema_dimmer": "line", "mixar_cinema_keycap": "muted_dim", "mixar_cinema_phone": "line",
        "mixar_cinema_chip": "line", "mixar_cinema_brand_top": "canvas", "mixar_cinema_brand_bottom": "accent_bed",
        "mixar_widget_border": "line", "mixar_ink": "text_hi", "mixar_sunken": "well",
        # Generate: no gradient (BRAND.md 5.4); four equal stops on the lamplit bed so text_hi clears 4.5:1
        "mixar_gradient_start": "accent_bed_hi", "mixar_gradient_mid_a": "accent_bed_hi",
        "mixar_gradient_mid_b": "accent_bed_hi", "mixar_gradient_end": "accent_bed_hi",
        "mixar_toolbar_background": "surface", "mixar_toolbar_border": "line", "mixar_toolbar_primary": "accent_bed",
        "mixar_toolbar_primary_border": "accent", "mixar_toolbar_text": "text", "mixar_toolbar_muted": "muted_dim",
        "mixar_toolbar_selected": "accent_bed", "mixar_glass_wash": "canvas@33", "mixar_sketch_ink": "muted_dim",
        # RNA hides these five from presets (PROP_HIDDEN | PROP_SKIP_SAVE), so no XML carries them: only the compiled
        # default does (emit_native). Each follows the visible slot it sits beside.
        "mixar_pane_pill_dim": "line", "mixar_pane_pill_on": "accent_bed", "mixar_cinema_pill_fill": "well",
        "mixar_profile_fill": "surface", "mixar_cinema_gate_fill": "text@12",
    },
    "user_interface/wcol_regular": widget("raised", "accent_bed", outline="raised", text_sel="text_hi"),
    "user_interface/wcol_tool": widget("raised", "accent_bed", outline="raised", text_sel="text_hi"),
    "user_interface/wcol_toolbar_item": widget("surface", "accent_bed", outline="line@00", text_sel="text_hi", roundness="0.3"),
    "user_interface/wcol_radio": widget("well", "accent_bed", outline="well", outline_sel="accent_bed", text_sel="accent_text"),
    "user_interface/wcol_text": widget("well", "raised_hi", outline="well", item="accent@66", roundness="0.3"),
    "user_interface/wcol_option": widget("well", "accent", item="on_accent", roundness="0.3"),
    "user_interface/wcol_toggle": widget("raised", "accent_bed", outline="raised", outline_sel="accent_bed", text_sel="accent_text"),
    "user_interface/wcol_num": widget("well", "raised_hi", outline="well", roundness="0.3"),
    "user_interface/wcol_numslider": widget("well", "raised_hi", outline="well", item="accent_bed_hi", roundness="0.3"),
    "user_interface/wcol_box": widget("surface", "accent_bed", outline="line@00", roundness="0.25"),
    "user_interface/wcol_curve": widget("well", "accent_bed", item="text"),
    "user_interface/wcol_menu": widget("raised", "raised_hi", outline="raised"),
    "user_interface/wcol_pulldown": widget("raised_hi", "raised_hi", outline="line@00", text_sel="text_hi"),
    "user_interface/wcol_menu_back": widget("raised@F7", "accent_bed", outline="line_hi", roundness="0.25"),
    "user_interface/wcol_pie_menu": widget("raised@EE", "accent_bed", item="accent", outline="line_hi"),
    "user_interface/wcol_tooltip": widget("canvas@F7", "raised", outline="line_hi", roundness="0.25"),
    "user_interface/wcol_menu_item": widget("raised@00", "accent_bed", outline="line@00", text_sel="text_hi", roundness="0.25"),
    "user_interface/wcol_scroll": widget("surface@00", "raised_hi", outline="line@00", item="line_hi", roundness="1"),
    "user_interface/wcol_progress": widget("well", "raised_hi", item="accent", roundness="1"),
    "user_interface/wcol_list_item": widget("surface@00", "accent_bed", outline="line@00", text_sel="text_hi", roundness="0.3"),
    "user_interface/wcol_tab": widget("canvas", "canvas", outline="line@00", item="accent", text="muted", text_sel="text_hi", roundness="0.4"),  # text with an amber underline (contract 03)
    "user_interface/wcol_state": {
        "error": "stop_bed", "warning": "accent_bed_hi", "info": "agent_bed", "success": "go_bed",
        "inner_anim": "@upstream", "inner_anim_sel": "@upstream", "inner_key": "@upstream", "inner_key_sel": "@upstream",
        "inner_driven": "@upstream", "inner_driven_sel": "@upstream", "inner_overridden": "@upstream",
        "inner_overridden_sel": "@upstream", "inner_changed": "@upstream", "inner_changed_sel": "@upstream", "blend": "=0.5",
    },
    "regions/asset_shelf": {"back": "surface@E6", "header_back": "canvas"},
    "regions/channels": {"back": "surface", "text": "text", "text_selected": "accent_hi"},
    "regions/scrubbing": {"back": "canvas", "text": "muted", "time_marker": "text@80", "time_marker_selected": "accent"},
    "regions/sidebars": {"back": "surface@E6", "tab_back": "canvas@F0"},
    "common/anim": {
        "playhead": "accent", "preview_range": "agent@33", "scene_strip_range": "canvas@80", "channels": "agent_bed@B3",
        "channels_sub": "agent_bed@80", "channel_group": "accent_bed@80", "channel_group_active": "accent_bed_hi@B3",
        "channel": "raised@99", "channel_selected": "accent@44", "keyframe": "text_dim", "keyframe_selected": "accent_hi",
        "keyframe_extreme": "@upstream", "keyframe_extreme_selected": "@upstream", "keyframe_breakdown": "@upstream",
        "keyframe_breakdown_selected": "@upstream", "keyframe_jitter": "@upstream", "keyframe_jitter_selected": "@upstream",
        "keyframe_moving_hold": "muted_dim", "keyframe_moving_hold_selected": "accent", "keyframe_generated": "muted_dim",
        "keyframe_generated_selected": "accent_bed_hi", "long_key": "text@1F", "long_key_selected": "accent@99",
    },
    "common/curves": {k: "@upstream" for k in (
        "handle_free", "handle_sel_free", "handle_auto", "handle_sel_auto", "handle_vect", "handle_sel_vect", "handle_align",
        "handle_sel_align", "handle_auto_clamped", "handle_sel_auto_clamped", "handle_vertex", "handle_vertex_select")},
    "view_3d": {
        "grid": "accent@14", "grid_major": "accent@26", "grid_axis_brightness": "=0.45", "clipping_border_3d": "canvas",
        "wire": "muted_dim", "wire_edit": "=#000000", "edge_width": "=1", "gp_wire_edit": "muted@80", "gp_vertex": "=#000000",
        "gp_vertex_select": "accent", "text_grease_pencil": "accent_hi", "object_selected": "accent",
        "object_active": "accent_hi", "camera": "muted", "empty": "muted", "light": "muted@CC", "speaker": "muted",
        "vertex": "=#000000", "vertex_select": "accent", "edge_select": "accent", "edge_mode_select": "accent_hi",
        "face": "text@05", "face_select": "accent@38", "face_mode_select": "accent@22", "face_back": "@upstream",
        "face_front": "@upstream", "bevel": "agent", "seam": "@upstream", "sharp": "agent", "crease": "@upstream",
        "freestyle": "@upstream", "extra_edge_len": "@upstream", "extra_edge_angle": "@upstream",
        "extra_face_angle": "@upstream", "extra_face_area": "@upstream", "editmesh_active": "text@40", "normal": "agent",
        "vertex_normal": "@upstream", "split_normal": "@upstream", "vertex_unreferenced": "=#000000",
        "face_retopology": "agent@1A", "nurb_uline": "@upstream", "nurb_vline": "@upstream", "nurb_sel_uline": "@upstream",
        "nurb_sel_vline": "@upstream", "bone_pose": "agent", "bone_pose_active": "text_hi", "bone_solid": "text_dim",
        "bone_locked_weight": "stop@80", "before_current_frame": "stop", "after_current_frame": "go", "bundle_solid": "text_dim",
        "camera_path": "=#000000", "camera_passepartout": "=#000000", "skin_root": "@upstream", "view_overlay": "=#000000",
        "transform": "text", "outline_width": "=2", "object_origin_size": "=5", "vertex_size": "=3", "facedot_size": "=3",
        "gp_vertex_size": "=3",
    },
    "view_3d/space": {"title": "text", "text": "text", "text_hi": "text_hi", "header": "canvas", "header_text": "muted",
                      "header_text_hi": "text_hi"},
    "view_3d/space/gradients": {"background_type": "=RADIAL", "high_gradient": "viewport_hi", "gradient": "viewport_lo"},
    "graph_editor": {"grid": "line", "vertex": "=#000000", "vertex_select": "accent", "vertex_active": "text_hi", "vertex_size": "=6"},
    "file_browser": {"selected_file": "accent_bed", "row_alternate": "text@03"},
    "nla_editor": {
        "grid": "line", "active_action": "accent@66", "active_action_unset": "muted@4D", "strips": "raised",
        "strips_selected": "accent", "transition_strips": "agent_bed", "transition_strips_selected": "agent",
        "meta_strips": "raised_hi", "meta_strips_selected": "agent", "sound_strips": "@upstream_seq_audio",
        "sound_strips_selected": "go", "tweak": "go", "tweak_duplicate": "stop", "keyframe_border": "=#000000ff",
        "keyframe_border_selected": "=#000000ff"},
    "dopesheet_editor": {
        "grid": "line", "keyframe_border": "=#000000ff", "keyframe_border_selected": "=#000000ff", "keyframe_scale_factor": "=1",
        "summary": "agent_bed@66", "anim_interpolation_linear": "go@CC", "anim_interpolation_constant": "stop@CC",
        "anim_interpolation_other": "agent@B3", "simulated_frames": "agent@66"},   # contract 12: the wire is data leaving only
    "image_editor": {
        "grid": "line_hi", "vertex": "=#000000", "vertex_select": "accent", "vertex_size": "=3", "face": "text@0A",
        "face_select": "accent@3C", "face_mode_select": "accent@00", "facedot_size": "=3", "editmesh_active": "text@40",
        "wire_edit": "text_dim", "edge_width": "=1", "edge_select": "accent", "scope_back": "raised",
        "preview_stitch_face": "@upstream", "preview_stitch_edge": "@upstream", "preview_stitch_vert": "@upstream",
        "preview_stitch_stitchable": "@upstream", "preview_stitch_unstitchable": "@upstream", "preview_stitch_active": "@upstream",
        "uv_shadow": "muted_dim", "metadatabg": "=#000000", "metadatatext": "=#ffffff"},
    "sequence_editor": {
        "grid": "line", "movie_strip": "@upstream", "movieclip_strip": "@upstream", "image_strip": "@upstream",
        "scene_strip": "@upstream", "audio_strip": "@upstream", "effect_strip": "@upstream", "transition_strip": "@upstream",
        "color_strip": "@upstream", "meta_strip": "@upstream", "mask_strip": "@upstream", "text_strip": "@upstream",
        "active_strip": "text_hi", "selected_strip": "accent", "keyframe_border": "=#000000ff",
        "keyframe_border_selected": "=#000000ff", "preview_back": "=#000000", "metadatabg": "=#000000", "metadatatext": "=#ffffff",
        "row_alternate": "text@0D", "text_strip_cursor": "accent", "selected_text": "accent@4D"},
    "properties": {"match": "accent"},
    "text_editor": {
        "line_numbers": "muted_dim", "line_numbers_background": "canvas", "selected_text": "accent_bed", "cursor": "accent",
        "syntax_builtin": "agent", "syntax_symbols": "text_dim", "syntax_special": "accent_hi", "syntax_preprocessor": "=#C49BF0",
        "syntax_reserved": "stop", "syntax_comment": "muted_dim", "syntax_string": "go", "syntax_numbers": "=#6FC3E8"},
    "node_editor": {
        "grid": "line", "node_outline": "text@26", "node_selected": "accent", "node_active": "accent_hi", "wire": "canvas",
        "wire_inner": "muted", "wire_select": "accent_hi@B3", "node_backdrop": "raised@E6", "converter_node": "@upstream",
        "color_node": "@upstream", "group_node": "@upstream", "group_socket_node": "@upstream", "frame_node": "canvas@CC",
        "matte_node": "@upstream", "distor_node": "@upstream", "noodle_curving": "=4", "grid_levels": "=2", "dash_alpha": "=0.5",
        "input_node": "@upstream", "output_node": "@upstream", "filter_node": "@upstream", "vector_node": "@upstream",
        "texture_node": "@upstream", "shader_node": "@upstream", "script_node": "@upstream", "geometry_node": "@upstream",
        "attribute_node": "@upstream", "simulation_zone": "@upstream", "repeat_zone": "@upstream",
        "foreach_geometry_element_zone": "@upstream", "closure_zone": "@upstream"},
    "outliner": {"match": "accent", "selected_highlight": "accent_bed", "active": "accent_bed_hi", "selected_object": "accent_hi",
                 "active_object": "accent", "edited_object": "accent@40", "row_alternate": "text@03"},
    "info": {"info_selected": "accent_bed", "info_selected_text": "text_hi", "info_error_text": "text_hi",
             "info_warning_text": "text_hi", "info_info_text": "text_hi", "info_debug": "raised_hi", "info_debug_text": "text",
             "info_property": "agent_bed", "info_property_text": "text", "info_operator": "go_bed", "info_operator_text": "text"},
    "preferences": {"match": "accent"},
    "console": {"line_output": "text_dim", "line_input": "text", "line_info": "agent", "line_error": "stop", "cursor": "accent",
                "select": "accent@30"},
    "clip_editor": {"grid": "line_hi", "marker_outline": "=#000000", "marker": "@upstream", "active_marker": "=#ffffff",
                    "selected_marker": "accent", "disabled_marker": "@upstream", "locked_marker": "@upstream",
                    "path_before": "@upstream", "path_after": "@upstream", "path_keyframe_before": "@upstream",
                    "path_keyframe_after": "@upstream", "metadatabg": "=#000000", "metadatatext": "=#ffffff"},
    "spreadsheet": {"row_alternate": "text@03"},
    "mixie_chat": {
        "chat_user_bubble": "raised", "chat_agent_bubble": "surface", "chat_bubble_hover": "accent@14",
        "chat_user_text": "text", "chat_agent_text": "text", "chat_input_bg": "well", "chat_button_bg": "raised",
        "chat_button_text": "text", "chat_button_hover": "raised_hi", "chat_history_row_hover": "text@12",
        "chat_label_color": "muted", "chat_mode_button": "raised", "chat_mode_button_active": "accent_bed",
        "chat_plan_toggle_on": "accent_bed_hi", "chat_placeholder_text": "muted_dim", "chat_prompt_button": "raised",
        "chat_thumbnail_border": "line_hi", "chat_send_icon_gradient_start": "accent", "chat_send_icon_gradient_end": "accent",
        "chat_send_arrow_color": "on_accent",
        "chat_font_size": "=13.5", "chat_label_font_size": "=10", "chat_padding": "=14", "chat_bubble_h_padding": "=14",
        "chat_bubble_v_padding": "=10", "chat_corner_radius": "=10", "chat_image_max_width": "=160", "chat_image_max_height": "=160",
        "chat_image_margin": "=8", "chat_image_corner_radius": "=8", "chat_thumbnail_border_radius": "=8",
        "chat_thumbnail_padding": "=4", "chat_action_button_height": "=24", "chat_action_button_padding": "=10",
        "chat_action_button_spacing": "=6", "chat_action_button_corner_radius": "=5"},
    "mixie_chat/space": dict(GENERIC_SPACE, back="surface"),
    "mixie": {
        "mixar_tab_accent": "accent_bed", "mixar_tab_strip_background": "canvas@F2", "mixar_tab_inactive": "line@99",
        "mixar_tab_text_active": "text_hi", "mixar_tab_text_inactive": "muted", "mixar_tab_glow": "accent@26",
        "mixar_tab_highlight": "text@2E", "mixar_tab_indicator": "accent@66", "mixar_action_button": "raised",
        "mixar_toggle_active": "accent_bed", "moodboard_button_background": "raised", "moodboard_button_hover": "raised_hi",
        "moodboard_button_text": "text", "moodboard_corner_radius": "=8", "moodboard_input_background": "well",
        "moodboard_input_border": "line", "moodboard_input_border_width": "=1", "moodboard_input_text": "text",
        "moodboard_label_text": "muted", "moodboard_panel_background": "surface"},
    "mixie/space": dict(GENERIC_SPACE, back="canvas"),
    "agent_bubble": {"footer_background": "canvas", "background_alpha": "=1", "agent_border": "line_hi",
                     "agent_tab_active": "accent_bed", "agent_accent": "accent"},
    "agent_bubble/space": dict(GENERIC_SPACE, back="canvas"),
    "bone_color_sets": {"normal": "@upstream", "select": "@upstream", "active": "@upstream", "show_colored_constraints": "=FALSE"},
    "collection_color": {"color": "@upstream"},
    "strip_color": {"color": "@upstream"},
    "style/panel_title": {"points": "=11.5", "character_weight": "=600", "shadow": "=0", "shadow_offset_x": "=0",
                          "shadow_offset_y": "=-1", "shadow_alpha": "=0.3", "shadow_value": "=0"},
    "style/widget": {"points": "=11", "character_weight": "=400", "shadow": "=0", "shadow_offset_x": "=0",
                     "shadow_offset_y": "=-1", "shadow_alpha": "=0.3", "shadow_value": "=0"},
    "style/tooltip": {"points": "=11", "character_weight": "=400", "shadow": "=0", "shadow_offset_x": "=0",
                      "shadow_offset_y": "=-1", "shadow_alpha": "=0.3", "shadow_value": "=0"},
}

# Literal colours, each with its reason (check_theme.py refuses a literal that is not listed here).
KEPT = {
    "#000000": "Blender's functional black (unselected vertices, wire_edit, metadata, passepartout); not a brand colour",
    "#000000ff": "keyframe borders: Blender's functional black",
    "#ffffff": "metadata text and the active clip marker: Blender's functional white",
    "#3A3D45": "transparency checker: neutral grey pair, never brand-tinted so a texture's own colour reads true",
    "#24272F": "transparency checker: neutral grey pair",
    "#C49BF0": "text editor preprocessor: a code-syntax hue with no token (syntax colours are a domain palette)",
    "#6FC3E8": "text editor numbers: the Sky worker colour reused as a syntax hue",
}

LIGHT_OVERRIDES = {   # where the light theme needs a different rule, not just a different token value
    "view_3d": {"grid": "on_accent@14", "grid_major": "on_accent@26", "wire": "muted"},
    "user_interface/wcol_option": {"item": "on_accent"},
    "user_interface/wcol_tab": {"inner": "canvas", "inner_sel": "canvas"},
}

# ----------------------------------------------------------------------------------------------- machinery
class Unmapped(Exception):
    pass


def container_key(stack):
    return "/".join(t for t in stack if t[0].islower())


def resolve(spec, attr, key, index, variant, size, upstream):
    """Return (hex-or-literal, provenance)."""
    if spec.startswith("="):
        val = spec[1:]
        if val.startswith("#"):
            if val not in KEPT:
                raise Unmapped(f"{key}.{attr}: literal {val} has no KEPT reason")
            return fmt(val, size), "kept:" + val
        return val, "metric"
    if spec.startswith("@upstream"):
        if spec == "@upstream_seq_audio":
            up = upstream.get(("sequence_editor", 0)).get("audio_strip")
        else:
            up = (upstream.get((key, index)) or {}).get(attr)
        if up is None:
            raise Unmapped(f"{key}[{index}].{attr}: no upstream value at this path")
        return fmt(up, size), "domain:upstream Blender_Light 5.2"
    name, _, alpha = spec.partition("@")
    tok = TOKENS["colour"].get(name)
    if tok is None:
        raise Unmapped(f"{key}.{attr}: unknown token {name!r}")
    hx = tok[variant]
    if alpha:
        hx = hx + alpha.lower()
    return fmt(hx, size), "token:" + spec


def fmt(hx, size):
    hx = hx.lower()
    body = hx[1:]
    if size == 3:
        return "#" + body[:6]
    if size == 4:
        return "#" + (body + "ff")[:8] if len(body) == 6 else "#" + body
    return hx


def load_upstream():
    """(container key, index) -> attrs, from upstream's preset (domain conventions only)."""
    out = {}
    root = ET.parse(UPSTREAM).getroot()

    def walk(el, stack, counters):
        if el.tag[0].isupper() and el.tag not in ("Theme", "ThemeStyle"):
            key = container_key(stack)
            idx = counters.get(key, 0)
            counters[key] = idx + 1
            out[(key, idx)] = dict(el.attrib)
        for ch in el:
            walk(ch, stack + [ch.tag] if ch.tag[0].islower() else stack + [ch.tag], counters)

    walk(root.find("Theme"), [], {})
    return out


def build(variant):
    upstream = load_upstream()
    tree = ET.parse(BASE)
    root = tree.getroot()
    prov = {}
    counters = {}
    rules = {k: dict(v) for k, v in RULES.items()}
    if variant == "light":
        for k, v in LIGHT_OVERRIDES.items():
            rules.setdefault(k, {}).update(v)

    def walk(el, stack):
        if el.tag[0].isupper() and el.tag not in ("Theme", "ThemeStyle"):
            key = container_key(stack)
            idx = counters.get(key, 0)
            counters[key] = idx + 1
            struct = SCHEMA[el.tag]
            rule = rules.get(key)
            if rule is None and el.tag == "ThemeSpaceGeneric":
                rule = GENERIC_SPACE
            if rule is None and el.attrib:
                raise Unmapped(f"no rule for container {key!r} ({el.tag})")
            rule = rule or {}
            for attr in list(el.attrib):
                info = struct.get(attr)
                if info is None:
                    raise Unmapped(f"{key}.{attr}: not in the 5.2 schema")
                spec = rule.get(attr)
                if spec is None:
                    if el.tag == "ThemeSpaceGeneric" and attr in GENERIC_SPACE:
                        spec = GENERIC_SPACE[attr]
                    elif info["type"] == "FLOAT" and info.get("size") in (3, 4):
                        raise Unmapped(f"{key}.{attr}: colour with no rule")
                    else:
                        prov[f"{key}[{idx}].{attr}"] = "keep:base metric"
                        continue
                val, src = resolve(spec, attr, key, idx, variant, info.get("size", 0), upstream)
                el.set(attr, val)
                prov[f"{key}[{idx}].{attr}"] = src
        for ch in el:
            walk(ch, stack + [ch.tag])

    walk(root.find("Theme"), [])
    style = root.find("ThemeStyle")
    for ch in style:
        fs = ch.find("ThemeFontStyle")
        key = "style/" + ch.tag
        for attr, spec in rules[key].items():
            fs.set(attr, resolve(spec, attr, key, 0, variant, 0, upstream)[0])
            prov[f"{key}[0].{attr}"] = "metric"
    return tree, prov


HEADER = """<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- {title}. GENERATED by theme/build_theme.py from theme/tokens.json over the 0.1.0 build's default theme
     (Blender 5.2.0 schema). Do not edit by hand: change tokens.json or the rules, rebuild, run check_theme.py. -->
"""


def serialise(el, depth=0):
    """Blender's own layout (_rna_xml.xml_file_write): one attribute per line, so a diff names the attribute."""
    pad = "  " * depth
    if not el.attrib and not len(el):
        return f"{pad}<{el.tag}>\n{pad}</{el.tag}>\n"
    out = f"{pad}<{el.tag}"
    if el.attrib:
        out += "\n" + "".join(f'{pad}    {k}="{v}"\n' for k, v in el.attrib.items()) + f"{pad}    >\n"
    else:
        out += ">\n"
    for ch in el:
        out += serialise(ch, depth + 1)
    return out + f"{pad}</{el.tag}>\n"


def write(variant, path, title):
    tree, prov = build(variant)
    body = serialise(tree.getroot())
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(HEADER.format(title=title) + "\n" + body)
    with open(path.replace(".xml", ".provenance.json"), "w") as fh:
        json.dump(prov, fh, indent=1, sort_keys=True)
    return len(prov)


# ----------------------------------------------------------------------------------------------- WezTerm (contract 16)
WEZ_ANSI = {   # ANSI slots from the tokens; `wire` is NOT an ANSI colour (it is reserved for egress), magenta is Orchid
    "dark": {"ansi": ["canvas", "stop", "go", "accent", "agent", "#D58FE0", "#6FC3E8", "text_dim"],
             "brights": ["muted_dim", "#F59A91", "#7FD6A8", "accent_hi", "#B9BBFA", "#E2AEEA", "#97D5F0", "text_hi"]},
    "light": {"ansi": ["text", "stop", "go", "accent_text", "agent", "#8A3A96", "#1F6E8C", "line_hi"],
              "brights": ["muted", "#C9483C", "#2A8F5C", "#A06A00", "#5A5CC8", "#A04AAE", "#2A86A8", "surface"]},
}
CUES = [  # DESIGN.md 13: agent state -> glyph, token. The same table drives the WezTerm tab bar.
    ("idle", "\u25cb", "muted_dim"), ("working", "\u25d4", "accent_text"), ("unread", "\u25cf", "agent"),
    ("blocked", "\u25c6", "accent_text"), ("paused", "\u25cc", "muted"), ("done", "\u2713", "go"), ("failed", "\u2715", "stop"),
]


def _c(v, variant):
    return v if v.startswith("#") else TOKENS["colour"][v][variant]


def wezterm_lua():
    def scheme(variant):
        t = lambda n: TOKENS["colour"][n][variant]  # noqa: E731
        a = WEZ_ANSI[variant]
        return f"""{{
    foreground = '{t("text")}', background = '{t("canvas")}',
    cursor_bg = '{t("accent")}', cursor_fg = '{t("on_accent")}', cursor_border = '{t("accent")}',
    selection_bg = '{t("accent_bed_hi")}', selection_fg = '{t("text_hi")}',
    scrollbar_thumb = '{t("line_hi")}', split = '{t("line")}', compose_cursor = '{t("agent")}',
    ansi = {{ {", ".join(repr(_c(x, variant)) for x in a["ansi"])} }},
    brights = {{ {", ".join(repr(_c(x, variant)) for x in a["brights"])} }},
    tab_bar = {{
      background = '{t("canvas")}',
      active_tab = {{ bg_color = '{t("surface")}', fg_color = '{t("text_hi")}' }},
      inactive_tab = {{ bg_color = '{t("canvas")}', fg_color = '{t("muted")}' }},
      inactive_tab_hover = {{ bg_color = '{t("raised")}', fg_color = '{t("text")}' }},
      new_tab = {{ bg_color = '{t("canvas")}', fg_color = '{t("muted_dim")}' }},
      new_tab_hover = {{ bg_color = '{t("raised")}', fg_color = '{t("text")}' }},
    }},
  }}"""
    cues = ",\n".join(f"  {k} = {{ glyph = '{g}', dark = '{TOKENS['colour'][c]['dark']}', light = '{TOKENS['colour'][c]['light']}' }}" for k, g, c in CUES)
    wire = TOKENS["colour"]["wire"]
    return f"""-- SPDX-FileCopyrightText: 2026 Lampway contributors
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Lampway's own WezTerm configuration (contract 16). GENERATED by theme/build_theme.py from theme/tokens.json; do not edit.
-- Loaded ONLY through `wezterm --config-file <this file>`: it never reads, writes or includes the user's ~/.wezterm.lua.
-- Everything it reads lives under $LAMPWAY_HOME (the launcher always sets it).
local wezterm = require 'wezterm'
local config = wezterm.config_builder and wezterm.config_builder() or {{}}
local home = os.getenv('LAMPWAY_HOME') or error('LAMPWAY_HOME is not set: start the terminal from Lampway')
local variant = (os.getenv('LAMPWAY_THEME') == 'paper') and 'light' or 'dark'

config.color_schemes = {{
  ['Lampway Night'] = {scheme("dark")},
  ['Lampway Paper'] = {scheme("light")},
}}
config.color_scheme = (variant == 'light') and 'Lampway Paper' or 'Lampway Night'

-- type (decision F1: Inter for the UI, Plex Mono for every number and every terminal)
config.font_dirs = {{ home .. '/addons/wezterm/fonts' }}
config.font = wezterm.font_with_fallback({{ 'IBM Plex Mono', 'DejaVu Sans Mono' }})
config.font_size = 11.5
config.line_height = 1.15

-- calm by default: no bell, no blinking, no update check (that would be an unannounced network call)
config.check_for_updates = false
config.automatically_reload_config = false
config.audible_bell = 'Disabled'
config.visual_bell = {{ fade_in_duration_ms = 0, fade_out_duration_ms = 0 }}
config.cursor_blink_rate = 0
config.default_cursor_style = 'SteadyBar'
config.enable_kitty_graphics = true
config.window_padding = {{ left = 14, right = 14, top = 10, bottom = 8 }}
config.use_fancy_tab_bar = false
config.tab_max_width = 36
config.hide_tab_bar_if_only_one_tab = false
config.status_update_interval = 1000
config.unix_domains = {{}}
config.ssh_domains = {{}}

-- glance cues (DESIGN.md 13): one glyph per agent state, the token colour; nothing in the tab bar moves
local CUES = {{
{cues}
}}
local WIRE_COLOUR = {{ dark = '{wire["dark"]}', light = '{wire["light"]}' }}
local WIRE_BED = {{ dark = '{TOKENS["colour"]["wire_bed"]["dark"]}', light = '{TOKENS["colour"]["wire_bed"]["light"]}' }}
local MUTED = {{ dark = '{TOKENS["colour"]["muted"]["dark"]}', light = '{TOKENS["colour"]["muted"]["light"]}' }}
local TEXT_HI = {{ dark = '{TOKENS["colour"]["text_hi"]["dark"]}', light = '{TOKENS["colour"]["text_hi"]["light"]}' }}

-- state written by the Lampway server: {{ panes = {{ ["<wezterm pane id>"] = {{ state = 'working', name = '...' }} }},
--                                        egress = {{ state = 'idle'|'open'|'live', route = '...', size = '...' }} }}
local STATE_FILE = home .. '/wezterm/state.json'
local cached, cached_at = {{ panes = {{}}, egress = {{ state = 'idle' }} }}, -1
local function state()
  local now = os.time()
  if now ~= cached_at then
    cached_at = now
    local f = io.open(STATE_FILE, 'r')
    if f then
      local ok, parsed = pcall(wezterm.json_parse, f:read('*a'))
      f:close()
      if ok and type(parsed) == 'table' then cached = parsed end
    end
  end
  return cached
end

wezterm.on('format-tab-title', function(tab)
  local pane = tab.active_pane
  local s = (state().panes or {{}})[tostring(pane.pane_id)] or {{}}
  local cue = CUES[s.state or 'idle'] or CUES.idle
  local name = s.name or pane.title
  return {{
    {{ Foreground = {{ Color = cue[variant] }} }}, {{ Text = ' ' .. cue.glyph .. ' ' }},
    {{ Foreground = {{ Color = tab.is_active and TEXT_HI[variant] or MUTED[variant] }} }}, {{ Text = name .. ' ' }},
  }}
end)

wezterm.on('update-status', function(window)
  local e = state().egress or {{ state = 'idle' }}
  if e.state == 'live' then
    window:set_right_status(wezterm.format({{
      {{ Background = {{ Color = WIRE_BED[variant] }} }}, {{ Foreground = {{ Color = WIRE_COLOUR[variant] }} }},
      {{ Text = ' \u21e2 Sending to ' .. (e.route or '?') .. ', ' .. (e.size or '') .. ' ' }},
    }}))
  elseif e.state == 'open' then
    window:set_right_status(wezterm.format({{ {{ Foreground = {{ Color = MUTED[variant] }} }}, {{ Text = ' \u21e2 ' .. (e.open or '') .. ' ' }} }}))
  else
    window:set_right_status(wezterm.format({{ {{ Foreground = {{ Color = MUTED[variant] }} }}, {{ Text = ' local ' }} }}))
  end
end)

-- images (contract 16, section 6.7): inline images do not cross herdr (measured live 2026-10-06, the iTerm2 and kitty
-- protocols both), so an image path in a pane's output is a link; a click appends it to a queue under $LAMPWAY_HOME that
-- Blender drains into its Image Editor. Only Lampway's own links are taken here; every other link opens as before.
local SHOW_QUEUE = home .. '/wezterm/show_in_blender.jsonl'
config.hyperlink_rules = wezterm.default_hyperlink_rules()
table.insert(config.hyperlink_rules, {{ regex = [[(?i)(/[^\\s'"`<>|]+\\.(?:png|jpe?g|exr|webp|tga|tiff?|bmp))\\b]], format = 'lampway-image:$1' }})
-- herdr takes the mouse (its panes report clicks), so a plain click goes to herdr; Ctrl+click opens a link in either mode
config.mouse_bindings = {{}}
for _, reporting in ipairs({{ false, true }}) do
  table.insert(config.mouse_bindings, {{ event = {{ Up = {{ streak = 1, button = 'Left' }} }}, mods = 'CTRL', mouse_reporting = reporting,
                                        action = wezterm.action.OpenLinkAtMouseCursor }})
  table.insert(config.mouse_bindings, {{ event = {{ Down = {{ streak = 1, button = 'Left' }} }}, mods = 'CTRL', mouse_reporting = reporting,
                                        action = wezterm.action.Nop }})
end
wezterm.on('open-uri', function(window, pane, uri)
  local path = uri:match('^lampway%-image:(.+)$')
  if not path then return end
  local f = io.open(SHOW_QUEUE, 'a')
  if f then
    f:write(wezterm.json_encode({{ path = path, at = os.time() }}) .. '\\n')
    f:close()
  end
  return false
end)

return config
"""


def write_wezterm(path):
    text = wezterm_lua().replace("local WIRE = ''\n", "")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


ROOT_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
TOKENS_CSS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "server", "lampway_server", "web", "workbench", "tokens.css"))


def tokens_css() -> str:
    """The tokens as CSS custom properties for the cockpit's page (facelift contract 10): the browser window and the Blender UI
    share one source. Night only: the page is the Night canvas (`--lw-<token>`)."""
    lines = ["/* SPDX-FileCopyrightText: 2026 Lampway contributors */", "/* SPDX-License-Identifier: GPL-3.0-or-later */",
             "/* GENERATED by scripts/lampway/facelift/theme/build_theme.py from theme/tokens.json; do not edit. */", ":root {"]
    lines += [f"  --lw-{name}: {v['dark'].lower()};" for name, v in TOKENS["colour"].items()]
    return "\n".join(lines + ["}", ""])


def write_tokens_css(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(tokens_css())


# ----------------------------------------------------------------------------------------------- the compiled defaults
# Lampway Night is the default theme (contract 01 6.3/6.4): what a new profile starts with, what "Reset to Default"
# gives back, and what the fork's painters fall back to are generated from the same rules as the preset.
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
DNA_MAP = os.path.join(HERE, "base", "theme_dna_0.1.0.json")   # measured by dump_theme_dna.py
NATIVE = {
    "userdef_default_theme.c": os.path.join(ROOT, "src", "release", "datafiles", "userdef", "userdef_default_theme.c"),
    "interface_mixar_theme.cc": os.path.join(ROOT, "src", "source", "blender", "editors", "interface",
                                             "interface_mixar_theme.cc"),
    "UI_mixar_tokens.hh": os.path.join(ROOT, "src", "source", "blender", "editors", "include", "UI_mixar_tokens.hh"),
    "rna_userdef.cc": os.path.join(ROOT, "src", "source", "blender", "makesrna", "intern", "rna_userdef.cc"),
    "interface_mixar_liquid_glass_tokens.cc": os.path.join(ROOT, "src", "source", "blender", "editors", "interface",
                                                           "interface_mixar_liquid_glass_tokens.cc"),
}
DEFAULT_NAME = "Lampway Night"
# The zen palette is the slot table read by name (mixar_zen() in interface_mixar_theme.cc): field -> slot.
ZEN = (("canvas", "mixar_canvas"), ("panel", "mixar_panel"), ("input", "mixar_input"), ("control", "mixar_control"),
       ("selected", "mixar_selected"), ("text", "mixar_text"), ("strong", "mixar_text_strong"),
       ("secondary", "mixar_text_secondary"), ("border", "mixar_border"), ("focus", "mixar_focus"),
       ("primary", "mixar_primary"), ("danger", "mixar_danger"), ("warning", "mixar_warning"),
       ("action", "mixar_action"))
# The reference constants beside it, each the slot it was measured from.
MX = {"MX_BG": ("tui", "mixar_bg"), "MX_BG_SUNKEN": ("tui", "mixar_sunken"), "MX_GRAY_800": ("tui", "mixar_gray_800"),
      "MX_GRAY_700": ("tui", "mixar_gray_700"), "MX_BORDER": ("tui", "mixar_border"),
      "MX_BORDER_STRONG": ("tui", "mixar_border_strong"), "MX_ACCENT": ("tui", "mixar_focus"),
      "MX_TOGGLE_ON": ("space_mixie", "mixar_toggle_active"), "MX_WARNING": ("tui", "mixar_warning"),
      "MX_DANGER": ("tui", "mixar_danger"), "MX_INK": ("tui", "mixar_ink"), "MX_FG_1": ("tui", "mixar_fg_1"),
      "MX_FG_2": ("tui", "mixar_fg_2"), "MX_FG_3": ("tui", "mixar_fg_3"), "MX_FG_4": ("tui", "mixar_fg_4")}
# The liquid-glass material table (contract 03 section 5): the four panes the island and the cards are made of take their tint
# from `surface` and their rim from `line_hi` at each row's own alpha; the moodboard's reveal tab is an amber bed, not green;
# no row has a moving specular ("only egress moves", DESIGN.md 13). Tokens are the dark variant: the table is compiled.
GLASS = {
    "MIXAR_GLASS_CARD": {"tint_top": "surface", "tint_bottom": "surface", "rim": "line_hi"},
    "MIXAR_GLASS_ISLAND": {"tint_top": "surface", "tint_bottom": "surface", "rim": "line_hi"},
    "MIXAR_GLASS_PANEL": {"tint_top": "surface", "tint_bottom": "surface", "rim": "line_hi"},
    "MIXAR_GLASS_PILL": {"tint_top": "surface", "tint_bottom": "surface", "rim": "line_hi"},
    "MIXAR_GLASS_MOODBOARD_TAB": {"tint_top": "accent_bed_hi", "tint_bottom": "accent_bed", "glaze": "accent_bed", "rim": "accent"},
}
# The chat space's DNA carries copies of the moodboard's colours that no RNA reaches (ThemeMixieChat has no moodboard
# properties); they follow the moodboard's own, so the compiled default holds no stale Forest copy.
MIRROR = {("space_mixie_chat", "moodboard_"): "space_mixie"}
# RNA's reset defaults live in three theme structs; their XML container names.
RNA_FUNCS = {"rna_def_userdef_theme_space_mixie_chat": "mixie_chat",
             "rna_def_userdef_theme_space_agent_bubble": "agent_bubble",
             "rna_def_userdef_theme_space_mixie": "mixie"}


def theme_values(tree):
    """provenance key -> value, keyed exactly as build() writes the provenance file."""
    counters, out = {}, {}

    def walk(el, stack):
        if el.tag[0].isupper() and el.tag not in ("Theme", "ThemeStyle"):
            key = container_key(stack)
            idx = counters.get(key, 0)
            counters[key] = idx + 1
            for attr, val in el.attrib.items():
                out[f"{key}[{idx}].{attr}"] = val
        for ch in el:
            walk(ch, stack + [ch.tag])

    walk(tree.getroot().find("Theme"), [])
    return out


def compiled_theme(values):
    """The default theme as DNA: the measured baseline with every mapped field set from Lampway Night."""
    dna = json.load(open(DNA_MAP))
    fields = {tuple(p): v for p, v in dna["baseline"]}
    if dna["unmapped"]:
        raise Unmapped(f"{len(dna['unmapped'])} attributes have no DNA field (re-run dump_theme_dna.py): "
                       f"{dna['unmapped'][:3]}")
    channels = []
    for key, m in sorted(dna["map"].items()):
        path, kind = tuple(m["path"]), m["kind"]
        if m.get("hidden"):
            container, _, rest = key.partition("[")
            attr = rest.split("].", 1)[1]
            spec = RULES.get(container, {}).get(attr)
            if spec is None:
                raise Unmapped(f"{key}: a colour no preset carries has no rule")
            val = resolve(spec, attr, container, 0, "dark", 4, {})[0]
        elif key not in values:
            raise Unmapped(f"{key}: in the DNA map but not in the theme (re-run dump_theme_dna.py)")
        else:
            val = values[key]
        cur = fields[path]
        if kind == "colour":
            hx = val[1:].lower()
            fields[path] = (hx + cur[6:])[:len(cur)] if len(hx) == 6 else hx[:len(cur)]
        elif kind == "channel":
            channels.append((path, m["channel"], val))
        elif kind == "flag":
            fields[path] = (int(cur) & ~m["mask"]) | (m["bit"] if val == "TRUE" else 0)
        elif kind == "enum":
            fields[path] = m["values"][val]
        elif kind == "float":
            fields[path] = m["scale"] * float(val) + m["offset"]
        else:
            fields[path] = int(round(m["scale"] * float(val) + m["offset"]))
    for path, channel, val in channels:   # after the colour they live in (background_alpha is back's alpha)
        b = bytearray.fromhex(fields[path])
        b[channel] = round(float(val) * 255)
        fields[path] = b.hex()
    mapped = {tuple(m["path"]) for m in dna["map"].values()}
    for (space, prefix), source in MIRROR.items():
        for path in [p for p in fields if p[:1] == (space,) and len(p) == 2 and p[1].startswith(prefix)]:
            if path not in mapped and isinstance(fields[path], str):
                fields[path] = fields[(source, path[1])]
    fields[("name",)] = DEFAULT_NAME
    return fields


def _upstream_theme_as_c():
    tools = os.path.join(ROOT, "upstream", "tools", "utils")
    if not os.path.isfile(os.path.join(tools, "blender_theme_as_c.py")):
        raise Unmapped("upstream/ is not checked out: its tools/utils/blender_theme_as_c.py writes the C file")
    sys.path.insert(0, tools)
    try:
        import blender_theme_as_c
    finally:
        sys.path.remove(tools)
    return blender_theme_as_c


def userdef_c(fields, path):
    """Write userdef_default_theme.c the way upstream's own tool writes it (same writer, zeros omitted)."""
    import io
    tool = _upstream_theme_as_c()
    items = []
    for p, v in fields.items():
        key = tuple(k.encode("ascii") if isinstance(k, str) else k for k in p)
        if isinstance(v, str):
            if len(v) in (6, 8) and all(c in "0123456789abcdef" for c in v):
                v = bytes.fromhex(v)
            elif not v:
                continue
            else:
                v = v.encode("ascii")
        items.append((key if len(key) > 1 else key[0], v))
    # The writer closes a nested block only when the next field's path differs. bTheme ends on padding the tool
    # skips (dump_theme_dna.py drops those names), so end on one top-level skipped name to close the last block.
    items.append((b"_pad_end", 0))
    buf = io.StringIO()
    buf.write(tool.C_SOURCE_HEADER)
    buf.write("const bTheme U_theme_default = {\n")
    tool.write_member(buf.write, 1, None, None, items)
    buf.write("};\n\n/* clang-format on */\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(buf.getvalue())
    tool.file_remove_empty_braces(path)


def _rgba(hx):
    return [int(hx[i:i + 2], 16) for i in (0, 2, 4, 6)]


def _over255(hx):
    return ", ".join(f"{c}.0f / 255.0f" for c in _rgba(hx))


def _sub_once(pattern, repl, text, what, flags=0):
    import re
    new, n = re.subn(pattern, repl, text, flags=flags)
    if n != 1:
        raise Unmapped(f"{what}: expected one match, found {n}")
    return new


def slot_table_cc(fields, text):
    """interface_mixar_theme.cc: each slot's compiled fallback is the default theme's value."""
    import re
    rows = re.compile(r"\{(false|true), offsetof\((ThemeUI|ThemeSpace), (\w+)\), \{\d+, \d+, \d+, \d+\}\},")

    def row(m):
        dna = ("space_agent_bubble" if m[1] == "true" else "tui", m[3])
        return f"{{{m[1]}, offsetof({m[2]}, {m[3]}), {{{', '.join(map(str, _rgba(fields[dna])))}}}}},"
    new, n = rows.subn(row, text)
    if n != 89:
        raise Unmapped(f"interface_mixar_theme.cc: expected the 89 slot rows, found {n}")
    return new


def tokens_hh(fields, text):
    """UI_mixar_tokens.hh: the zen palette and the MX_ reference colours are the default theme's slots."""
    zen = ",\n".join(f"    {{{_over255(fields[('tui', slot)])}}}" for _field, slot in ZEN)
    text = _sub_once(r"inline constexpr Palette zen = \{.*?\}\};", lambda m: f"inline constexpr Palette zen = {{\n{zen}}};",
                     text, "UI_mixar_tokens.hh zen", flags=__import__("re").S)
    for name, dna in MX.items():
        text = _sub_once(rf"(inline constexpr uchar {name}\[4\] = )\{{[^}}]*\}};[^\n]*",
                         lambda m, dna=dna: m[1] + "{" + ", ".join(map(str, _rgba(fields[dna]))) + "};", text, name)
    return text


def rna_defaults_cc(fields, dna_map, text):
    """rna_userdef.cc: "Reset to Default Value" on a Lampway theme colour gives back the default theme's value."""
    import re
    for table, dna_struct in (("mixar_theme_ui_colors", "tui"), ("mixar_theme_agent_colors", "space_agent_bubble")):
        start = text.index(f"static const MixarRnaColor {table}[] = {{")
        end = text.index("\n};", start)
        body = text[start:end]
        rows = re.compile(r'(\{"(\w+)", N_\("[^"]*"\), N_\("[^"]*"\), )\{[^}]*\}\}')
        body, n = rows.subn(lambda m: f"{m[1]}{{{_over255(fields[(dna_struct, m[2])])}}}}}", body)
        if n == 0 or n != body.count('{"'):
            raise Unmapped(f"rna_userdef.cc {table}: rewrote {n} of {body.count(chr(123) + chr(34))} rows")
        text = text[:start] + body + text[end:]
    for func, container in RNA_FUNCS.items():
        start = text.index(f"static void {func}(BlenderRNA *brna)")
        end = text.index("\n}\n", start)
        body = text[start:end]
        for block in body.split("prop = RNA_def_property(srna, \"")[1:]:
            rna, default = block.split('"', 1)[0], re.search(r"float_array_default\(prop, (default_\w+)\)", block)
            if default is None:
                continue
            m = dna_map.get(f"{container}[0].{rna}")
            if m is None:
                raise Unmapped(f"rna_userdef.cc {func}: {rna} has a reset default but no DNA field")
            body = _sub_once(rf"(static const float {default[1]}\[4\] = )\{{[^}}]*\}};[^\n]*",
                             lambda mm, m=m: mm[1] + "{" + _over255(fields[tuple(m["path"])]) + "};", body, default[1])
        text = text[:start] + body + text[end:]
    return text


def glass_cc(text):
    """interface_mixar_liquid_glass_tokens.cc: retint the rows GLASS names, keep each colour's alpha, and zero every specular."""
    import re
    start = text.index("const MixarGlassTokens g_glass_tokens[] = {")
    end = text.index("\n};", start)
    table = text[start:end]

    def row(m):
        name, body = m[1], m[2]
        for field, token in GLASS.get(name, {}).items():
            hx = TOKENS["colour"][token]["dark"]
            rgb = ", ".join(f"{int(hx[i:i + 2], 16) / 255:.3f}f" for i in (1, 3, 5))
            body, n = re.subn(rf"(/\*\s*{field}\s*\*/\s*\{{)[^,]*, [^,]*, [^,]*,", lambda mm: f"{mm[1]}{rgb},", body, count=1)
            if n != 1:
                raise Unmapped(f"glass {name}.{field}: expected one colour")
        body, n = re.subn(r"(/\*\s*specular_alpha\s*\*/\s*)[-\d.]+f", r"\g<1>0.00f", body)
        if n != 1:
            raise Unmapped(f"glass {name}: expected one specular_alpha")
        return m[0][:m.start(2) - m.start(0)] + body + m[0][m.end(2) - m.start(0):]

    table, n = re.subn(r"/\* (MIXAR_GLASS_\w+).*?\*/\s*\{(.*?)\n    \},", row, table, flags=re.S)
    if n < len(GLASS):
        raise Unmapped(f"glass table: found {n} rows")
    return text[:start] + table + text[end:]


def emit_native(values, out):
    """Write the four compiled tables; into the source tree when out is None, else as files in out."""
    fields = compiled_theme(values)
    dna_map = json.load(open(DNA_MAP))["map"]
    dest = (lambda name: NATIVE[name]) if out is None else (lambda name: os.path.join(out, name))
    userdef_c(fields, dest("userdef_default_theme.c"))
    for name, fn in (("interface_mixar_theme.cc", slot_table_cc), ("UI_mixar_tokens.hh", tokens_hh),
                     ("rna_userdef.cc", lambda f, t: rna_defaults_cc(f, dna_map, t)),
                     ("interface_mixar_liquid_glass_tokens.cc", lambda _f, t: glass_cc(t))):
        text = open(NATIVE[name], encoding="utf-8").read()
        with open(dest(name), "w", encoding="utf-8") as fh:
            fh.write(fn(fields, text))


if __name__ == "__main__":
    out = HERE
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    try:
        n1 = write("dark", os.path.join(out, "lampway_dark.xml"), "Lampway Night (dark)")
        n2 = write("light", os.path.join(out, "lampway_light.xml"), "Lampway Paper (light)")
    except Unmapped as exc:
        print("BUILD REFUSED:", exc)
        sys.exit(1)
    write_wezterm(os.path.join(out, "lampway.wezterm.lua"))
    if out == HERE:   # the copy the server's terminal add-on installs (facelift contract 16): the same bytes
        write_wezterm(os.path.join(ROOT_DIR, "server", "lampway_server", "addons", "lampway.wezterm.lua"))
    write_tokens_css(TOKENS_CSS if out == HERE else os.path.join(out, "tokens.css"))
    try:
        emit_native(theme_values(build("dark")[0]), None if out == HERE else out)
    except Unmapped as exc:
        print("BUILD REFUSED:", exc)
        sys.exit(1)
    if out == HERE:  # the shipped presets are the same bytes as the generated themes
        for shipped, generated in (("Lampway_Night.xml", "lampway_dark.xml"), ("Lampway_Paper.xml", "lampway_light.xml")):
            shutil.copyfile(os.path.join(HERE, generated), os.path.join(PRESETS, shipped))
    print(f"wrote lampway_dark.xml ({n1} attributes), lampway_light.xml ({n2} attributes), lampway.wezterm.lua "
          f"and the compiled defaults ({', '.join(NATIVE)})")
