.. _sequencer-effects-index:

#################
  Effect Strips
#################

Effect Strips are special strips in the :doc:`/editors/video_sequencer/index` that generate
or modify the visual output based on other strips in the timeline. Unlike regular media strips,
they do not represent source footage. Instead, they apply operations such as transitions,
filters, compositing, or procedural generation.

Effect Strips are commonly used to blend clips together, adjust color, add stylized effects,
or create entirely new visual elements directly within the Video Sequence Editor (VSE).


Types of Effects
================

Effect Strips operate in different ways depending on their type:

- **Single-Input Effects** --
  Modify a single strip, such as applying color correction or adding a glow.
- **Dual-Input Effects** --
  Combine two strips together, commonly used for transitions such as crossfades or wipes.
- **Generator Effects** --
  Create new content without requiring an input strip, such as color backgrounds or text.

Below is a list of available effect strip types:

.. toctree::
   :maxdepth: 1
   :class: toc-list

   multicam.rst

-----


.. toctree::
   :maxdepth: 1
   :class: toc-list

   speed_control.rst
   glow.rst
   blur.rst

-----

.. toctree::
   :maxdepth: 1
   :class: toc-list

   add.rst
   subtract.rst
   multiply.rst
   alpha_over_under.rst
   color_mix.rst


.. _bpy.ops.sequencer.effect_strip_add:

Adding Effect Strips
====================

Effect Strips can be added in the Timeline by selecting one or more strips and using
:menuselection:`Add --> Effect Strip`.

The available effect types depend on the number of selected strips:

- No selection: Generator effects are available.
- One strip selected: Single-input effects are available.
- Two strips selected: Dual-input effects are available.

The resulting Effect Strip appears in the timeline and can be moved, trimmed,
and adjusted like any other strip.


Adjustment and Controls
=======================

Each Effect Strip provides its own set of properties in
:doc:`/video_editing/edit/montage/strips/strip_properties`.
These properties control how the effect is applied, such as blending modes,
influence, or effect-specific parameters.

Effect Strips are evaluated based on their position in the timeline.
Their placement, overlap, and channel order can significantly influence the final result.


Workflow Notes
==============

- Effect Strips are non-destructive and can be adjusted at any time.
- Multiple effects can be stacked to create more complex results.
- Higher channel strips typically override lower ones.
- Some effects require precise strip alignment to work correctly (for example, transitions).

Effect Strips provide a flexible way to perform editing and compositing tasks directly in the VSE,
reducing the need to switch to other editors for many common workflows.
