StripProxy(bpy_struct)
======================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: StripProxy(bpy_struct)

   Proxy parameters for a sequence strip

   .. attribute:: build_100

      Build 100% proxy resolution (default False)

      :type: bool

   .. attribute:: build_25

      Build 25% proxy resolution (default False)

      :type: bool

   .. attribute:: build_50

      Build 50% proxy resolution (default False)

      :type: bool

   .. attribute:: build_75

      Build 75% proxy resolution (default False)

      :type: bool

   .. attribute:: directory

      Location to store the proxy files (default "", never None, blend relative ``//`` prefix supported)

      :type: str

   .. attribute:: filepath

      Location of custom proxy file (default "", never None, blend relative ``//`` prefix supported)

      :type: str

   .. attribute:: quality

      Quality of proxies to build (in [0, 32767], default 0)

      :type: int

   .. attribute:: use_overwrite

      Overwrite existing proxy files when building (default False)

      :type: bool

   .. attribute:: use_proxy_custom_directory

      Use a custom directory to store data (default False)

      :type: bool

   .. attribute:: use_proxy_custom_file

      Use a custom file to read proxy data from (default False)

      :type: bool

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

   - :class:`EffectStrip.proxy`
   - :class:`ImageStrip.proxy`
   - :class:`MetaStrip.proxy`
   - :class:`MovieStrip.proxy`
   - :class:`SceneStrip.proxy`

