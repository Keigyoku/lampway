
*********************************
Grease Pencil Material Properties
*********************************

Grease Pencil materials define how strokes and fills are rendered.
Each stroke references a single material, and that material contains
separate settings for its *Stroke* and *Fill* components.

The Material Properties panel provides tools to manage material slots,
control visibility and locking, and configure the appearance of stroke
and fill shading.


.. _gp-material-slots:

Material Slots
==============

.. figure:: /images/grease-pencil_materials_introduction_slots-panel.png
   :align: right

   Grease Pencil material slots panel.

Material slots assign materials to the Grease Pencil object.
Each stroke stores a reference to one of these material slots.

The active material is used for newly created strokes.
Existing strokes keep their assigned material unless changed manually.

Next to each material name are controls for common visibility and editing options:

.. _bpy.types.MaterialGPencilStyle.ghost:

:bl-icon:`onionskin_on` / :bl-icon:`onionskin_off` (Show/Hide in Ghosts)
   Controls whether the material is visible in
   :doc:`Onion Skinning </grease_pencil/properties/onion_skinning>` previews.

.. _bpy.types.MaterialGPencilStyle.hide:

:bl-icon:`hide_off` / :bl-icon:`hide_on` (Hide/Show Material)
   Toggles the visibility of strokes using this material in the viewport.

.. _bpy.types.MaterialGPencilStyle.lock:

:bl-icon:`unlocked` / :bl-icon:`locked` (Lock/Unlock Material)
   Prevents strokes using this material from being edited in Edit Mode.


Specials
--------

These operators provide bulk control over material visibility and locking:

.. _bpy.ops.grease_pencil.material_reveal:

Show All
   Enable visibility for all materials.

.. _bpy.ops.grease_pencil.material_hide:

Hide Others
   Hide all materials except the active one.

.. _bpy.ops.grease_pencil.material_lock_all:

Lock All
   Lock all materials to prevent editing.

.. _bpy.ops.grease_pencil.material_unlock_all:

Unlock All
   Unlock all materials for editing.

.. _bpy.ops.grease_pencil.material_lock_unselected:

Lock Unselected
   Lock materials not used by the currently selected strokes.

.. _bpy.ops.grease_pencil.material_lock_unused:

Lock Unused
   Lock and hide materials not assigned to any stroke.

.. _bpy.ops.grease_pencil.material_copy_to_object:

Copy Material to Selected
   Copy the active material to selected Grease Pencil objects.

Copy All Materials to Selected
   Copy all material slots to selected Grease Pencil objects.

Remove Unused Slots
   Remove material slots that are not assigned to any strokes.


Lock & Visibility Controls
--------------------------

.. _bpy.ops.grease_pencil.material_isolate:

:bl-icon:`locked` (Isolate Material)
   Lock all other materials so only the active material can be edited.

:bl-icon:`restrict_view_on` (Isolate Material)
   Hide all other materials so only the active material is visible.


.. _gp-material-surface:

Surface
=======

.. figure:: /images/grease-pencil_materials_properties_panel.png
   :align: right

   Shader panel with only Stroke component enabled.

The Surface panel defines the visual appearance of strokes and fills.
Each material contains two independent components:

- *Stroke* -- Controls the outline rendering.
- *Fill* -- Controls the interior rendering of closed strokes.

Each component can be enabled or disabled independently.


Stroke
------

The *Stroke* component defines how the line itself is drawn.

.. _bpy.types.MaterialGPencilStyle.mode:

Line Type
   Defines how the stroke geometry is rendered.

   :Line:
      Renders a continuous line connecting stroke points.
   :Dots:
      Draws a circular shape at each stroke point.
      Points are not connected.
   :Squares:
      Draws a square shape at each stroke point.
      Points are not connected.

.. _bpy.types.MaterialGPencilStyle.stroke_style:

Style
   Determines how the stroke is shaded.

   :Solid:
      Uses a uniform base color.
   :Texture:
      Uses an image texture mapped along the stroke.

      Image
         Image data-block used as the texture source.

      Blend
         Mix factor between the texture and the Base Color.

      UV Factor
         Controls texture scaling along the stroke length.

.. _bpy.types.MaterialGPencilStyle.placement_mode:

Placement :guilabel:`Dots` :guilabel:`Squares`
   Defines how dots or squares are distributed along strokes.

   :Count:
      Places a fixed number of dots on each stroke segment.

      This mode keeps the number of generated shapes consistent regardless
      of the stroke length or thickness.

      .. _bpy.types.MaterialGPencilStyle.placement_count:

      Count
         Number of dots to place on each stroke segment.

   :Radius:
      Places dots based on the stroke radius, adapting the spacing to the stroke thickness.

      Larger stroke radii produce wider spacing between dots, while smaller
      radii place them closer together.

      .. _bpy.types.MaterialGPencilStyle.placement_radius_spacing:

      Spacing
         Distance between dots as a percentage of their diameter.

         Lower values create overlapping or tightly packed dots,
         while higher values increase the gap between each generated shape.

   :Density:
      Places dots based on the stroke length.

      Longer strokes generate more dots while shorter strokes generate fewer,
      maintaining a more uniform visual density along the stroke.

      .. _bpy.types.MaterialGPencilStyle.placement_density:

      Density
         Number of dots generated along the stroke length.

         Higher values create more densely packed dots.


.. _bpy.types.MaterialGPencilStyle.color:

Base Color
   The primary color of the stroke.

