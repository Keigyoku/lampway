.. index:: Data-Block; Movie Clip
.. _bpy.types.MovieClip:

**********************
Movie Clip Data-Blocks
**********************

Movie Clip data-blocks store video files and image sequences used for motion tracking,
masking, and compositing.

They are primarily used in the :doc:`Movie Clip Editor </editors/clip/index>`,
but can also be referenced by nodes and other systems that support video input.


Creating a Movie Clip
=====================

Movie Clips can be created by:

- Opening a video file or image sequence in the :doc:`Movie Clip Editor </editors/clip/index>`.
- Adding a clip in the :doc:`Compositor </compositing/index>` using a
  :doc:`Movie Clip node </compositing/types/input/movie_clip>`.
- Using the data-block selector in editors that support Movie Clip references.

When a file is loaded, a Movie Clip data-block is created and stored in the current
Blend file.


Properties
==========

The Movie Clip data-block provides the following main properties:

File Path
   The path to the video file or image sequence on disk.

Start Frame
   Defines the scene frame that corresponds to the first frame of the clip.
   This allows aligning footage with the timeline.

Frame Offset
   Offsets the clip's internal frame numbering without changing its placement
   in the scene timeline. This is useful when syncing footage that does not
   start at frame 1.

Color Space
   Specifies the :term:`Color Space` that the image file was saved in.
   This information is used to correctly convert the image to Blender's
   internal linear color space, which is used for all color computations and rendering.

   Textures and final renders are often stored in sRGB,
   while OpenEXR images are stored in a linear color space.
   Some images such as normal, bump or stencil maps do not strictly contain "colors"
   and should never have a color conversion applied to them.
   For such images, the color space should be set to *Non-Color*.

   The list of color spaces depends on the active :ref:`OCIO config <ocio-config>`.
   The default supported color spaces are described in detail here:
   :ref:`Default OpenColorIO Configuration <ocio-config-default-color-spaces>`.


Usage
=====

Movie Clips are most commonly used for:

- :doc:`Motion Tracking </movie_clip/tracking/index>` to reconstruct camera movement
  or track objects.
- :doc:`Masking </movie_clip/masking/index>` for rotoscoping and compositing.
- Input in the :doc:`Compositor </compositing/index>` via Movie Clip nodes.

Multiple Movie Clip data-blocks can exist in a single Blend file,
allowing different footage sources to be used in the same project.


Data-Block Management
=====================

Movie Clips are regular Blender data-blocks and can be managed in the
:doc:`Outliner </editors/outliner/index>`.

They support:

- Renaming.
- Fake User (to prevent automatic removal when unused).
- Unlinking from editors or nodes.

.. note::

   Removing a Movie Clip data-block from the Blend file does not delete
   the original media file from disk.
