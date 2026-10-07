.. _bpy.ops.pose.armature_apply:

*****
Apply
*****

.. reference::

   :Mode:      Pose Mode
   :Menu:      :menuselection:`Pose --> Apply`
   :Shortcut:  :kbd:`Ctrl-A`

The Apply menu contains operators for converting the current pose,
constraint results, or custom property values into a new default state.

.. note::

   Applying a pose from a pose Library can still work correctly
   even when the bone's rotation mode has changed since the pose was created.

   Blender determines the stored rotation representation from the pose data's
   RNA paths and converts the rotation internally before applying it to the
   current bone rotation mode.

   However, poses stored using Euler rotations may lose the original rotation
   order information. In these cases Blender falls back to ``XYZ`` order,
   which can result in slightly different rotations when applying the pose.


Pose as Rest Pose
=================

Defines the current pose as the new armature rest pose by applying the current
bone transforms to the armature in *Edit Mode*.

After applying the pose, the armature's undeformed state changes to match the
current pose. Meshes and other geometry deformed by the armature are also reset
to their undeformed state relative to the new rest pose.

This operation permanently changes the armature structure and can require
re-binding or adjusting existing skinning, constraints, drivers, animations,
and exported assets.


Pose Selected as Rest Pose
==========================

Similar to *Pose as Rest Pose*, but only applies the selected bones.

Unselected bones retain their original rest pose transforms.


.. _bpy.ops.pose.visual_transform_apply:

Visual Transform to Pose
========================

Applies the evaluated visual transforms of bones after constraints are evaluated.

This converts the final constrained position, rotation, and scale into regular
pose transforms, allowing constraints to be removed while preserving the
current visual result.

This is useful for baking constrained poses, preparing rigs for export,
or simplifying complex constraint setups.


.. _bpy.ops.object.assign_property_defaults:

Assign Custom Property Values as Default
========================================

Stores the current values of custom properties as their default values.

These defaults are used as part of the armature's rest state for
:doc:`NLA </editors/nla/index>` track blending and animation evaluation.

This is useful when rigs rely on custom properties to control rig behavior,
IK/FK switching, corrective shapes, or driver-based systems.
