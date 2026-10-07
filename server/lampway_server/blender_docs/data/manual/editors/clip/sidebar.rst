
**************
Sidebar Region
**************

Footage
=======

.. _bpy.types.MovieClipProxy:

Proxy/Timecode
--------------

.. figure:: /images/editors_clip_sidebar_proxy-panel.png
   :align: right

High-resolution video files can impact Blender's performance, slowing down scrubbing and other operations.
To counter this, you can generate one or more proxies, which are copies of the original footage
stored at a lower resolution and/or quality. These proxies can then be used as a less resource-heavy
stand-in while working on the scene.

Build Original
   The proxy resolution(s) to generate based on the original, distorted footage.
Build Undistorted
   The proxy resolution(s) to generate based on the undistorted footage
   (that is, with the :ref:`Lens settings <motion_tracking-camera-lens>` applied
   to undo the distortion in the recording).
Quality
   Controls the level of lossy compression applied to the image, expressed as a percentage.
   Lossy compression reduces file size by discarding some image data, which may result in a loss of detail.

   - **0%**: Maximum compression, producing the smallest file size but the most noticeable quality loss.
   - **100%**: No compression, preserving full image quality at the cost of a larger file size.
Proxy Custom Directory
   By default, proxies are stored to a ``BL_proxy`` subfolder next to the original file.
   Use this option to specify a different location.
Build Proxy/Timecode
   Generates proxies based on the settings above, as well as timecode files.
   Instead of using this button, you can also click
   :menuselection:`Clip --> Proxy --> Rebuild Proxy and Timecode Indices`.
Proxy Render Size
   Which proxy size to use for display. Depending on the
   :ref:`Render Undistorted <bpy.types.MovieClipUser.use_render_undistorted>` setting,
   Blender will use either the Original proxy or the Undistorted proxy.


Footage Settings
----------------

See :doc:`/editors/image/image_settings`.


.. _clip-properties-animation:

Animation
---------

Controls animation data for movie clip properties, including active :doc:`Actions </animation/actions>`
and their assigned :ref:`Slot <animation-actions-slots>`.

See :ref:`animation-actions-slots-manual-assign` for more information.


Track
=====

See :doc:`/movie_clip/tracking/clip/sidebar/track/index`.


Stabilization
=============

See :doc:`/movie_clip/tracking/clip/sidebar/stabilization/index`.


View
====

.. _editors-clip-2d_cursor:

2D Cursor
---------

The 2D Cursor is the dashed crosshair in the main region. It can be used as a
transformation :doc:`pivot point </editors/3dview/controls/pivot_point/index>`
by selecting the corresponding option in the editor's header.

Note that the 2D Cursor is only available in Mask mode, not in Tracking mode.

.. _bpy.types.SpaceClipEditor.cursor_location:

Location X, Y
   The relative location of the 2D Cursor, going from (0, 0) for the bottom left
   corner to (1, 1) for the top right corner.

   You can also position the 2D Cursor by clicking :kbd:`Shift-RMB`
   in (or around) the video.

Annotations
-----------

See :doc:`/interface/annotate_tool`.
