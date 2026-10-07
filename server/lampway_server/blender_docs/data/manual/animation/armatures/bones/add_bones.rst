************
Adding Bones
************

Bones can be added to an armature in Edit Mode.


.. _bpy.ops.armature.bone_primitive_add:

Single Bone
===========

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Add --> Single Bone`
   :Shortcut:  :kbd:`Shift-A`

In the 3D Viewport, :kbd:`Shift-A` to add a new bone to your armature.

By default this bone will be:

- One unit in length.
- Oriented towards the global Z axis.
- With its root placed at the 3D cursor position.
- Have no parent/child relationship with any other bone.
- Have its :ref:`bpy.types.Bone.use_deform` option enabled

It is also possible to edit the parameters of the bone in the :ref:`redo panel <bpy.ops.screen.redo_last>` when creating it.

.. figure:: /images/animation_armatures_add_bone_redo_panel.png

   Add Bone redo panel.

Options
=======

Name
   Name of the newly created bone.

Space
   Coordinate system used when creating the new bone.

   :Object:
      Creates the bone using the armature object's local space.

   :World:
      Creates the bone using world space coordinates.

Align
   Orientation used for the newly created bone.

   :Up: Aligns the bone so its main axis points upward along the positive Z axis of the selected space.
   :Axes: Aligns the bone axes to match the selected coordinate system.
   :3D Cursor: Aligns the bone to the orientation of the 3D Cursor.
   :Viewport: Aligns the bone to the current viewport orientation.

Length
   Length of the newly created bone.

   This also scales the initial B-Bone and envelope display size proportionally to the bone length.

   See :ref:`bpy.types.EditBone.length`.

Deform
   Enables the bone to deform geometry.

   Disable this when creating control bones that should not affect mesh deformation.

   See :ref:`bpy.types.EditBone.use_deform`.
