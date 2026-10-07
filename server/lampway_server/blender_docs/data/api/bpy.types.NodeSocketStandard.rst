NodeSocketStandard(NodeSocket)
==============================

.. currentmodule:: bpy.types

base classes --- :class:`bpy_struct`, :class:`NodeSocket`

.. toctree::
   :caption: Subclasses
   :maxdepth: 1

   bpy.types.NodeSocketBool.rst
   bpy.types.NodeSocketBundle.rst
   bpy.types.NodeSocketClosure.rst
   bpy.types.NodeSocketCollection.rst
   bpy.types.NodeSocketColor.rst
   bpy.types.NodeSocketFloat.rst
   bpy.types.NodeSocketFloatAngle.rst
   bpy.types.NodeSocketFloatColorTemperature.rst
   bpy.types.NodeSocketFloatDistance.rst
   bpy.types.NodeSocketFloatFactor.rst
   bpy.types.NodeSocketFloatFrequency.rst
   bpy.types.NodeSocketFloatMass.rst
   bpy.types.NodeSocketFloatPercentage.rst
   bpy.types.NodeSocketFloatPixel.rst
   bpy.types.NodeSocketFloatTime.rst
   bpy.types.NodeSocketFloatTimeAbsolute.rst
   bpy.types.NodeSocketFloatUnsigned.rst
   bpy.types.NodeSocketFloatWavelength.rst
   bpy.types.NodeSocketFont.rst
   bpy.types.NodeSocketGeometry.rst
   bpy.types.NodeSocketImage.rst
   bpy.types.NodeSocketInt.rst
   bpy.types.NodeSocketIntFactor.rst
   bpy.types.NodeSocketIntPercentage.rst
   bpy.types.NodeSocketIntPixel.rst
   bpy.types.NodeSocketIntUnsigned.rst
   bpy.types.NodeSocketIntVector2D.rst
   bpy.types.NodeSocketIntVector3D.rst
   bpy.types.NodeSocketIntVectorFactor2D.rst
   bpy.types.NodeSocketIntVectorFactor3D.rst
   bpy.types.NodeSocketIntVectorPercentage2D.rst
   bpy.types.NodeSocketIntVectorPercentage3D.rst
   bpy.types.NodeSocketIntVectorPixel2D.rst
   bpy.types.NodeSocketIntVectorPixel3D.rst
   bpy.types.NodeSocketIntVectorUnsigned2D.rst
   bpy.types.NodeSocketIntVectorUnsigned3D.rst
   bpy.types.NodeSocketMask.rst
   bpy.types.NodeSocketMaterial.rst
   bpy.types.NodeSocketMatrix.rst
   bpy.types.NodeSocketMenu.rst
   bpy.types.NodeSocketObject.rst
   bpy.types.NodeSocketRotation.rst
   bpy.types.NodeSocketScene.rst
   bpy.types.NodeSocketShader.rst
   bpy.types.NodeSocketSound.rst
   bpy.types.NodeSocketString.rst
   bpy.types.NodeSocketStringFilePath.rst
   bpy.types.NodeSocketText.rst
   bpy.types.NodeSocketTexture.rst
   bpy.types.NodeSocketVector.rst
   bpy.types.NodeSocketVector2D.rst
   bpy.types.NodeSocketVector4D.rst
   bpy.types.NodeSocketVectorAcceleration.rst
   bpy.types.NodeSocketVectorAcceleration2D.rst
   bpy.types.NodeSocketVectorAcceleration4D.rst
   bpy.types.NodeSocketVectorDirection.rst
   bpy.types.NodeSocketVectorDirection2D.rst
   bpy.types.NodeSocketVectorDirection4D.rst
   bpy.types.NodeSocketVectorEuler.rst
   bpy.types.NodeSocketVectorEuler2D.rst
   bpy.types.NodeSocketVectorEuler4D.rst
   bpy.types.NodeSocketVectorFactor.rst
   bpy.types.NodeSocketVectorFactor2D.rst
   bpy.types.NodeSocketVectorFactor4D.rst
   bpy.types.NodeSocketVectorPercentage.rst
   bpy.types.NodeSocketVectorPercentage2D.rst
   bpy.types.NodeSocketVectorPercentage4D.rst
   bpy.types.NodeSocketVectorPixel.rst
   bpy.types.NodeSocketVectorPixel2D.rst
   bpy.types.NodeSocketVectorPixel4D.rst
   bpy.types.NodeSocketVectorTranslation.rst
   bpy.types.NodeSocketVectorTranslation2D.rst
   bpy.types.NodeSocketVectorTranslation4D.rst
   bpy.types.NodeSocketVectorVelocity.rst
   bpy.types.NodeSocketVectorVelocity2D.rst
   bpy.types.NodeSocketVectorVelocity4D.rst
   bpy.types.NodeSocketVectorXYZ.rst
   bpy.types.NodeSocketVectorXYZ2D.rst
   bpy.types.NodeSocketVectorXYZ4D.rst
   bpy.types.NodeSocketVirtual.rst

