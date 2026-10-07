ThemeUserInterface(bpy_struct)
==============================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: ThemeUserInterface(bpy_struct)

   Theme settings for user interface elements

   .. attribute:: axis_w

      W-axis for quaternion and axis-angle rotations (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: axis_x

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: axis_y

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: axis_z

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: editor_border

      Color of the border between editors (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: editor_outline

      Color of the outline of each editor, except the active one (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: editor_outline_active

      Color of the outline of the active editor (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: gizmo_a

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: gizmo_b

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: gizmo_hi

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: gizmo_primary

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: gizmo_secondary

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: gizmo_view_align

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: icon_alpha

      Transparency of icons in the interface, to reduce contrast (in [0, 1], default 0.0)

      :type: float

   .. attribute:: icon_autokey

      Color of Auto Keying indicator when enabled (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: icon_border_intensity

      Control the intensity of the border around themes icons (in [0, 1], default 0.0)

      :type: float

   .. attribute:: icon_collection

      (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: icon_folder

      Color of folders in the file browser (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: icon_modifier

      (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: icon_object

      (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: icon_object_data

      (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: icon_saturation

      Saturation of icons in the interface (in [0, 1], default 0.0)

      :type: float

   .. attribute:: icon_scene

      (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: icon_shading

      (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: link

      Color of link widgets (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: menu_shadow_fac

      Blending factor for panel and menu shadows (in [0.01, 1], default 0.0)

      :type: float

   .. attribute:: menu_shadow_width

      Width of panel and menu shadows, set to zero to disable (in [0, 24], default 0)

      :type: int

   .. attribute:: mixar_action

      Secondary action chip (array of 4 items, in [0, 1], default (0.0862745, 0.0980392, 0.133333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_bg

      Raised card bed (array of 4 items, in [0, 1], default (0.0862745, 0.0980392, 0.133333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_border

      Neutral control outline (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_border_strong

      Widget and card outline (array of 4 items, in [0, 1], default (0.231373, 0.258824, 0.321569, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_brand

      Toast primary action (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_brand_text

      Text on the brand action (array of 4 items, in [0, 1], default (0.054902, 0.0627451, 0.0862745, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_canvas

      Shared canvas and page background (array of 4 items, in [0, 1], default (0.054902, 0.0627451, 0.0862745, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_chip

      Chip track (array of 4 items, in [0, 1], default (0.117647, 0.133333, 0.176471, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_chip_active

      Selected segment thumb (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_brand_bottom

      Cinema brand gradient bottom (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_brand_top

      Cinema brand gradient top (array of 4 items, in [0, 1], default (0.054902, 0.0627451, 0.0862745, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_card_bottom

      Cinema card gradient bottom (array of 4 items, in [0, 1], default (0.0862745, 0.0980392, 0.133333, 0.960784))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_card_top

      Cinema card gradient top (array of 4 items, in [0, 1], default (0.117647, 0.133333, 0.176471, 0.960784))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_chip

      Cinema chip (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_dimmer

      Cinema dimmer (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_gate_fill

      Cinema gate wash (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 0.0705882))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_keycap

      Cinema keycap (array of 4 items, in [0, 1], default (0.490196, 0.478431, 0.45098, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_label

      Cinema field label (array of 4 items, in [0, 1], default (0.662745, 0.65098, 0.615686, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_phone

      Cinema phone chip (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_pill_border

      Cinema mode pill hairline (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_pill_border_on

      Cinema mode pill active hairline (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_pill_fill

      Cinema mode pill at rest (array of 4 items, in [0, 1], default (0.0666667, 0.0745098, 0.101961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_pill_label

      Cinema mode pill label at rest (array of 4 items, in [0, 1], default (0.490196, 0.478431, 0.45098, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_pill_label_on

      Cinema mode pill label when active (array of 4 items, in [0, 1], default (0.968627, 0.956863, 0.933333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_pill_on_a

      Cinema mode pill gradient start (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_pill_on_b

      Cinema mode pill gradient end (array of 4 items, in [0, 1], default (0.352941, 0.278431, 0.12549, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_row_bottom

      Cinema row gradient bottom (array of 4 items, in [0, 1], default (0.0862745, 0.0980392, 0.133333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_row_caption

      Cinema caption text (array of 4 items, in [0, 1], default (0.662745, 0.65098, 0.615686, 0.85098))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_row_hover

      Cinema slider hover track (array of 4 items, in [0, 1], default (0.14902, 0.168627, 0.219608, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_row_slider_on

      Cinema slider fill (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_row_text_disabled

      Disabled cinema row text (array of 4 items, in [0, 1], default (0.490196, 0.478431, 0.45098, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_row_text_off

      Cinema row text at rest (array of 4 items, in [0, 1], default (0.811765, 0.796078, 0.760784, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_row_text_on

      Cinema value text (array of 4 items, in [0, 1], default (0.968627, 0.956863, 0.933333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_row_top

      Cinema row gradient top (array of 4 items, in [0, 1], default (0.14902, 0.168627, 0.219608, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_cinema_row_track

      Cinema slider resting track (array of 4 items, in [0, 1], default (0.0666667, 0.0745098, 0.101961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_control

      Parameter chip and control track (array of 4 items, in [0, 1], default (0.117647, 0.133333, 0.176471, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_danger

      Destructive and error accent (array of 4 items, in [0, 1], default (0.941176, 0.462745, 0.419608, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_fg_1

      Primary widget text (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_fg_2

      Secondary widget text (array of 4 items, in [0, 1], default (0.811765, 0.796078, 0.760784, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_fg_3

      Section label (array of 4 items, in [0, 1], default (0.662745, 0.65098, 0.615686, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_fg_4

      Muted glyph (array of 4 items, in [0, 1], default (0.490196, 0.478431, 0.45098, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_focus

      Shared accent, focus ring and hover (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_glass_wash

      Island Glass Wash color (array of 4 items, in [0, 1], default (0.054902, 0.0627451, 0.0862745, 0.2))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_glyph

      Header glyph (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_gradient_end

      Generate action gradient stop (array of 4 items, in [0, 1], default (0.352941, 0.278431, 0.12549, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_gradient_mid_a

      Generate action gradient stop (array of 4 items, in [0, 1], default (0.352941, 0.278431, 0.12549, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_gradient_mid_b

      Generate action gradient stop (array of 4 items, in [0, 1], default (0.352941, 0.278431, 0.12549, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_gradient_start

      Generate action gradient stop (array of 4 items, in [0, 1], default (0.352941, 0.278431, 0.12549, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_gray_700

      Toggle off track (array of 4 items, in [0, 1], default (0.117647, 0.133333, 0.176471, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_gray_800

      Input and dropdown fill (array of 4 items, in [0, 1], default (0.0666667, 0.0745098, 0.101961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_ink

      Text on a bright action (array of 4 items, in [0, 1], default (0.968627, 0.956863, 0.933333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_input

      Prompt and text-field bed (array of 4 items, in [0, 1], default (0.0666667, 0.0745098, 0.101961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_pane_pill_dim

      Recessed value pill (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_pane_pill_on

      On-state pill (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_pane_wash

      Pane wash bottom (array of 4 items, in [0, 1], default (0.0862745, 0.0980392, 0.133333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_panel

      Raised panel and wash top (array of 4 items, in [0, 1], default (0.0862745, 0.0980392, 0.133333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_primary

      Generate and export action (array of 4 items, in [0, 1], default (0.352941, 0.278431, 0.12549, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_profile_avatar

      Account avatar disc (array of 4 items, in [0, 1], default (0.14902, 0.168627, 0.219608, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_profile_fill

      Account chip fill (array of 4 items, in [0, 1], default (0.0862745, 0.0980392, 0.133333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_profile_glyph

      Account avatar glyph (array of 4 items, in [0, 1], default (0.811765, 0.796078, 0.760784, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_profile_label

      Account chip label (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_queue

      Queue pill and speed-off (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_queue_count

      Queue count chip (array of 4 items, in [0, 1], default (0.490196, 0.478431, 0.45098, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_selected

      Selected chip, thumb and hover wash (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_sketch_ink

      Default ink for Scribble and new Moodboard strokes (array of 4 items, in [0, 1], default (0.490196, 0.478431, 0.45098, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_slider_label

      Lamplight/Workshop slider label (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_slider_thumb

      Lamplight/Workshop slider thumb (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_slider_thumb_hover

      Lamplight/Workshop thumb hover (array of 4 items, in [0, 1], default (0.964706, 0.803922, 0.419608, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_slider_track

      Lamplight/Workshop slider track (array of 4 items, in [0, 1], default (0.0666667, 0.0745098, 0.101961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_sunken

      Quota and sunken track (array of 4 items, in [0, 1], default (0.0666667, 0.0745098, 0.101961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_text

      Primary label (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_text_secondary

      Inactive and caption text (array of 4 items, in [0, 1], default (0.662745, 0.65098, 0.615686, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_text_strong

      Titles and active labels (array of 4 items, in [0, 1], default (0.968627, 0.956863, 0.933333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_toolbar_background

      Toolbar Background color (array of 4 items, in [0, 1], default (0.0862745, 0.0980392, 0.133333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_toolbar_border

      Toolbar Border color (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_toolbar_muted

      Toolbar Disabled Text color (array of 4 items, in [0, 1], default (0.490196, 0.478431, 0.45098, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_toolbar_primary

      Toolbar Action color (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_toolbar_primary_border

      Toolbar Action Border color (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_toolbar_selected

      Toolbar Selected color (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_toolbar_text

      Toolbar Text color (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_viewport_border

      Shading pill hairline (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_viewport_fill

      Shading pill fill (array of 4 items, in [0, 1], default (0.0666667, 0.0745098, 0.101961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_viewport_label

      Shading pill label at rest (array of 4 items, in [0, 1], default (0.662745, 0.65098, 0.615686, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_viewport_label_on

      Shading pill label when active (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_warning

      Warning accent (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_widget_border

      Card outline (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: panel_active

      Color of the outline of top-level panels that are active (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: panel_back

      (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: panel_header

      (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: panel_outline

      Color of the outline of top-level panels (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: panel_roundness

      Roundness of the corners of panels and sub-panels (in [0, 1], default 0.4)

      :type: float

   .. attribute:: panel_sub_back

      (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: panel_text

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: panel_title

      (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: transparent_checker_primary

      Primary color of checkerboard pattern indicating transparent areas (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: transparent_checker_secondary

      Secondary color of checkerboard pattern indicating transparent areas (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. attribute:: transparent_checker_size

      Size of checkerboard pattern indicating transparent areas (in [2, 48], default 0)

      :type: int

   .. data:: wcol_box

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_curve

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_list_item

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_menu

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_menu_back

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_menu_item

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_num

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_numslider

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_option

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_pie_menu

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_progress

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_pulldown

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_radio

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_regular

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_scroll

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_state

      (readonly, never None)

      :type: :class:`ThemeWidgetStateColors`

   .. data:: wcol_tab

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_text

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_toggle

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_tool

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_toolbar_item

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. data:: wcol_tooltip

      (readonly, never None)

      :type: :class:`ThemeWidgetColors`

   .. attribute:: widget_emboss

      Color of the 1px shadow line underlying widgets (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: widget_text_cursor

      Color of the text insertion cursor (caret) (array of 3 items, in [0, 1], default (0.0, 0.0, 0.0))

      :type: :class:`mathutils.Color`

   .. classmethod:: bl_rna_get_subclass(id, default=None, /)
   
      :param id: The RNA type identifier.
      :type id: str
      :param default: The value to return when not found.
      :type default: :class:`bpy.types.Struct` | None
      :return: The RNA type or default when not found.
      :rtype: :class:`bpy.types.Struct`


   .. classmethod:: bl_rna_get_subclass_py(id, default=None, /)
   
      :param id: The RNA type identifier.
      :type id: str
      :param default: The value to return when not found.
      :type default: type | None
      :return: The class or default when not found.
      :rtype: type


Inherited Properties
--------------------

.. hlist::
   :columns: 2

   - :class:`bpy_struct.id_data`

Inherited Functions
-------------------

.. hlist::
   :columns: 2

   - :class:`bpy_struct.as_pointer`
   - :class:`bpy_struct.driver_add`
   - :class:`bpy_struct.driver_remove`
   - :class:`bpy_struct.get`
   - :class:`bpy_struct.id_properties_clear`
   - :class:`bpy_struct.id_properties_ensure`
   - :class:`bpy_struct.id_properties_ui`
   - :class:`bpy_struct.is_property_hidden`
   - :class:`bpy_struct.is_property_overridable_library`
   - :class:`bpy_struct.is_property_readonly`
   - :class:`bpy_struct.is_property_set`
   - :class:`bpy_struct.items`
   - :class:`bpy_struct.keyframe_delete`
   - :class:`bpy_struct.keyframe_insert`
   - :class:`bpy_struct.keys`
   - :class:`bpy_struct.path_from_id`
   - :class:`bpy_struct.path_from_module`
   - :class:`bpy_struct.path_resolve`
   - :class:`bpy_struct.pop`
   - :class:`bpy_struct.property_overridable_library_set`
   - :class:`bpy_struct.property_unset`
   - :class:`bpy_struct.rna_ancestors`
   - :class:`bpy_struct.type_recast`
   - :class:`bpy_struct.values`

References
----------

.. hlist::
   :columns: 2

   - :class:`Theme.user_interface`

