XrViewfinderState(bpy_struct)
=============================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: XrViewfinderState(bpy_struct)

   Runtime state information about the VR Location Scouting Viewfinder

   .. attribute:: active_action_confirm

      Active viewfinder confirm action (default ``'CONFIRM'``)

      :type: Literal['CANCEL', 'CONFIRM']

   .. attribute:: active_action_live

      Active viewfinder live action (default ``'LENS'``)

      :type: Literal['LENS', 'DOF', 'FOCUS', 'APERTURE']

   .. attribute:: active_action_playback

      Active viewfinder playback action (default ``'BROWSE'``)

      :type: Literal['BROWSE', 'PREVIEW', 'DELETE']

   .. attribute:: active_mode

      Active viewfinder mode, live or playback (default ``'LIVE'``)

      - ``LIVE``
        Live Mode -- Capture a shot using the viewfinder.
      - ``PLAYBACK``
        Playback Mode -- Preview and playback captured shots in the viewfinder.
      - ``CONFIRM``
        Confirmation Mode -- Confirm user action.

      :type: Literal['LIVE', 'PLAYBACK', 'CONFIRM']

   .. attribute:: capture_dof_distance

      Viewfinder capture distance to the focus point for depth of field (in [-inf, inf], default 0.0)

      :type: float

   .. attribute:: capture_dof_enabled

      Enable viewfinder capture depth of field (default False)

      :type: bool

   .. attribute:: capture_dof_fstop

      Viewfinder capture f-stop ratio (in [-inf, inf], default 0.0)

      :type: float

   .. attribute:: capture_lens_focal

      Viewfinder capture focal length value in millimeters (in [-inf, inf], default 0.0)

      :type: float

   .. data:: location

      Last known location of the viewfinder in world space (array of 3 items, in [-inf, inf], default (0.0, 0.0, 0.0), readonly)

      :type: :class:`mathutils.Vector`

   .. data:: orientation

      Last known orientation of the viewfinder in world space (array of 4 items, in [-inf, inf], default (0.0, 0.0, 0.0, 0.0), readonly)

      :type: :class:`mathutils.Quaternion`

   .. attribute:: playback_show_active_capture_in_space_enabled

      Display active capture in space when in Viewfinder Playback mode (default False)

      :type: bool

   .. method:: trigger_flash()

      Trigger the Viewfinder flash to indicate a shot was captured


   .. method:: trigger_focus_indicator(hit_success)

      Blink the Viewfinder crosshair to indicate whether a focus action hit a target

      :param hit_success: Hit success, True to blink the success color, False to blink the miss color
      :type hit_success: bool

   .. method:: reset_view_smoothing()

      Reset the Viewfinder continuous view smoothing


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

   - :class:`XrSessionState.viewfinder`

