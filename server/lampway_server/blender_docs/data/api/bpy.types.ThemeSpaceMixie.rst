ThemeSpaceMixie(bpy_struct)
===========================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: ThemeSpaceMixie(bpy_struct)

   Theme settings for Lampway/Moodboard space

   .. attribute:: mixar_action_button

      Background color for Generate / action buttons (array of 4 items, in [0, 1], default (0.117647, 0.133333, 0.176471, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_tab_accent

      Active tab fill color (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_tab_glow

      Outer glow color for the active tab (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 0.14902))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_tab_highlight

      Inner glass highlight on the active tab (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 0.180392))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_tab_inactive

      Inactive tab fill color (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 0.6))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_tab_indicator

      Edge indicator bar color on the active tab (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 0.4))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_tab_strip_background

      Background color for the tab strip (array of 4 items, in [0, 1], default (0.054902, 0.0627451, 0.0862745, 0.94902))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_tab_text_active

      Text color for the active tab (array of 4 items, in [0, 1], default (0.968627, 0.956863, 0.933333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_tab_text_inactive

      Text color for inactive tabs (array of 4 items, in [0, 1], default (0.662745, 0.65098, 0.615686, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: mixar_toggle_active

      Track color for toggles when checked (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: moodboard_button_background

      Background color for buttons (array of 4 items, in [0, 1], default (0.117647, 0.133333, 0.176471, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: moodboard_button_hover

      Button hover overlay color (array of 4 items, in [0, 1], default (0.14902, 0.168627, 0.219608, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: moodboard_button_text

      Text color for buttons (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: moodboard_corner_radius

      Corner radius for rounded UI elements (in [0, 20], default 8.0)

      :type: float

   .. attribute:: moodboard_input_background

      Background color for text input fields (array of 4 items, in [0, 1], default (0.0666667, 0.0745098, 0.101961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: moodboard_input_border

      Border color for text input fields (array of 4 items, in [0, 1], default (0.168627, 0.188235, 0.239216, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: moodboard_input_border_width

      Border width for text input fields (in [0, 5], default 1.0)

      :type: float

   .. attribute:: moodboard_input_text

      Text color for input fields (array of 4 items, in [0, 1], default (0.92549, 0.909804, 0.87451, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: moodboard_label_text

      Text color for labels (array of 4 items, in [0, 1], default (0.662745, 0.65098, 0.615686, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: moodboard_panel_background

      Background color for panels (array of 4 items, in [0, 1], default (0.0862745, 0.0980392, 0.133333, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. data:: space

      Settings for space (readonly, never None)

      :type: :class:`ThemeSpaceGeneric`

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

   - :class:`Theme.mixie`

