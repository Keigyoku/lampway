ThemeAgentBubble(bpy_struct)
============================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: ThemeAgentBubble(bpy_struct)

   Theme settings for the floating Agent Bubble

   .. attribute:: agent_accent

      Agent island accent (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: agent_border

      Agent island border (array of 4 items, in [0, 1], default (0.231373, 0.258824, 0.321569, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: agent_tab_active

      Agent island active tab (array of 4 items, in [0, 1], default (0.227451, 0.184314, 0.0901961, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: background_alpha

      Opacity of the window background (lower = more frosted glass) (in [0, 1], default 0.0)

      :type: float

   .. attribute:: footer_background

      Background color for the input / send-button region (array of 4 items, in [0, 1], default (0.054902, 0.0627451, 0.0862745, 1.0))

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

   - :class:`Theme.agent_bubble`

