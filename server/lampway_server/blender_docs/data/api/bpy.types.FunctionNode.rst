FunctionNode(NodeInternal)
==========================

.. currentmodule:: bpy.types

base classes --- :class:`bpy_struct`, :class:`Node`, :class:`NodeInternal`

.. toctree::
   :caption: Subclasses
   :maxdepth: 1

   bpy.types.FunctionNodeAlignEulerToVector.rst
   bpy.types.FunctionNodeAlignRotationToVector.rst
   bpy.types.FunctionNodeAxesToRotation.rst
   bpy.types.FunctionNodeAxisAngleToRotation.rst
   bpy.types.FunctionNodeBitMath.rst
   bpy.types.FunctionNodeBooleanMath.rst
   bpy.types.FunctionNodeCombineColor.rst
   bpy.types.FunctionNodeCombineMatrix.rst
   bpy.types.FunctionNodeCombineTransform.rst
   bpy.types.FunctionNodeCompare.rst
   bpy.types.FunctionNodeEulerToRotation.rst
   bpy.types.FunctionNodeFindInString.rst
   bpy.types.FunctionNodeFloatToInt.rst
   bpy.types.FunctionNodeFormatString.rst
   bpy.types.FunctionNodeHashValue.rst
   bpy.types.FunctionNodeInputBool.rst
   bpy.types.FunctionNodeInputColor.rst
   bpy.types.FunctionNodeInputInt.rst
   bpy.types.FunctionNodeInputIntVector.rst
   bpy.types.FunctionNodeInputMenu.rst
   bpy.types.FunctionNodeInputRotation.rst
   bpy.types.FunctionNodeInputSpecialCharacters.rst
   bpy.types.FunctionNodeInputString.rst
   bpy.types.FunctionNodeInputVector.rst
   bpy.types.FunctionNodeIntegerMath.rst
   bpy.types.FunctionNodeInvertMatrix.rst
   bpy.types.FunctionNodeInvertRotation.rst
   bpy.types.FunctionNodeMatchString.rst
   bpy.types.FunctionNodeMatrixDeterminant.rst
   bpy.types.FunctionNodeMatrixMultiply.rst
   bpy.types.FunctionNodeMatrixSVD.rst
   bpy.types.FunctionNodeProjectPoint.rst
   bpy.types.FunctionNodeQuaternionToRotation.rst
   bpy.types.FunctionNodeRandomValue.rst
   bpy.types.FunctionNodeReplaceString.rst
   bpy.types.FunctionNodeReverseString.rst
   bpy.types.FunctionNodeRotateEuler.rst
   bpy.types.FunctionNodeRotateRotation.rst
   bpy.types.FunctionNodeRotateVector.rst
   bpy.types.FunctionNodeRotationToAxisAngle.rst
   bpy.types.FunctionNodeRotationToEuler.rst
   bpy.types.FunctionNodeRotationToQuaternion.rst
   bpy.types.FunctionNodeSeparateColor.rst
   bpy.types.FunctionNodeSeparateMatrix.rst
   bpy.types.FunctionNodeSeparateTransform.rst
   bpy.types.FunctionNodeSetStringCase.rst
   bpy.types.FunctionNodeSliceString.rst
   bpy.types.FunctionNodeSplitString.rst
   bpy.types.FunctionNodeStringLength.rst
   bpy.types.FunctionNodeStringToValue.rst
   bpy.types.FunctionNodeTransformDirection.rst
   bpy.types.FunctionNodeTransformPoint.rst
   bpy.types.FunctionNodeTransposeMatrix.rst
   bpy.types.FunctionNodeTrimString.rst
   bpy.types.FunctionNodeValueToString.rst

.. class:: FunctionNode(NodeInternal)


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
   - :class:`Node.type`
   - :class:`Node.location`
   - :class:`Node.location_absolute`
   - :class:`Node.width`
   - :class:`Node.height`
   - :class:`Node.dimensions`
   - :class:`Node.name`
   - :class:`Node.label`
   - :class:`Node.inputs`
   - :class:`Node.outputs`
   - :class:`Node.panel_states`
   - :class:`Node.internal_links`
   - :class:`Node.parent`
   - :class:`Node.warning_propagation`
   - :class:`Node.use_custom_color`
   - :class:`Node.color`
   - :class:`Node.color_tag`
   - :class:`Node.select`
   - :class:`Node.show_options`
   - :class:`Node.show_preview`
   - :class:`Node.hide`
   - :class:`Node.mute`
   - :class:`Node.show_texture`
   - :class:`Node.bl_idname`
   - :class:`Node.bl_label`
   - :class:`Node.bl_description`
   - :class:`Node.bl_icon`
   - :class:`Node.bl_static_type`
   - :class:`Node.bl_width_default`
   - :class:`Node.bl_width_min`
   - :class:`Node.bl_width_max`
   - :class:`Node.bl_height_default`
   - :class:`Node.bl_height_min`
   - :class:`Node.bl_height_max`

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
   - :class:`Node.bl_system_properties_get`
   - :class:`Node.socket_value_update`
   - :class:`Node.is_registered_node_type`
   - :class:`Node.poll`
   - :class:`Node.poll_instance`
   - :class:`Node.update`
   - :class:`Node.insert_link`
   - :class:`Node.init`
   - :class:`Node.copy`
   - :class:`Node.free`
   - :class:`Node.draw_buttons`
   - :class:`Node.draw_buttons_ext`
   - :class:`Node.draw_label`
   - :class:`Node.debug_zone_body_lazy_function_graph`
   - :class:`Node.debug_zone_lazy_function_graph`
   - :class:`Node.poll`
   - :class:`Node.bl_rna_get_subclass`
   - :class:`Node.bl_rna_get_subclass_py`
   - :class:`NodeInternal.poll`
   - :class:`NodeInternal.poll_instance`
   - :class:`NodeInternal.update`
   - :class:`NodeInternal.draw_buttons`
   - :class:`NodeInternal.draw_buttons_ext`
   - :class:`NodeInternal.bl_rna_get_subclass`
   - :class:`NodeInternal.bl_rna_get_subclass_py`

