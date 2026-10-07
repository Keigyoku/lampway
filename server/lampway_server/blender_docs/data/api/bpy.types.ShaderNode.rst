ShaderNode(NodeInternal)
========================

.. currentmodule:: bpy.types

base classes --- :class:`bpy_struct`, :class:`Node`, :class:`NodeInternal`

.. toctree::
   :caption: Subclasses
   :maxdepth: 1

   bpy.types.ShaderNodeAddShader.rst
   bpy.types.ShaderNodeAmbientOcclusion.rst
   bpy.types.ShaderNodeAttribute.rst
   bpy.types.ShaderNodeBackground.rst
   bpy.types.ShaderNodeBevel.rst
   bpy.types.ShaderNodeBlackbody.rst
   bpy.types.ShaderNodeBrightContrast.rst
   bpy.types.ShaderNodeBsdfAnisotropic.rst
   bpy.types.ShaderNodeBsdfDiffuse.rst
   bpy.types.ShaderNodeBsdfGlass.rst
   bpy.types.ShaderNodeBsdfHair.rst
   bpy.types.ShaderNodeBsdfHairPrincipled.rst
   bpy.types.ShaderNodeBsdfMetallic.rst
   bpy.types.ShaderNodeBsdfPrincipled.rst
   bpy.types.ShaderNodeBsdfRayPortal.rst
   bpy.types.ShaderNodeBsdfRefraction.rst
   bpy.types.ShaderNodeBsdfSheen.rst
   bpy.types.ShaderNodeBsdfToon.rst
   bpy.types.ShaderNodeBsdfTranslucent.rst
   bpy.types.ShaderNodeBsdfTransparent.rst
   bpy.types.ShaderNodeBump.rst
   bpy.types.ShaderNodeCameraData.rst
   bpy.types.ShaderNodeClamp.rst
   bpy.types.ShaderNodeCombineColor.rst
   bpy.types.ShaderNodeCombineXYZ.rst
   bpy.types.ShaderNodeCustomGroup.rst
   bpy.types.ShaderNodeDisplacement.rst
   bpy.types.ShaderNodeEeveeSpecular.rst
   bpy.types.ShaderNodeEmission.rst
   bpy.types.ShaderNodeFloatCurve.rst
   bpy.types.ShaderNodeFresnel.rst
   bpy.types.ShaderNodeGamma.rst
   bpy.types.ShaderNodeGroup.rst
   bpy.types.ShaderNodeHairInfo.rst
   bpy.types.ShaderNodeHoldout.rst
   bpy.types.ShaderNodeHueSaturation.rst
   bpy.types.ShaderNodeInvert.rst
   bpy.types.ShaderNodeLayerWeight.rst
   bpy.types.ShaderNodeLightFalloff.rst
   bpy.types.ShaderNodeLightPath.rst
   bpy.types.ShaderNodeMapRange.rst
   bpy.types.ShaderNodeMapping.rst
   bpy.types.ShaderNodeMath.rst
   bpy.types.ShaderNodeMix.rst
   bpy.types.ShaderNodeMixRGB.rst
   bpy.types.ShaderNodeMixShader.rst
   bpy.types.ShaderNodeNewGeometry.rst
   bpy.types.ShaderNodeNormal.rst
   bpy.types.ShaderNodeNormalMap.rst
   bpy.types.ShaderNodeObjectInfo.rst
   bpy.types.ShaderNodeOutputAOV.rst
   bpy.types.ShaderNodeOutputLight.rst
   bpy.types.ShaderNodeOutputLineStyle.rst
   bpy.types.ShaderNodeOutputMaterial.rst
   bpy.types.ShaderNodeOutputWorld.rst
   bpy.types.ShaderNodeParticleInfo.rst
   bpy.types.ShaderNodePointInfo.rst
   bpy.types.ShaderNodeRGB.rst
   bpy.types.ShaderNodeRGBCurve.rst
   bpy.types.ShaderNodeRGBToBW.rst
   bpy.types.ShaderNodeRadialTiling.rst
   bpy.types.ShaderNodeRaycast.rst
   bpy.types.ShaderNodeScript.rst
   bpy.types.ShaderNodeSeparateColor.rst
   bpy.types.ShaderNodeSeparateXYZ.rst
   bpy.types.ShaderNodeShaderToRGB.rst
   bpy.types.ShaderNodeSqueeze.rst
   bpy.types.ShaderNodeSubsurfaceScattering.rst
   bpy.types.ShaderNodeTangent.rst
   bpy.types.ShaderNodeTexBrick.rst
   bpy.types.ShaderNodeTexChecker.rst
   bpy.types.ShaderNodeTexCoord.rst
   bpy.types.ShaderNodeTexEnvironment.rst
   bpy.types.ShaderNodeTexGabor.rst
   bpy.types.ShaderNodeTexGradient.rst
   bpy.types.ShaderNodeTexIES.rst
   bpy.types.ShaderNodeTexImage.rst
   bpy.types.ShaderNodeTexMagic.rst
   bpy.types.ShaderNodeTexNoise.rst
   bpy.types.ShaderNodeTexSky.rst
   bpy.types.ShaderNodeTexVoronoi.rst
   bpy.types.ShaderNodeTexWave.rst
   bpy.types.ShaderNodeTexWhiteNoise.rst
   bpy.types.ShaderNodeUVAlongStroke.rst
   bpy.types.ShaderNodeUVMap.rst
   bpy.types.ShaderNodeValToRGB.rst
   bpy.types.ShaderNodeValue.rst
   bpy.types.ShaderNodeVectorCurve.rst
   bpy.types.ShaderNodeVectorDisplacement.rst
   bpy.types.ShaderNodeVectorMath.rst
   bpy.types.ShaderNodeVectorRotate.rst
   bpy.types.ShaderNodeVectorTransform.rst
   bpy.types.ShaderNodeVertexColor.rst
   bpy.types.ShaderNodeVolumeAbsorption.rst
   bpy.types.ShaderNodeVolumeCoefficients.rst
   bpy.types.ShaderNodeVolumeInfo.rst
   bpy.types.ShaderNodeVolumePrincipled.rst
   bpy.types.ShaderNodeVolumeScatter.rst
   bpy.types.ShaderNodeWavelength.rst
   bpy.types.ShaderNodeWireframe.rst

.. class:: ShaderNode(NodeInternal)

   Material shader node

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

References
----------

.. hlist::
   :columns: 2

   - :class:`ShaderNodeTree.get_output_node`

