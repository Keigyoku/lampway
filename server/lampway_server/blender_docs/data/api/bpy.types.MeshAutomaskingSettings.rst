MeshAutomaskingSettings(bpy_struct)
===================================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: MeshAutomaskingSettings(bpy_struct)

   Automasking settings for mesh painting & sculpting.

   .. attribute:: boundary_edges_propagation_steps

      Distance where boundary edge automasking is going to protect vertices from the fully masked edge (in [1, 20], default 1)

      :type: int

   .. attribute:: cavity_blur_steps

      The number of times the cavity mask is blurred (in [0, 25], default 0)

      :type: int

   .. data:: cavity_curve

      Curve used for the sensitivity (readonly)

      :type: :class:`CurveMapping` | None

   .. data:: cavity_curve_op

      Curve used for the sensitivity (readonly)

      :type: :class:`CurveMapping` | None

   .. attribute:: cavity_factor

      The contrast of the cavity mask (in [0, 5], default 1.0)

      :type: float

   .. attribute:: start_normal_falloff

      Extend the angular range with a falloff gradient (in [0.0001, 1], default 0.25)

      :type: float

   .. attribute:: start_normal_limit

      The range of angles that will be affected (in [0.0001, 3.14159], default 0.349066)

      :type: float

   .. attribute:: use_automasking_boundary_edges

      Do not affect non manifold boundary edges (default False)

      :type: bool

   .. attribute:: use_automasking_boundary_face_sets

      Do not affect vertices that belong to a face set boundary (default False)

      :type: bool

   .. attribute:: use_automasking_cavity

      Do not affect vertices on peaks, based on the surface curvature (default False)

      :type: bool

   .. attribute:: use_automasking_cavity_inverted

      Do not affect vertices within crevices, based on the surface curvature (default False)

      :type: bool

   .. attribute:: use_automasking_custom_cavity_curve

      Use custom curve (default False)

      :type: bool

   .. attribute:: use_automasking_face_sets

      Affect only vertices that share face sets with the active vertex (default False)

      :type: bool

   .. attribute:: use_automasking_start_normal

      Affect only vertices with a similar normal to where the stroke starts (default False)

      :type: bool

   .. attribute:: use_automasking_topology

      Affect only vertices connected to the active vertex under the brush (default False)

      :type: bool

   .. attribute:: use_automasking_view_normal

      Affect only vertices with a normal that faces the viewer (default False)

      :type: bool

   .. attribute:: use_automasking_view_occlusion

      Only affect vertices that are not occluded by other faces (slower performance) (default False)

      :type: bool

   .. attribute:: view_normal_falloff

      Extend the angular range with a falloff gradient (in [0.0001, 1], default 0.25)

      :type: float

   .. attribute:: view_normal_limit

      The range of angles that will be affected (in [0.0001, 3.14159], default 1.5708)

      :type: float

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

   - :class:`Brush.mesh_automasking_settings`
   - :class:`Paint.mesh_automasking_settings`

