USDHook(bpy_struct)
===================

.. currentmodule:: bpy.types


USD Hook Example
++++++++++++++++

This example shows an implementation of ``USDHook`` to extend USD
export and import functionality.

Callback Function API
---------------------

One may optionally define any or all of the following callback functions
in the ``USDHook`` subclass.

on_export
^^^^^^^^^

Called before the USD export finalizes, allowing modifications to the USD
stage immediately before it is saved.

Args:

- ``export_context`` (`USDSceneExportContext`_): Provides access to the stage and dependency graph

Returns:

- ``True`` on success or ``False`` if the operation was bypassed or otherwise failed to complete

on_material_export
^^^^^^^^^^^^^^^^^^

Called for each material that is exported, allowing modifications to the USD material,
such as shader generation.

Args:

- ``export_context`` (`USDMaterialExportContext`_): Provides access to the stage and a texture export utility function
- ``bl_material`` (``bpy.types.Material``): The source Blender material
- ``usd_material`` (``pxr.UsdShade.Material``): The target USD material to be exported

Returns:

- ``True`` on success or ``False`` if the operation was bypassed or otherwise failed to complete

Note that the target USD material might already have connected shaders created by the USD exporter or
by other material export hooks.

on_import
^^^^^^^^^

Called after the USD import finalizes.

Args:

- ``import_context`` (`USDSceneImportContext`_):
  Provides access to the stage and a map associating USD prim paths and Blender IDs

Returns:

- ``True`` on success or ``False`` if the operation was bypassed or otherwise failed to complete


material_import_poll
^^^^^^^^^^^^^^^^^^^^

Called to determine if the ``USDHook`` implementation can convert a given USD material.

Args:

- ``import_context`` (`USDMaterialImportContext`_): Provides access to the stage and a texture import utility function
- ``usd_material`` (``pxr.UsdShade.Material``): The source USD material to be exported

Returns:

- ``True`` if the hook can convert the material or ``False`` otherwise

If any hook returns ``True`` from ``material_import_poll``, the USD importer will skip standard ``USD Preview Surface``
or ``MaterialX`` import and invoke the hook's `on_material_import`_ method to convert the material instead.

on_material_import
^^^^^^^^^^^^^^^^^^

Called for each material that is imported, to allow converting the USD material to nodes on the Blender material.
To ensure that this function gets called, the hook must also implement the ``material_import_poll()``
callback to return ``True`` for the given USD material.

Args:

- ``import_context`` (`USDMaterialImportContext`_): Provides access to the stage and a texture import utility function
- ``bl_material`` (``bpy.types.Material``): The target Blender material with an empty node tree
- ``usd_material`` (``pxr.UsdShade.Material``): The source USD material to be imported

Returns:

- ``True`` on success or ``False`` if the conversion failed or otherwise did not complete


Context Classes
---------------

Instances of the following built-in classes are provided as arguments to the callbacks.

USDSceneExportContext
^^^^^^^^^^^^^^^^^^^^^

Argument for `on_export`_.

Methods:

- ``get_stage()``: returns the USD stage to be saved
- ``get_depsgraph()``: returns the Blender scene dependency graph
- ``get_prim_map()`` returns a ``dict`` where the key is an exported USD Prim path and the value a ``list``
  of the IDs associated with that prim.


USDMaterialExportContext
^^^^^^^^^^^^^^^^^^^^^^^^

Argument for `on_material_export`_.

Methods:

- ``get_stage()``: returns the USD stage to be saved
- ``export_texture(image: bpy.types.Image)``: Returns the USD asset path for the given texture image

The ``export_texture`` function will save in-memory images and may copy texture assets,
depending on the current USD export options.
For example, by default calling ``export_texture(/foo/bar.png)`` will copy the file to a ``textures``
directory next to the exported USD and will return the relative path ``./textures/bar.png``.


USDSceneImportContext
^^^^^^^^^^^^^^^^^^^^^

Argument for `on_import`_.

Methods:

- ``get_prim_map()`` returns a ``dict`` where the key is an imported USD Prim path and the value a ``list``
  of the IDs created by the imported prim.
- ``get_stage()`` returns the USD stage which was imported.


USDMaterialImportContext
^^^^^^^^^^^^^^^^^^^^^^^^

Argument for `material_import_poll`_ and `on_material_import`_.

Methods:

- ``get_stage()``:
  returns the USD stage to be saved.
- ``import_texture(asset_path: str)``:
  for the given USD texture asset path, returns a ``tuple[str, bool]``,
  containing the asset's local path and a bool indicating whether the path references a temporary file.

The ``import_texture`` function may copy the texture to the local file system if the given asset path is a
package-relative path for a USDZ archive, depending on the current USD ``Import Textures`` options.
When the ``Import Textures`` mode is ``Packed``, the texture is saved to a temporary location and the
second element of the returned tuple is ``True``, indicating that the file is temporary, in which
case it may be necessary to pack the image. The original asset path will be returned unchanged if it's
already a local file or if it could not be copied to a local destination.


Errors
------

Exceptions raised by these functions will be reported in Blender with the exception details printed to the console.


Example Code
------------

The ``USDHookExample`` class in the example below implements the following functions:

- ``on_export()`` function to add custom data to the stage's root layer.
- ``on_material_export()`` function to create a simple ``MaterialX`` shader on the given USD material.
- ``on_import()`` function to create a text object to display the stage's custom layer data.
- ``material_import_poll()`` returns ``True`` if the given USD material has an ``mtlx`` context.
- ``on_material_import()`` function to convert a simple ``MaterialX`` shader with a ``base_color`` input.

.. literalinclude:: ../examples/bpy.types.USDHook.0.py
   :lines: 183-

base class --- :class:`bpy_struct`


.. class:: USDHook(bpy_struct)

   Defines callback functions to extend USD IO

   .. attribute:: bl_description

      A short description of the USD hook (default "", never None)

      :type: str

   .. attribute:: bl_idname

      (default "", never None)

      :type: str

   .. attribute:: bl_label

      (default "", never None)

      :type: str

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

