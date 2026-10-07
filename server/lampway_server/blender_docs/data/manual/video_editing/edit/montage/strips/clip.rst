.. _bpy.types.MovieClipStrip:

**********
Clip Strip
**********

A Clip Strip references a :ref:`Movie Clip <bpy.types.MovieClip>` data-block
and allows it to be used within the Movie Clip Editor timeline.

The clip can be modified within the :doc:`/editors/clip/index`,
including tracking, stabilization, and lens distortion correction.


Options
=======

.. reference::

   :Panel:     :menuselection:`Sidebar region --> Strip --> Movie Clip`

.. _bpy.types.MovieClipStrip.clip:

Movie Clip
   Used to select the Movie Clip data-block.
   For data-block controls, see :ref:`ui-data-block`.

.. _bpy.types.MovieClipStrip.stabilize2d:

Use: 2D Stabilized Clip
   Displays the clip with 2D stabilization applied.
   Stabilization settings are configured in the tracking tools.

.. _bpy.types.MovieClipStrip.undistort:

Use: Undistorted Clip
   Displays the clip with lens distortion removed,
   based on the solved camera data.

Frame Range
   Displays the original start and end frames of the Movie Clip,
   before any strip-level adjustments are applied.
