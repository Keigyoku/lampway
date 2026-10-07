Window(bpy_struct)
==================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: Window(bpy_struct)

   Open window

   .. data:: global_areas

      Window-global areas (topbar, statusbar). Lampway extension — exposed so onboarding can address the topbar for redraw. (default None, readonly)

      :type: :class:`bpy_prop_collection`\ [:class:`Area`]

   .. data:: height

      Window height (in [0, 32767], default 0, readonly)

      :type: int

   .. data:: modal_operators

      A list of currently running modal operators (default None, readonly)

      :type: :class:`bpy_prop_collection`\ [:class:`Operator`]

   .. data:: parent

      Active workspace and scene follow this window (readonly)

      :type: :class:`Window` | None

   .. attribute:: scene

      Active scene to be edited in the window (never None)

      :type: :class:`Scene`

   .. attribute:: screen

      Active workspace screen showing in the window (never None)

      :type: :class:`Screen`

   .. data:: stereo_3d_display

      Settings for stereo 3D display (readonly, never None)

      :type: :class:`Stereo3dDisplay`

   .. data:: support_hdr_color

      The window has a HDR graphics buffer that wide gamut and high dynamic range colors can be written to, in extended sRGB color space. (default False, readonly)

      :type: bool

   .. attribute:: view_layer

      The active workspace view layer showing in the window (never None)

      :type: :class:`ViewLayer`

   .. data:: width

      Window width (in [0, 32767], default 0, readonly)

      :type: int

   .. attribute:: workspace

      Active workspace showing in the window (never None)

      :type: :class:`WorkSpace`

   .. data:: x

      Horizontal location of the window (in [-32768, 32767], default 0, readonly)

      :type: int

   .. data:: y

      Vertical location of the window (in [-32768, 32767], default 0, readonly)

      :type: int

   .. method:: cursor_warp(x, y)

      Set the cursor position

      :param x: (in [-inf, inf])
      :type x: int
      :param y: (in [-inf, inf])
      :type y: int

   .. method:: cursor_set(cursor)

      Set the cursor

      :param cursor: cursor
      :type cursor: Literal[:ref:`rna_enum_window_cursor_items`]

   .. method:: cursor_modal_set(cursor)

      Set the cursor, so the previous cursor can be restored

      :param cursor: cursor
      :type cursor: Literal[:ref:`rna_enum_window_cursor_items`]

   .. method:: cursor_modal_restore()

      Restore the previous cursor after calling ``cursor_modal_set``


   .. method:: event_simulate(type, value, *, unicode="", x=0, y=0, shift=False, ctrl=False, alt=False, oskey=False, hyper=False)

      event_simulate

      :param type: Type
      :type type: Literal[:ref:`rna_enum_event_type_items`]
      :param value: Value
      :type value: Literal[:ref:`rna_enum_event_value_items`]
      :param unicode: (optional)
      :type unicode: str
      :param x: (in [-inf, inf], optional)
      :type x: int
      :param y: (in [-inf, inf], optional)
      :type y: int
      :param shift: Shift, (optional)
      :type shift: bool
      :param ctrl: Ctrl, (optional)
      :type ctrl: bool
      :param alt: Alt, (optional)
      :type alt: bool
      :param oskey: OS Key, (optional)
      :type oskey: bool
      :param hyper: Hyper, (optional)
      :type hyper: bool
      :return: Item, Added key map item
      :rtype: :class:`Event`

   .. method:: find_playing_scene(*, scrub=False)

      find_playing_scene

      :param scrub: Scrubbing, Check if time in the scene is being scrubbed (optional)
      :type scrub: bool
      :return: Scene, Scene that is currently playing
      :rtype: :class:`Scene`

   .. method:: mixar_ui_event(*, owner="", type='NONE', value='NOTHING', text="", x=0, y=0, shift=False, ctrl=False, alt=False, oskey=False)

      mixar_ui_event

      :param owner: Owner, Controller lease token (optional, never None)
      :type owner: str
      :param type: Type, (optional)
      :type type: Literal[:ref:`rna_enum_event_type_items`]
      :param value: Value, (optional)
      :type value: Literal[:ref:`rna_enum_event_value_items`]
      :param text: Text, Single UTF-8 character (optional, never None)
      :type text: str
      :param x: (in [-inf, inf], optional)
      :type x: int
      :param y: (in [-inf, inf], optional)
      :type y: int
      :param shift: (optional)
      :type shift: bool
      :param ctrl: (optional)
      :type ctrl: bool
      :param alt: (optional)
      :type alt: bool
      :param oskey: (optional)
      :type oskey: bool
      :rtype: bool

   .. method:: mixar_ui_modal_count()

      mixar_ui_modal_count

      :return: (in [0, inf])
      :rtype: int

   .. method:: mixar_ui_capture(*, filepath="", x=0, y=0, width=0, height=0)

      mixar_ui_capture

      :param filepath: PNG path (optional, never None)
      :type filepath: str
      :param x: (in [0, inf], optional)
      :type x: int
      :param y: (in [0, inf], optional)
      :type y: int
      :param width: (in [0, inf], optional)
      :type width: int
      :param height: (in [0, inf], optional)
      :type height: int
      :rtype: bool

   .. method:: mixar_qa_double_click(*, x=0, y=0)

      mixar_qa_double_click

      :param x: X, Window pixel (in [-inf, inf], optional)
      :type x: int
      :param y: Y, Window pixel (in [-inf, inf], optional)
      :type y: int
      :return: Event queued
      :rtype: bool

   .. method:: mixar_qa_drag_file(filepath)

      Preview a file entering the window without dropping (QA harness)

      :param filepath: File being dragged (never None)
      :type filepath: str

   .. method:: mixar_qa_drop_file(filepath, x, y, *, filepaths_json="")

      Simulate an OS file drop onto this window (QA harness; requires --enable-event-simulate)

      :param filepath: File to drop (never None)
      :type filepath: str
      :param x: (in [-inf, inf])
      :type x: int
      :param y: (in [-inf, inf])
      :type y: int
      :param filepaths_json: Optional JSON array of paths for one batch drop (optional, never None)
      :type filepaths_json: str

   .. method:: mixar_qa_capture_frame(filepath, *, x=0, y=0, width=0, height=0)

      Save a cached UI frame without clearing hover or menus (QA event-simulation mode only)

      :param filepath: PNG path (never None)
      :type filepath: str
      :param x: Optional crop in window pixels (in [0, inf], optional)
      :type x: int
      :param y: Optional crop in window pixels (in [0, inf], optional)
      :type y: int
      :param width: Optional crop in window pixels (in [0, inf], optional)
      :type width: int
      :param height: Optional crop in window pixels (in [0, inf], optional)
      :type height: int
      :return: Frame saved
      :rtype: bool

   .. method:: mixar_live_client_rect()

      Current client bounds from the windowing system: (left, top, right, bottom) in screen points with a top-left origin; zeros when the window has no native window

      :return: Rect, left, top, right, bottom (array of 4 items, in [-inf, inf])
      :rtype: :class:`bpy_prop_array`\ [int]

   .. method:: mixar_tour_menu_open(menu)

      Onboarding tour: open a menu under its own pulldown button in this window, as a click would; False when the button is not on screen or it is already open

      :param menu: Menu, Menu type idname (never None)
      :type menu: str
      :rtype: bool

   .. method:: mixar_tour_menu_close()

      Onboarding tour: close the menu it opened

      :rtype: bool

   .. method:: mixar_tour_menu_is_open()

      Onboarding tour: the menu it opened is still up

      :rtype: bool

   .. method:: mixar_tour_popover_open(panel)

      Open a header popover under its own button in this window, as a click would; False when the button is not on screen or the panel does not poll

      :param panel: Panel, Panel type idname (never None)
      :type panel: str
      :rtype: bool

   .. method:: mixar_refresh_popups()

      Rebuild every pop-up open in this window after async state changes

      :return: (in [0, inf])
      :rtype: int

   .. method:: mixar_content_rect_in(host)

      This window's client rect in another window's client coordinates: (x, y, width, height) in points, bottom-left origin; zeros when unavailable

      :param host: The reference window (never None)
      :type host: :class:`Window` | None
      :return: Rect, x, y, width, height (array of 4 items, in [-inf, inf])
      :rtype: :class:`bpy_prop_array`\ [int]

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


   .. method:: screenshot(*, region=None, use_alpha=False)
   
      Capture the windows pixel data.
   
      :param region: The region to capture, or ``None`` to capture all.
         Each int pair represents a pixel coordinate (the end value is not inclusive, matching Python slicing): ((min_x, min_y), (max_x, max_y))
      :type region: tuple[tuple[int, int], tuple[int, int]] | None
      :param use_alpha: When false the alpha channel is fully opaque. Otherwise alpha values from the window's frame-buffer are returned as-is.
      :type use_alpha: bool
      :return: A read-only :class:`memoryview` of shape ``(height, width, 4)`` and format ``'B'``, viewing the captured RGBA pixels (rows ordered from bottom to top).
      :rtype: memoryview


      **Save 3D Viewport to a PNG**

      Capture the 3D viewport's main region from the current window
      and write it to a PNG file using :mod:`imbuf`.

      .. literalinclude:: ../examples/bpy.types.Window.screenshot.0.py
         :lines: 8-


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

   - :class:`Context.window`
   - :class:`Window.mixar_content_rect_in`
   - :class:`Window.parent`
   - :class:`WindowManager.event_timer_add`
   - :class:`WindowManager.windows`
   - :class:`Windows.find_playing`

