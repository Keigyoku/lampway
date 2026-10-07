
***********
In-Betweens
***********

.. figure:: /images/animation_armatures_posing_editing_in-betweens_tools.png
   :align: right

   In-Betweens Tools.

These tools create a new pose which is based on the keys surrounding the current frame.
This can help to quickly build up in-betweens from already existing key poses.


.. _bpy.ops.pose.blend_with_rest:

Blend Pose with Rest Pose
=========================

.. reference::

   :Mode:      Pose Mode and Object Mode
   :Menu:      :menuselection:`Pose --> Animation --> In-Betweens --> Blend Pose with Rest Pose`
   :Menu:      :menuselection:`Object --> Animation --> In-Betweens --> Blend Pose with Rest Pose`

*Blend with Rest Pose* linearly interpolates the current pose to the rest position.
When blending with a negative factor, the pose is moved away from the rest position.
Only one keyframe is needed for this tool unlike two for the other.


.. _bpy.ops.pose.push:

Push Pose from Breakdown
========================

.. reference::

   :Mode:      Pose Mode and Object Mode
   :Tool:      :menuselection:`Toolbar --> In-Betweens Tools --> Push`
   :Menu:      :menuselection:`Pose --> Animation --> In-Betweens --> Push Pose from Breakdown`
   :Menu:      :menuselection:`Object --> Animation --> In-Betweens --> Push Pose from Breakdown`
   :Shortcut:  :kbd:`Ctrl-E`

*Push Pose* interpolates the current pose away from the *linear interpolation between the surrounding keys*.
On your current frame, imagine a pose that is linearly interpolated from the surrounding keys.
That is the base pose that this tool interpolates away from.


.. _bpy.ops.pose.relax:

Relax Pose to Breakdown
=======================

.. reference::

   :Mode:      Pose Mode and Object Mode
   :Tool:      :menuselection:`Toolbar --> In-Betweens Tools --> Relax`
   :Menu:      :menuselection:`Pose --> Animation --> In-Betweens --> Relax Pose to Breakdown`
   :Menu:      :menuselection:`Object --> Animation --> In-Betweens --> Relax Pose to Breakdown`
   :Shortcut:  :kbd:`Alt-E`

*Relax Pose* is the opposite of *Push Pose from Breakdown*.
Hence at full influence, the resulting pose will be identical to a linear interpolation
between the surrounding keys.


.. _bpy.ops.pose.breakdown:

Pose Breakdowner
================

.. reference::

   :Mode:      Pose Mode and Object Mode
   :Tool:      :menuselection:`Toolbar region --> In-Betweens Tools --> Breakdowner`
   :Menu:      :menuselection:`Pose --> Animation --> In-Betweens --> Pose Breakdowner`
   :Menu:      :menuselection:`Object --> Animation --> In-Betweens --> Pose Breakdowner`
   :Shortcut:  :kbd:`Shift-E`

Creates a suitable breakdown pose on the current frame.

The Breakdowner tool can be constrained to work on specific transforms and axes,
by pressing the following keys while the tool is active:

- :kbd:`G`, :kbd:`R`, :kbd:`S`: move, rotate, scale
- :kbd:`B`: Bendy bones
- :kbd:`C`: custom properties
- :kbd:`X`, :kbd:`Y`, :kbd:`Z`: to the corresponding axes


.. _bpy.ops.pose.blend_to_neighbor:

Blend to Neighbor
=================

.. reference::

   :Mode:      Pose Mode and Object Mode
   :Menu:      :menuselection:`Pose --> Animation --> In-Betweens --> Blend to Neighbor`
   :Menu:      :menuselection:`Object --> Animation --> In-Betweens --> Blend to Neighbor`
   :Shortcut:  :kbd:`Shift-Alt-E`

Transitions the current pose with the neighboring keyframes in the timeline.
In order for this operator to work, there must be a keyframe before and after the current frame.
