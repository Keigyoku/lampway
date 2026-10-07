Modifier(bpy_struct)
====================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`

.. toctree::
   :caption: Subclasses
   :maxdepth: 1

   bpy.types.ArmatureModifier.rst
   bpy.types.ArrayModifier.rst
   bpy.types.BevelModifier.rst
   bpy.types.BooleanModifier.rst
   bpy.types.BuildModifier.rst
   bpy.types.CastModifier.rst
   bpy.types.ClothModifier.rst
   bpy.types.CollisionModifier.rst
   bpy.types.CorrectiveSmoothModifier.rst
   bpy.types.CurveModifier.rst
   bpy.types.DataTransferModifier.rst
   bpy.types.DecimateModifier.rst
   bpy.types.DisplaceModifier.rst
   bpy.types.DynamicPaintModifier.rst
   bpy.types.EdgeSplitModifier.rst
   bpy.types.ExplodeModifier.rst
   bpy.types.FluidModifier.rst
   bpy.types.GreasePencilArmatureModifier.rst
   bpy.types.GreasePencilArrayModifier.rst
   bpy.types.GreasePencilBuildModifier.rst
   bpy.types.GreasePencilColorModifier.rst
   bpy.types.GreasePencilDashModifierData.rst
   bpy.types.GreasePencilEnvelopeModifier.rst
   bpy.types.GreasePencilHookModifier.rst
   bpy.types.GreasePencilLatticeModifier.rst
   bpy.types.GreasePencilLengthModifier.rst
   bpy.types.GreasePencilLineartModifier.rst
   bpy.types.GreasePencilMirrorModifier.rst
   bpy.types.GreasePencilMultiplyModifier.rst
   bpy.types.GreasePencilNoiseModifier.rst
   bpy.types.GreasePencilOffsetModifier.rst
   bpy.types.GreasePencilOpacityModifier.rst
   bpy.types.GreasePencilOutlineModifier.rst
   bpy.types.GreasePencilShrinkwrapModifier.rst
   bpy.types.GreasePencilSimplifyModifier.rst
   bpy.types.GreasePencilSmoothModifier.rst
   bpy.types.GreasePencilSubdivModifier.rst
   bpy.types.GreasePencilTextureModifier.rst
   bpy.types.GreasePencilThickModifierData.rst
   bpy.types.GreasePencilTimeModifier.rst
   bpy.types.GreasePencilTintModifier.rst
   bpy.types.GreasePencilWeightAngleModifier.rst
   bpy.types.GreasePencilWeightProximityModifier.rst
   bpy.types.HookModifier.rst
   bpy.types.LaplacianDeformModifier.rst
   bpy.types.LaplacianSmoothModifier.rst
   bpy.types.LatticeModifier.rst
   bpy.types.MaskModifier.rst
   bpy.types.MeshCacheModifier.rst
   bpy.types.MeshDeformModifier.rst
   bpy.types.MeshSequenceCacheModifier.rst
   bpy.types.MeshToVolumeModifier.rst
   bpy.types.MirrorModifier.rst
   bpy.types.MultiresModifier.rst
   bpy.types.NodesModifier.rst
   bpy.types.NormalEditModifier.rst
   bpy.types.OceanModifier.rst
   bpy.types.ParticleInstanceModifier.rst
   bpy.types.ParticleSystemModifier.rst
   bpy.types.RemeshModifier.rst
   bpy.types.ScrewModifier.rst
   bpy.types.ShrinkwrapModifier.rst
   bpy.types.SimpleDeformModifier.rst
   bpy.types.SkinModifier.rst
   bpy.types.SmoothModifier.rst
   bpy.types.SoftBodyModifier.rst
   bpy.types.SolidifyModifier.rst
   bpy.types.SubsurfModifier.rst
   bpy.types.SurfaceDeformModifier.rst
   bpy.types.SurfaceModifier.rst
   bpy.types.TriangulateModifier.rst
   bpy.types.UVProjectModifier.rst
   bpy.types.UVWarpModifier.rst
   bpy.types.VertexWeightEditModifier.rst
   bpy.types.VertexWeightMixModifier.rst
   bpy.types.VertexWeightProximityModifier.rst
   bpy.types.VolumeDisplaceModifier.rst
   bpy.types.VolumeToMeshModifier.rst
   bpy.types.WarpModifier.rst
   bpy.types.WaveModifier.rst
   bpy.types.WeightedNormalModifier.rst
   bpy.types.WeldModifier.rst
   bpy.types.WireframeModifier.rst

.. class:: Modifier(bpy_struct)

   Modifier affecting the geometry data of an object

   .. data:: execution_time

      Time in seconds that the modifier took to evaluate. This is only set on evaluated objects. If multiple modifiers run in parallel, execution time is not a reliable metric. (in [-inf, inf], default 0.0, readonly)

      :type: float

   .. attribute:: is_active

      The active modifier in the list (default False)

      :type: bool

   .. data:: is_override_data

      In a local override object, whether this modifier comes from the linked reference object, or is local to the override (default True, readonly)

      :type: bool

   .. attribute:: name

      Modifier name (default "", never None)

      :type: str

   .. data:: persistent_uid

      Uniquely identifies the modifier within the modifier stack that it is part of (in [-inf, inf], default 0, readonly)

      :type: int

   .. attribute:: show_expanded

      Set modifier expanded in the user interface (default False)

      :type: bool

   .. attribute:: show_in_editmode

      Display modifier in Edit mode (default False)

      :type: bool

   .. attribute:: show_on_cage

      Adjust edit cage to modifier result (default False)

      :type: bool

   .. attribute:: show_render

      Use modifier during render (default False)

      :type: bool

   .. attribute:: show_viewport

      Display modifier in viewport (default False)

      :type: bool

   .. data:: type

      (default ``'GREASE_PENCIL_VERTEX_WEIGHT_PROXIMITY'``, readonly)

      :type: Literal[:ref:`rna_enum_object_modifier_type_items`]

   .. attribute:: use_apply_on_spline

      Apply this and all preceding deformation modifiers on splines' points rather than on filled curve/surface (default False)

      :type: bool

   .. attribute:: use_pin_to_last

      Keep the modifier at the end of the list (default False)

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

   - :class:`Object.modifiers`
   - :class:`ObjectModifiers.active`
   - :class:`ObjectModifiers.new`
   - :class:`ObjectModifiers.remove`

