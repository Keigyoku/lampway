PreferencesInput(bpy_struct)
============================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: PreferencesInput(bpy_struct)

   Settings for input devices

   .. attribute:: drag_threshold

      Number of pixels to drag before a drag event is triggered for keyboard and other non mouse/tablet input (otherwise click events are detected) (in [1, 255], default 30)

      :type: int

   .. attribute:: drag_threshold_mouse

      Number of pixels to drag before a drag event is triggered for mouse/trackpad input (otherwise click events are detected) (in [1, 255], default 3)

      :type: int

   .. attribute:: drag_threshold_tablet

      Number of pixels to drag before a drag event is triggered for tablet input (otherwise click events are detected) (in [1, 255], default 10)

      :type: int

   .. attribute:: invert_mouse_zoom

      Invert the axis of mouse movement for zooming (default False)

      :type: bool

   .. attribute:: invert_zoom_wheel

      Swap the Mouse Wheel zoom direction (default False)

      :type: bool

   .. attribute:: mouse_double_click_time

      Time/delay (in ms) for a double click (in [1, 1000], default 350)

      :type: int

   .. attribute:: mouse_emulate_3_button_modifier

      Hold this modifier to emulate the middle mouse button (default ``'ALT'``)

      :type: Literal['ALT', 'OSKEY']

   .. attribute:: move_threshold

      Number of pixels to before the cursor is considered to have moved (used for cycling selected items on successive clicks) (in [0, 255], default 2)

      :type: int

   .. attribute:: navigation_mode

      Which method to use for viewport navigation (default ``'WALK'``)

      :type: Literal[:ref:`rna_enum_navigation_mode_items`]

   .. attribute:: ndof_deadzone

      Threshold of initial movement needed from the device's rest position (in [0, 1], default 0.0)

      :type: float

   .. attribute:: ndof_fly_helicopter

      Device up/down directly controls the Z position of the 3D viewport (default False)

      :type: bool

   .. attribute:: ndof_fly_speed_auto

      Automatically adjusts fly navigation speed based on the distance of objects near the center of the viewport, making it easier to navigate complex scenes. Speed is recalculated each time movement starts. (default False)

      :type: bool

   .. attribute:: ndof_lock_camera_pan_zoom

      Pan/zoom the camera view instead of leaving the camera view when orbiting (default True)

      :type: bool

   .. attribute:: ndof_lock_horizon

      Lock Horizon forces the horizon to be kept leveled as it currently is (default True)

      :type: bool

   .. attribute:: ndof_navigation_mode

      3D Mouse Navigation Mode (default ``'OBJECT'``)

      - ``OBJECT``
        Object -- This mode is like reaching into the screen and holding the model in your hand. Push the 3D Mouse cap left, and the model moves left. Push right and the model moves right.
      - ``FLY``
        Fly -- Enables using the 3D Mouse as if it is a camera. Push into the scene and the camera moves forward into the scene. You are entering the scene as if flying around in it. This also inverts pan & zoom for 2D views.
      - ``DRONE``
        Drone -- Enables a Fly Mode navigation but pushing the cap forward while looking down will not change the altitude of the camera..

      :type: Literal['OBJECT', 'FLY', 'DRONE']

   .. attribute:: ndof_orbit_center_auto

      Auto sets the orbit center dynamically. When the complete model is in view, the center of volume of the whole model is used as the rotation point. When you move closer, the orbit center will be set on an object close to your center of the view. (default True)

      :type: bool

   .. attribute:: ndof_orbit_center_selected

      Selected Item forces the orbit center to only take the currently selected objects into account. (default False)

      :type: bool

   .. attribute:: ndof_panx_invert_axis

      (default False)

      :type: bool

   .. attribute:: ndof_pany_invert_axis

      (default False)

      :type: bool

   .. attribute:: ndof_panz_invert_axis

      (default False)

      :type: bool

   .. attribute:: ndof_rotation_sensitivity

      Overall sensitivity of the 3D Mouse for rotation (in [0.01, 40], default 4.0)

      :type: float

   .. attribute:: ndof_rotx_invert_axis

      (default False)

      :type: bool

   .. attribute:: ndof_roty_invert_axis

      (default False)

      :type: bool

   .. attribute:: ndof_rotz_invert_axis

      (default False)

      :type: bool

   .. attribute:: ndof_show_guide_orbit_axis

      Display the center and axis during rotation (default False)

      :type: bool

   .. attribute:: ndof_show_guide_orbit_center

      Display the orbit center during rotation (default True)

      :type: bool

   .. attribute:: ndof_translation_sensitivity

      Overall sensitivity of the 3D Mouse for translation (in [0.01, 40], default 4.0)

      :type: float

   .. attribute:: ndof_zoom_direction

      Which axis of the 3D Mouse cap zooms the view (default ``'NDOF_ZOOM_FORWARD'``)

      - ``NDOF_ZOOM_FORWARD``
        Forward/Backward -- Zoom by pulling the 3D Mouse cap upwards or pushing the cap downwards.
      - ``NDOF_ZOOM_UP``
        Up/Down -- Zoom by pulling the 3D Mouse cap upwards or pushing the cap downwards.

      :type: Literal['NDOF_ZOOM_FORWARD', 'NDOF_ZOOM_UP']

   .. attribute:: pressure_softness

      Adjusts softness of the low pressure response onset using a gamma curve (in [-inf, inf], default 0.0)

      :type: float

   .. attribute:: pressure_threshold_max

      Raw input pressure value that is interpreted as 100% by Blender (in [0, 1], default 1.0)

      :type: float

   .. attribute:: show_tablet_debug_values

      Show pressure values when using a paint operator (default False)

      :type: bool

   .. attribute:: tablet_api

      Select the tablet API to use for pressure sensitivity (may require restarting Blender for changes to take effect) (default ``'AUTOMATIC'``)

      - ``AUTOMATIC``
        Automatic -- Automatically choose Wintab or Windows Ink depending on the device.
      - ``WINDOWS_INK``
        Windows Ink -- Use native Windows Ink API, for modern tablet and pen devices. Requires Windows 8 or newer..
      - ``WINTAB``
        Wintab -- Use Wintab driver for older tablets and Windows versions.

      :type: Literal['AUTOMATIC', 'WINDOWS_INK', 'WINTAB']

   .. attribute:: touchpad_scroll_direction

      Scroll direction (Wayland only) (default ``'TRADITIONAL'``)

      - ``TRADITIONAL``
        Traditional -- Traditional scroll direction.
      - ``NATURAL``
        Natural -- Natural scroll direction.

      :type: Literal['TRADITIONAL', 'NATURAL']

   .. attribute:: use_auto_perspective

      Automatically switch between orthographic and perspective when changing from top/front/side views (default True)

      :type: bool

   .. attribute:: use_drag_immediately

      Moving things with a mouse drag confirms when releasing the button (default True)

      :type: bool

   .. attribute:: use_emulate_numpad

      Main 1 to 0 keys act as the numpad ones (useful for laptops) (default False)

      :type: bool

   .. attribute:: use_mouse_continuous

      Let the mouse wrap around the view boundaries so mouse movements are not limited by the screen size (used by transform, dragging of UI controls, etc.) (default True)

      :type: bool

   .. attribute:: use_mouse_depth_navigate

      Use the depth under the mouse to improve view pan/rotate/zoom functionality (default False)

      :type: bool

   .. attribute:: use_mouse_emulate_3_button

      Emulate Middle Mouse with Alt+Left Mouse (default False)

      :type: bool

   .. attribute:: use_multitouch_gestures

      Use multi-touch gestures for navigation with touchpad, instead of scroll wheel emulation (default True)

      :type: bool

   .. attribute:: use_numeric_input_advanced

      When entering numbers while transforming, default to advanced mode for full math expression evaluation (default False)

      :type: bool

   .. attribute:: use_rotate_around_active

      Use the selection (or the last stroke center in Paint modes) as the pivot point for orbiting (default False)

      :type: bool

   .. attribute:: use_zoom_to_mouse

      Zoom in towards the mouse pointer's position in the 3D view, rather than the 2D window center (default False)

      :type: bool

   .. attribute:: view_rotate_method

      Orbit method in the viewport (default ``'TURNTABLE'``)

      - ``TURNTABLE``
        Turntable -- Turntable keeps the Z-axis upright while orbiting.
      - ``TRACKBALL``
        Trackball -- Trackball allows you to tumble your view at any angle.

      :type: Literal['TURNTABLE', 'TRACKBALL']

   .. attribute:: view_rotate_sensitivity_trackball

      Scale trackball orbit sensitivity (in [0.1, 10], default 1.0)

      :type: float

   .. attribute:: view_rotate_sensitivity_turntable

      Rotation amount per pixel to control how fast the viewport orbits (in [1.74533e-05, 0.261799], default 0.00698132)

      :type: float

   .. attribute:: view_zoom_axis

      Axis of mouse movement to zoom in or out on (default ``'VERTICAL'``)

      - ``VERTICAL``
        Vertical -- Zoom in and out based on vertical mouse movement.
      - ``HORIZONTAL``
        Horizontal -- Zoom in and out based on horizontal mouse movement.

      :type: Literal['VERTICAL', 'HORIZONTAL']

   .. attribute:: view_zoom_method

      Which style to use for viewport scaling (default ``'DOLLY'``)

      - ``CONTINUE``
        Continue -- Continuous zooming. The zoom direction and speed depends on how far along the set Zoom Axis the mouse has moved..
      - ``DOLLY``
        Dolly -- Zoom in and out based on mouse movement along the set Zoom Axis.
      - ``SCALE``
        Scale -- Zoom in and out as if you are scaling the view, mouse movements relative to center.

      :type: Literal['CONTINUE', 'DOLLY', 'SCALE']

   .. data:: walk_navigation

      Settings for walk navigation mode (readonly, never None)

      :type: :class:`WalkNavigation`

   .. data:: xr_navigation

      Settings for navigation in XR (readonly, never None)

      :type: :class:`XrNavigation`

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

   - :class:`Preferences.inputs`