.. class:: NodeSocketStandard(NodeSocket)


   .. data:: links

      List of node links from or to this socket.
      
      :type: :class:`NodeLinks`
      
      .. note:: Takes ``O(len(nodetree.links))`` time.

      (readonly)

   .. method:: draw(context, layout, node, text)

      Draw socket

      :param context: (never None)
      :type context: :class:`Context` | None
      :param layout: Layout, Layout in the UI (never None)
      :type layout: :class:`UILayout` | None
      :param node: Node, Node the socket belongs to (never None)
      :type node: :class:`Node` | None
      :param text: Text, Text label to draw alongside properties (never None)
      :type text: str

   .. method:: draw_color(context, node)

      Color of the socket icon

      :param context: (never None)
      :type context: :class:`Context` | None
      :param node: Node, Node the socket belongs to (never None)
      :type node: :class:`Node` | None
      :return: Color, (array of 4 items, in [0, 1])
      :rtype: :class:`bpy_prop_array`\ [float]

   .. classmethod:: draw_color_simple()

      Color of the socket icon

      :return: Color, (array of 4 items, in [0, 1])
      :rtype: :class:`bpy_prop_array`\ [float]

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
   - :class:`NodeSocket.name`
   - :class:`NodeSocket.label`
   - :class:`NodeSocket.identifier`
   - :class:`NodeSocket.description`
   - :class:`NodeSocket.is_output`
   - :class:`NodeSocket.select`
   - :class:`NodeSocket.hide`
   - :class:`NodeSocket.enabled`
   - :class:`NodeSocket.link_limit`
   - :class:`NodeSocket.is_linked`
   - :class:`NodeSocket.is_unavailable`
   - :class:`NodeSocket.is_multi_input`
   - :class:`NodeSocket.show_expanded`
   - :class:`NodeSocket.is_inactive`
   - :class:`NodeSocket.is_icon_visible`
   - :class:`NodeSocket.hide_value`
   - :class:`NodeSocket.pin_gizmo`
   - :class:`NodeSocket.node`
   - :class:`NodeSocket.type`
   - :class:`NodeSocket.display_shape`
   - :class:`NodeSocket.inferred_structure_type`
   - :class:`NodeSocket.bl_idname`
   - :class:`NodeSocket.bl_label`
   - :class:`NodeSocket.bl_subtype_label`
   - :class:`NodeSocket.links`

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
   - :class:`NodeSocket.bl_system_properties_get`
   - :class:`NodeSocket.draw`
   - :class:`NodeSocket.draw_color`
   - :class:`NodeSocket.draw_color_simple`
   - :class:`NodeSocket.bl_rna_get_subclass`
   - :class:`NodeSocket.bl_rna_get_subclass_py`

