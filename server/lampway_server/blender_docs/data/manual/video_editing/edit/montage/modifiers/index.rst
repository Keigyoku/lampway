.. index:: Modifiers; Video Sequencer Modifiers
.. index:: Video Sequencer Modifiers
.. _bpy.types.StripModifier:

***************
Strip Modifiers
***************

.. reference::

   :Panel:     :menuselection:`Properties Editor --> Strip Modifiers`

.. figure:: /images/video-editing_sequencer_strip_modifiers_panel.webp
   :align: right
   :scale: 75%

Modifiers are used to make adjustments to the image, like contrast,
brightness, saturation, color balance and applying masks.

You can add these modifiers directly to a media strip,
or you can use them within an :doc:`Adjustment Layer </video_editing/edit/montage/strips/adjustment>`
strip, making them apply to several media strips in one go.


Modifier Assets
===============

Compositor node groups marked as :doc:`Assets </editors/asset_browser>`
can be used as strip modifiers.

Asset modifiers appear in the :menuselection:`Add` menu alongside Blender's
built-in modifiers. Assets assigned to :doc:`Catalogs
</files/asset_libraries/catalogs>` are organized into matching submenus.

This makes it possible to build reusable modifier libraries and share custom
effects across multiple projects.

.. tip::

   To make a compositor node group available as a strip modifier,
   mark it as an asset by right-clicking its data-block selector and choosing
   :menuselection:`Mark as Asset`.

   After saving the file, the asset will appear in the modifier
   :menuselection:`Add` menu. Existing assets created in older Blender versions
   may need to be re-saved before they become available.


Common Options
==============

Each modifier provides several controls in its header:

:bl-icon:`restrict_view_on` / :bl-icon:`restrict_view_off` Viewport
   Toggles the modifier effect in the Preview region.
:bl-icon:`restrict_render_on` / :bl-icon:`restrict_render_off` Render
   Enables or disables the modifier during rendering and final output.
   This can be useful for comparing the strip with and without the modifier applied.

.. _bpy.ops.sequencer.strip_modifier_duplicate:

Extras
   Duplicate :kbd:`Shift-D`
      Creates a duplicate of the modifier just below current one in the stack.

   .. _bpy.ops.sequencer.strip_modifier_copy:

   Copy to Selected
      Copies the modifier from the :term:`Active` strip to all selected strips.

   .. _bpy.ops.sequencer.strip_modifier_move_to_index:

   Move to First/Last
      Moves the modifier to the first or last position in the modifier stack.

   .. _bpy.types.SequencerCompositorModifierData.show_group_selector:

   Show Node Group
      For :ref:`Compositor Modifiers <bpy.types.SequencerCompositorModifierData>`,
      shows or hides the node group selector.

:bl-icon:`x` Remove Strip Modifier
   Removes the modifier from the modifier stack.
:bl-icon:`grip` Move Strip Modifier
   Drag to reorder modifiers in the stack.

   Modifiers are evaluated from top to bottom, so changing their order affects the final result.


Types
=====

Strip modifiers include built-in image and sound modifiers as well as custom
compositor modifier assets.


Image Modifiers
---------------

.. toctree::
   :maxdepth: 1
   :class: toc-list

   brightness_contrast.rst
   color_balance.rst
   compositor.rst
   curves.rst
   hue_correct.rst
   mask.rst
   tone_map.rst
   white_balance.rst

-----

.. toctree::
   :maxdepth: 2
   :class: toc-list

   camera_lens_effects/index.rst
   creative/index.rst


Sound Modifiers
---------------

.. toctree::
   :maxdepth: 1
   :class: toc-list

   echo.rst
   pitch.rst
   sound_equalizer.rst
