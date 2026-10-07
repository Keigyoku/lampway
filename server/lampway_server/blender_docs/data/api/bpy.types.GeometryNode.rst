GeometryNode(NodeInternal)
==========================

.. currentmodule:: bpy.types

base classes --- :class:`bpy_struct`, :class:`Node`, :class:`NodeInternal`

.. toctree::
   :caption: Subclasses
   :maxdepth: 1

   bpy.types.GeometryNodeAccumulateField.rst
   bpy.types.GeometryNodeApplySimulatedData.rst
   bpy.types.GeometryNodeAttributeDomainSize.rst
   bpy.types.GeometryNodeAttributeStatistic.rst
   bpy.types.GeometryNodeBake.rst
   bpy.types.GeometryNodeBlurAttribute.rst
   bpy.types.GeometryNodeBoneInfo.rst
   bpy.types.GeometryNodeBoundBox.rst
   bpy.types.GeometryNodeCameraInfo.rst
   bpy.types.GeometryNodeCaptureAttribute.rst
   bpy.types.GeometryNodeClosureToList.rst
   bpy.types.GeometryNodeClusterByConnected.rst
   bpy.types.GeometryNodeClusterByDistance.rst
   bpy.types.GeometryNodeCollectionChildren.rst
   bpy.types.GeometryNodeCollectionInfo.rst
   bpy.types.GeometryNodeConvexHull.rst
   bpy.types.GeometryNodeCornersOfEdge.rst
   bpy.types.GeometryNodeCornersOfFace.rst
   bpy.types.GeometryNodeCornersOfVertex.rst
   bpy.types.GeometryNodeCubeGridTopology.rst
   bpy.types.GeometryNodeCurveArc.rst
   bpy.types.GeometryNodeCurveEndpointSelection.rst
   bpy.types.GeometryNodeCurveHandleTypeSelection.rst
   bpy.types.GeometryNodeCurveLength.rst
   bpy.types.GeometryNodeCurveOfPoint.rst
   bpy.types.GeometryNodeCurvePrimitiveBezierSegment.rst
   bpy.types.GeometryNodeCurvePrimitiveCircle.rst
   bpy.types.GeometryNodeCurvePrimitiveLine.rst
   bpy.types.GeometryNodeCurvePrimitiveQuadrilateral.rst
   bpy.types.GeometryNodeCurveQuadraticBezier.rst
   bpy.types.GeometryNodeCurveSetHandles.rst
   bpy.types.GeometryNodeCurveSpiral.rst
   bpy.types.GeometryNodeCurveSplineType.rst
   bpy.types.GeometryNodeCurveStar.rst
   bpy.types.GeometryNodeCurveToMesh.rst
   bpy.types.GeometryNodeCurveToPoints.rst
   bpy.types.GeometryNodeCurvesToGreasePencil.rst
   bpy.types.GeometryNodeCustomGroup.rst
   bpy.types.GeometryNodeDeformCurvesOnSurface.rst
   bpy.types.GeometryNodeDeleteGeometry.rst
   bpy.types.GeometryNodeDistributePointsInGrid.rst
   bpy.types.GeometryNodeDistributePointsInVolume.rst
   bpy.types.GeometryNodeDistributePointsOnFaces.rst
   bpy.types.GeometryNodeDualMesh.rst
   bpy.types.GeometryNodeDuplicateElements.rst
   bpy.types.GeometryNodeEdgePathsToCurves.rst
   bpy.types.GeometryNodeEdgePathsToSelection.rst
   bpy.types.GeometryNodeEdgesOfCorner.rst
   bpy.types.GeometryNodeEdgesOfVertex.rst
   bpy.types.GeometryNodeEdgesToFaceGroups.rst
   bpy.types.GeometryNodeExtrudeMesh.rst
   bpy.types.GeometryNodeFaceOfCorner.rst
   bpy.types.GeometryNodeFieldAtIndex.rst
   bpy.types.GeometryNodeFieldAverage.rst
   bpy.types.GeometryNodeFieldMinAndMax.rst
   bpy.types.GeometryNodeFieldOnDomain.rst
   bpy.types.GeometryNodeFieldToGrid.rst
   bpy.types.GeometryNodeFieldToList.rst
   bpy.types.GeometryNodeFieldVariance.rst
   bpy.types.GeometryNodeFillCurve.rst
   bpy.types.GeometryNodeFilletCurve.rst
   bpy.types.GeometryNodeFilterList.rst
   bpy.types.GeometryNodeFlipFaces.rst
   bpy.types.GeometryNodeForeachGeometryElementInput.rst
   bpy.types.GeometryNodeForeachGeometryElementOutput.rst
   bpy.types.GeometryNodeGeometryToInstance.rst
   bpy.types.GeometryNodeGetAttributeNames.rst
   bpy.types.GeometryNodeGetGeometryBundle.rst
   bpy.types.GeometryNodeGetGeometryComponent.rst
   bpy.types.GeometryNodeGetNamedGrid.rst
   bpy.types.GeometryNodeGizmoDial.rst
   bpy.types.GeometryNodeGizmoLinear.rst
   bpy.types.GeometryNodeGizmoTransform.rst
   bpy.types.GeometryNodeGreasePencilToCurves.rst
   bpy.types.GeometryNodeGridAdvect.rst
   bpy.types.GeometryNodeGridClip.rst
   bpy.types.GeometryNodeGridCurl.rst
   bpy.types.GeometryNodeGridDilateAndErode.rst
   bpy.types.GeometryNodeGridDivergence.rst
   bpy.types.GeometryNodeGridGradient.rst
   bpy.types.GeometryNodeGridInfo.rst
   bpy.types.GeometryNodeGridLaplacian.rst
   bpy.types.GeometryNodeGridMean.rst
   bpy.types.GeometryNodeGridMedian.rst
   bpy.types.GeometryNodeGridPrune.rst
   bpy.types.GeometryNodeGridToMesh.rst
   bpy.types.GeometryNodeGridToPoints.rst
   bpy.types.GeometryNodeGridVoxelize.rst
   bpy.types.GeometryNodeGroup.rst
   bpy.types.GeometryNodeImageInfo.rst
   bpy.types.GeometryNodeImageTexture.rst
   bpy.types.GeometryNodeImportCSV.rst
   bpy.types.GeometryNodeImportOBJ.rst
   bpy.types.GeometryNodeImportPLY.rst
   bpy.types.GeometryNodeImportSTL.rst
   bpy.types.GeometryNodeImportText.rst
   bpy.types.GeometryNodeImportVDB.rst
   bpy.types.GeometryNodeIndexOfNearest.rst
   bpy.types.GeometryNodeIndexSwitch.rst
   bpy.types.GeometryNodeInputActiveCamera.rst
   bpy.types.GeometryNodeInputCollection.rst
   bpy.types.GeometryNodeInputCurveHandlePositions.rst
   bpy.types.GeometryNodeInputCurveTilt.rst
   bpy.types.GeometryNodeInputEdgeSmooth.rst
   bpy.types.GeometryNodeInputFont.rst
   bpy.types.GeometryNodeInputID.rst
   bpy.types.GeometryNodeInputImage.rst
   bpy.types.GeometryNodeInputIndex.rst
   bpy.types.GeometryNodeInputInstanceBounds.rst
   bpy.types.GeometryNodeInputInstanceReference.rst
   bpy.types.GeometryNodeInputInstanceRotation.rst
   bpy.types.GeometryNodeInputInstanceScale.rst
   bpy.types.GeometryNodeInputMaterial.rst
   bpy.types.GeometryNodeInputMaterialIndex.rst
   bpy.types.GeometryNodeInputMeshEdgeAngle.rst
   bpy.types.GeometryNodeInputMeshEdgeNeighbors.rst
   bpy.types.GeometryNodeInputMeshEdgeVertices.rst
   bpy.types.GeometryNodeInputMeshFaceArea.rst
   bpy.types.GeometryNodeInputMeshFaceIsPlanar.rst
   bpy.types.GeometryNodeInputMeshFaceNeighbors.rst
   bpy.types.GeometryNodeInputMeshIsland.rst
   bpy.types.GeometryNodeInputMeshVertexNeighbors.rst
   bpy.types.GeometryNodeInputNamedAttribute.rst
   bpy.types.GeometryNodeInputNamedLayerSelection.rst
   bpy.types.GeometryNodeInputNormal.rst
   bpy.types.GeometryNodeInputObject.rst
   bpy.types.GeometryNodeInputPosition.rst
   bpy.types.GeometryNodeInputRadius.rst
   bpy.types.GeometryNodeInputSceneTime.rst
   bpy.types.GeometryNodeInputShadeSmooth.rst
   bpy.types.GeometryNodeInputShortestEdgePaths.rst
   bpy.types.GeometryNodeInputSplineCyclic.rst
   bpy.types.GeometryNodeInputSplineResolution.rst
   bpy.types.GeometryNodeInputTangent.rst
   bpy.types.GeometryNodeInputVoxelIndex.rst
   bpy.types.GeometryNodeInstanceOnPoints.rst
   bpy.types.GeometryNodeInstanceTransform.rst
   bpy.types.GeometryNodeInstancesToPoints.rst
   bpy.types.GeometryNodeInterpolateCurves.rst
   bpy.types.GeometryNodeIsViewport.rst
   bpy.types.GeometryNodeJoinGeometry.rst
   bpy.types.GeometryNodeListGetItem.rst
   bpy.types.GeometryNodeListLength.rst
   bpy.types.GeometryNodeMaterialSelection.rst
   bpy.types.GeometryNodeMenuSwitch.rst
   bpy.types.GeometryNodeMergeByDistance.rst
   bpy.types.GeometryNodeMergeLayers.rst
   bpy.types.GeometryNodeMergePoints.rst
   bpy.types.GeometryNodeMeshBevel.rst
   bpy.types.GeometryNodeMeshBoolean.rst
   bpy.types.GeometryNodeMeshCircle.rst
   bpy.types.GeometryNodeMeshCone.rst
   bpy.types.GeometryNodeMeshCube.rst
   bpy.types.GeometryNodeMeshCylinder.rst
   bpy.types.GeometryNodeMeshFaceSetBoundaries.rst
   bpy.types.GeometryNodeMeshGrid.rst
   bpy.types.GeometryNodeMeshIcoSphere.rst
   bpy.types.GeometryNodeMeshLine.rst
   bpy.types.GeometryNodeMeshToCurve.rst
   bpy.types.GeometryNodeMeshToDensityGrid.rst
   bpy.types.GeometryNodeMeshToPoints.rst
   bpy.types.GeometryNodeMeshToSDFGrid.rst
   bpy.types.GeometryNodeMeshToVolume.rst
   bpy.types.GeometryNodeMeshUVSphere.rst
   bpy.types.GeometryNodeObjectInfo.rst
   bpy.types.GeometryNodeOffsetCornerInFace.rst
   bpy.types.GeometryNodeOffsetPointInCurve.rst
   bpy.types.GeometryNodePoints.rst
   bpy.types.GeometryNodePointsOfCurve.rst
   bpy.types.GeometryNodePointsToCurves.rst
   bpy.types.GeometryNodePointsToSDFGrid.rst
   bpy.types.GeometryNodePointsToVertices.rst
   bpy.types.GeometryNodePointsToVolume.rst
   bpy.types.GeometryNodeProximity.rst
   bpy.types.GeometryNodeRaycast.rst
   bpy.types.GeometryNodeRealizeInstances.rst
   bpy.types.GeometryNodeRemoveAttribute.rst
   bpy.types.GeometryNodeRenameAttribute.rst
   bpy.types.GeometryNodeRepeatInput.rst
   bpy.types.GeometryNodeRepeatOutput.rst
   bpy.types.GeometryNodeReplaceMaterial.rst
   bpy.types.GeometryNodeResampleCurve.rst
   bpy.types.GeometryNodeReverseCurve.rst
   bpy.types.GeometryNodeRotateInstances.rst
   bpy.types.GeometryNodeSDFGridBoolean.rst
   bpy.types.GeometryNodeSDFGridFillet.rst
   bpy.types.GeometryNodeSDFGridLaplacian.rst
   bpy.types.GeometryNodeSDFGridMean.rst
   bpy.types.GeometryNodeSDFGridMeanCurvature.rst
   bpy.types.GeometryNodeSDFGridMedian.rst
   bpy.types.GeometryNodeSDFGridOffset.rst
   bpy.types.GeometryNodeSampleCurve.rst
   bpy.types.GeometryNodeSampleGrid.rst
   bpy.types.GeometryNodeSampleGridIndex.rst
   bpy.types.GeometryNodeSampleIndex.rst
   bpy.types.GeometryNodeSampleNearest.rst
   bpy.types.GeometryNodeSampleNearestSurface.rst
   bpy.types.GeometryNodeSampleSoundFrequencies.rst
   bpy.types.GeometryNodeSampleUVSurface.rst
   bpy.types.GeometryNodeScaleElements.rst
   bpy.types.GeometryNodeScaleInstances.rst
   bpy.types.GeometryNodeSelfObject.rst
   bpy.types.GeometryNodeSeparateComponents.rst
   bpy.types.GeometryNodeSeparateGeometry.rst
   bpy.types.GeometryNodeSetCurveHandlePositions.rst
   bpy.types.GeometryNodeSetCurveNormal.rst
   bpy.types.GeometryNodeSetCurveRadius.rst
   bpy.types.GeometryNodeSetCurveTilt.rst
   bpy.types.GeometryNodeSetGeometryBundle.rst
   bpy.types.GeometryNodeSetGeometryName.rst
   bpy.types.GeometryNodeSetGreasePencilColor.rst
   bpy.types.GeometryNodeSetGreasePencilDepth.rst
   bpy.types.GeometryNodeSetGreasePencilSoftness.rst
   bpy.types.GeometryNodeSetGridBackground.rst
   bpy.types.GeometryNodeSetGridTransform.rst
   bpy.types.GeometryNodeSetID.rst
   bpy.types.GeometryNodeSetInstanceTransform.rst
   bpy.types.GeometryNodeSetMaterial.rst
   bpy.types.GeometryNodeSetMaterialIndex.rst
   bpy.types.GeometryNodeSetMeshNormal.rst
   bpy.types.GeometryNodeSetNURBSOrder.rst
   bpy.types.GeometryNodeSetNURBSWeight.rst
   bpy.types.GeometryNodeSetPointRadius.rst
   bpy.types.GeometryNodeSetPosition.rst
   bpy.types.GeometryNodeSetShadeSmooth.rst
   bpy.types.GeometryNodeSetSplineCyclic.rst
   bpy.types.GeometryNodeSetSplineResolution.rst
   bpy.types.GeometryNodeSimulationInput.rst
   bpy.types.GeometryNodeSimulationOutput.rst
   bpy.types.GeometryNodeSortElements.rst
   bpy.types.GeometryNodeSortList.rst
   bpy.types.GeometryNodeSplineLength.rst
   bpy.types.GeometryNodeSplineParameter.rst
   bpy.types.GeometryNodeSplitEdges.rst
   bpy.types.GeometryNodeSplitToInstances.rst
   bpy.types.GeometryNodeStoreNamedAttribute.rst
   bpy.types.GeometryNodeStoreNamedGrid.rst
   bpy.types.GeometryNodeStringJoin.rst
   bpy.types.GeometryNodeStringToCurves.rst
   bpy.types.GeometryNodeSubdivideCurve.rst
   bpy.types.GeometryNodeSubdivideMesh.rst
   bpy.types.GeometryNodeSubdivisionSurface.rst
   bpy.types.GeometryNodeSwitch.rst
   bpy.types.GeometryNodeTagFilter.rst
   bpy.types.GeometryNodeTool3DCursor.rst
   bpy.types.GeometryNodeToolActiveElement.rst
   bpy.types.GeometryNodeToolFaceSet.rst
   bpy.types.GeometryNodeToolMousePosition.rst
   bpy.types.GeometryNodeToolSelection.rst
   bpy.types.GeometryNodeToolSetFaceSet.rst
   bpy.types.GeometryNodeToolSetSelection.rst
   bpy.types.GeometryNodeTransferAttributes.rst
   bpy.types.GeometryNodeTransform.rst
   bpy.types.GeometryNodeTranslateInstances.rst
   bpy.types.GeometryNodeTriangulate.rst
   bpy.types.GeometryNodeTrimCurve.rst
   bpy.types.GeometryNodeUVPackIslands.rst
   bpy.types.GeometryNodeUVTangent.rst
   bpy.types.GeometryNodeUVUnwrap.rst
   bpy.types.GeometryNodeVertexOfCorner.rst
   bpy.types.GeometryNodeViewer.rst
   bpy.types.GeometryNodeViewportTransform.rst
   bpy.types.GeometryNodeVolumeCube.rst
   bpy.types.GeometryNodeVolumeToMesh.rst
   bpy.types.GeometryNodeWarning.rst
   bpy.types.GeometryNodeXPBDSolver.rst

.. class:: GeometryNode(NodeInternal)


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