.. _bpy.types.MaterialGPencilStyle.use_stroke_holdout:

Holdout
   Makes the stroke act as a mask,
   removing color from underlying strokes and fills.

.. _bpy.types.MaterialGPencilStyle.alignment_mode:

Alignment
   Controls orientation of *Dots* and *Squares*.

   :Path: Aligns to the drawing direction and object rotation.
   :Object: Aligns only to the object's rotation.
   :Fixed: Aligns to screen space.

.. _bpy.types.MaterialGPencilStyle.alignment_rotation:

Rotation
   Rotates the *Dots* or *Squares* shapes.
   Limited to -90° to 90°.

.. _bpy.types.MaterialGPencilStyle.use_overlap_strokes:

Self Overlap
   Controls how overlapping parts of the same stroke blend,
   particularly with semi-transparent materials.

.. list-table:: Stroke examples
   :widths: 1 1 1 1

   * - .. figure:: /images/grease-pencil_materials_properties_stroke-solid-line.png

          Line / Solid
     - .. figure:: /images/grease-pencil_materials_properties_stroke-texture-line.png

          Line / Texture
     - .. figure:: /images/grease-pencil_materials_properties_stroke-solid-dot.png

          Dot / Solid
     - .. figure:: /images/grease-pencil_materials_properties_stroke-texture-dot.png

          Dot / Texture


Randomize
^^^^^^^^^

Adds random variation to generated dots or squares to create a less uniform appearance.

.. _bpy.types.MaterialGPencilStyle.random_size_factor:

Size
   Randomly varies the size of generated shapes.

   Higher values increase the variation between larger and smaller dots.

.. _bpy.types.MaterialGPencilStyle.random_strength_factor:

Strength
   Randomly varies the opacity of generated shapes.

   This can create a more natural or textured appearance.

.. _bpy.types.MaterialGPencilStyle.random_rotation_factor:

Rotation
   Randomly rotates generated shapes around their center.

   This is most noticeable when using square shapes.

.. _bpy.types.MaterialGPencilStyle.random_hue_factor:

Hue
   Randomly varies the hue of generated shapes.

.. _bpy.types.MaterialGPencilStyle.random_saturation_factor:

Saturation
   Randomly varies the saturation of generated shapes.

.. _bpy.types.MaterialGPencilStyle.random_value_factor:

Value
   Randomly varies the brightness of generated shapes.

.. _bpy.types.MaterialGPencilStyle.random_noise_scale:

Noise Scale
   Controls the scale of the random noise pattern.

   Lower values create smoother variation across the stroke, while higher
   values produce more rapidly changing randomization.


Fill
----

The *Fill* component controls rendering of closed stroke regions.

.. _bpy.types.MaterialGPencilStyle.fill_style:

Style
   Defines how the fill is shaded.

   :Solid:
      Uses a single base color.
   :Gradient:
      Blends between two colors.

      .. _bpy.types.MaterialGPencilStyle.gradient_type:

      Gradient Type
         :Linear: Blends along one axis.
         :Radial: Blends outward from a center point.

   :Texture:
      Uses an image texture.

      .. _bpy.types.MaterialGPencilStyle.fill_image:

      Image
         Image data-block used for the fill texture.

.. list-table:: Fill examples
   :widths: 25 25 25 25

   * - .. figure:: /images/grease-pencil_materials_properties_fill-solid.png
          :width: 120px

          Solid
     - .. figure:: /images/grease-pencil_materials_properties_fill-gradient.png
          :width: 120px

          Gradient (Linear)
     - .. figure:: /images/grease-pencil_materials_properties_fill-gradient-radial.png
          :width: 120px

          Gradient (Radial)
     - .. figure:: /images/grease-pencil_materials_properties_fill-texture.png
          :width: 120px

          Texture

.. _bpy.types.MaterialGPencilStyle.fill_color:

Base Color
   Primary fill color.

.. _bpy.types.MaterialGPencilStyle.mix_color:

Secondary Color :guilabel:`Gradient`
   Secondary color used for gradients.

.. _bpy.types.MaterialGPencilStyle.use_fill_holdout:

Holdout
   Makes the fill act as a mask,
   removing color from strokes underneath.

.. _bpy.types.MaterialGPencilStyle.mix_factor:

Blend :guilabel:`Gradient / Texture`
   Controls mixing between Base Color and the gradient or texture.

.. _bpy.types.MaterialGPencilStyle.flip:

Flip Colors :guilabel:`Gradient`
   Swaps Base and Secondary colors.

.. _bpy.types.MaterialGPencilStyle.texture_offset:

Location X, Y :guilabel:`Gradient / Texture`
   Offsets gradient or texture coordinates.

.. _bpy.types.MaterialGPencilStyle.texture_angle:

Rotation :guilabel:`Gradient / Texture`
   Rotates the gradient or texture mapping.

.. _bpy.types.MaterialGPencilStyle.texture_scale:

Scale X, Y :guilabel:`Gradient / Texture`
   Scales the gradient or texture mapping.

.. _bpy.types.MaterialGPencilStyle.texture_clamp:

Clip Image :guilabel:`Texture`
   Prevents texture tiling when enabled.


.. _gp-material-settings:

Settings
========

.. _bpy.types.MaterialGPencilStyle.pass_index:

Pass Index
   Custom integer identifier for use in modifiers and compositing.
   Can be used to target specific materials in
   :doc:`Grease Pencil Modifiers </grease_pencil/modifiers/introduction>`.
