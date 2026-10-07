
###############
  Transitions
###############

Transitions are a type of :ref:`Effect Strip <sequencer-effects-index>` used to blend two strips
over time. They create a smooth visual or audio change between adjacent strips,
commonly used to move from one shot to another without a hard cut.

Transitions are typically placed where two strips overlap in the timeline,
using that overlap to define the duration of the transition.


Types of Transitions
====================

Transitions combine two input strips and interpolate between them over time.

Below is a list of available transition effect strip types:

.. toctree::
   :maxdepth: 1
   :class: toc-list

   sound_crossfade.rst
   cross.rst
   gamma_cross.rst
   wipe.rst


Adding Transitions
==================

Transitions are added by selecting two strips and using:
:menuselection:`Add --> Transition`.

Blender creates the transition using the overlap between the strips.
If the strips do not overlap, the last frame of each strip is used for the transition.

The length of the overlap determines the duration of the transition.


Adjustment and Controls
=======================

Each transition provides its own set of properties in
:doc:`/video_editing/edit/montage/strips/strip_properties`.
These control how the blend occurs, such as transition type,
direction, and timing.

Adjusting the overlap or trimming the transition strip changes the timing of the effect.


Workflow Notes
==============

- Transitions require two input strips.
- The transition duration is defined by the overlapping region.
- Transitions are non-destructive and can be adjusted at any time.
- Multiple transitions and effects can be combined for more complex results.
- Strip order and channel placement can affect how transitions are evaluated.

Transitions provide a simple and effective way to create smooth edits
and improve visual continuity within a sequence.
