CompositorNode(NodeInternal)
============================

.. currentmodule:: bpy.types

base classes --- :class:`bpy_struct`, :class:`Node`, :class:`NodeInternal`

.. toctree::
   :caption: Subclasses
   :maxdepth: 1

   bpy.types.CompositorNodeAlphaOver.rst
   bpy.types.CompositorNodeAntiAliasing.rst
   bpy.types.CompositorNodeBilateralblur.rst
   bpy.types.CompositorNodeBlankImage.rst
   bpy.types.CompositorNodeBlur.rst
   bpy.types.CompositorNodeBokehBlur.rst
   bpy.types.CompositorNodeBokehImage.rst
   bpy.types.CompositorNodeBoxMask.rst
   bpy.types.CompositorNodeBrightContrast.rst
   bpy.types.CompositorNodeChannelMatte.rst
   bpy.types.CompositorNodeChromaMatte.rst
   bpy.types.CompositorNodeColorBalance.rst
   bpy.types.CompositorNodeColorCorrection.rst
   bpy.types.CompositorNodeColorMatte.rst
   bpy.types.CompositorNodeColorSpill.rst
   bpy.types.CompositorNodeCombineColor.rst
   bpy.types.CompositorNodeConvertColorSpace.rst
   bpy.types.CompositorNodeConvertToDisplay.rst
   bpy.types.CompositorNodeConvolve.rst
   bpy.types.CompositorNodeCornerPin.rst
   bpy.types.CompositorNodeCrop.rst
   bpy.types.CompositorNodeCryptomatte.rst
   bpy.types.CompositorNodeCryptomatteV2.rst
   bpy.types.CompositorNodeCurveRGB.rst
   bpy.types.CompositorNodeCustomGroup.rst
   bpy.types.CompositorNodeDBlur.rst
   bpy.types.CompositorNodeDefocus.rst
   bpy.types.CompositorNodeDenoise.rst
   bpy.types.CompositorNodeDespeckle.rst
   bpy.types.CompositorNodeDiffMatte.rst
   bpy.types.CompositorNodeDilateErode.rst
   bpy.types.CompositorNodeDisplace.rst
   bpy.types.CompositorNodeDistanceMatte.rst
   bpy.types.CompositorNodeDoubleEdgeMask.rst
   bpy.types.CompositorNodeEllipseMask.rst
   bpy.types.CompositorNodeExposure.rst
   bpy.types.CompositorNodeFilter.rst
   bpy.types.CompositorNodeFlip.rst
   bpy.types.CompositorNodeGamma.rst
   bpy.types.CompositorNodeGlare.rst
   bpy.types.CompositorNodeGroup.rst
   bpy.types.CompositorNodeHueCorrect.rst
   bpy.types.CompositorNodeHueSat.rst
   bpy.types.CompositorNodeIDMask.rst
   bpy.types.CompositorNodeImage.rst
   bpy.types.CompositorNodeImageCoordinates.rst
   bpy.types.CompositorNodeImageInfo.rst
   bpy.types.CompositorNodeInpaint.rst
   bpy.types.CompositorNodeInvert.rst
   bpy.types.CompositorNodeKeying.rst
   bpy.types.CompositorNodeKeyingScreen.rst
   bpy.types.CompositorNodeKuwahara.rst
   bpy.types.CompositorNodeLensdist.rst
   bpy.types.CompositorNodeLevels.rst
   bpy.types.CompositorNodeLumaMatte.rst
   bpy.types.CompositorNodeMapUV.rst
   bpy.types.CompositorNodeMask.rst
   bpy.types.CompositorNodeMaskToSDF.rst
   bpy.types.CompositorNodeMovieClip.rst
   bpy.types.CompositorNodeMovieDistortion.rst
   bpy.types.CompositorNodeNormal.rst
   bpy.types.CompositorNodeNormalize.rst
   bpy.types.CompositorNodeOutputFile.rst
   bpy.types.CompositorNodePixelate.rst
   bpy.types.CompositorNodePlaneTrackDeform.rst
   bpy.types.CompositorNodePosterize.rst
   bpy.types.CompositorNodePremulKey.rst
   bpy.types.CompositorNodeRGB.rst
   bpy.types.CompositorNodeRGBToBW.rst
   bpy.types.CompositorNodeRLayers.rst
   bpy.types.CompositorNodeRelativeToPixel.rst
   bpy.types.CompositorNodeRotate.rst
   bpy.types.CompositorNodeScale.rst
   bpy.types.CompositorNodeSceneTime.rst
   bpy.types.CompositorNodeSeparateColor.rst
   bpy.types.CompositorNodeSequencerStripInfo.rst
   bpy.types.CompositorNodeSetAlpha.rst
   bpy.types.CompositorNodeSplit.rst
   bpy.types.CompositorNodeStabilize.rst
   bpy.types.CompositorNodeStringToImage.rst
   bpy.types.CompositorNodeSwitch.rst
   bpy.types.CompositorNodeSwitchView.rst
   bpy.types.CompositorNodeTime.rst
   bpy.types.CompositorNodeTonemap.rst
   bpy.types.CompositorNodeTrackPos.rst
   bpy.types.CompositorNodeTransform.rst
   bpy.types.CompositorNodeTranslate.rst
   bpy.types.CompositorNodeVecBlur.rst
   bpy.types.CompositorNodeViewer.rst
   bpy.types.CompositorNodeZcombine.rst

.. class:: CompositorNode(NodeInternal)


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

