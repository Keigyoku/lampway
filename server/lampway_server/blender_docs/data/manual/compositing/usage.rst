
********************
Using The Compositor
********************

The Compositor provides a node-based workflow for processing and combining
images. Node groups can perform tasks such as color correction, filtering,
blending, keying, masking, stylization, and other image-processing operations.

In addition to the standard Compositor editor, compositor node groups can be
used directly in the Video Sequencer through compositor strips and compositor
modifiers. This allows node-based effects to be integrated into editing
workflows without leaving the Sequencer.


.. _compositor-node-gizmos:

Node Gizmos
===========

Some compositor nodes provide interactive gizmos for adjusting their
properties directly in the image.

Node gizmos are available in both:

- The :ref:`Compositor backdrop <bpy.types.SpaceNodeEditor.show_backdrop>`
  when :ref:`Active Node <bpy.types.SpaceNodeEditor.show_gizmo_active_node>`
  is enabled in the Compositor's gizmo popover.
- The built-in *Viewer Node* image in the
  :doc:`Image Editor </editors/image/index>` when
  :ref:`Active Node <bpy.types.SpaceImageEditor.show_gizmo_active_node>`
  is enabled.

To use node gizmos:

#. Connect the node to a :doc:`Viewer Node </compositing/types/output/viewer>`
   or make it the active viewer.
#. Display either the compositor backdrop or the built-in *Viewer Node* image.
#. Enable the *Active Node* gizmo if it is not already enabled.
#. Drag the displayed gizmos to adjust the node interactively.

Changes made with the gizmos are immediately reflected in the node's
properties and the compositor output.

.. note::

   When multiple Compositor editors are open, the Image Editor displays the
   gizmos from the node editor that was used most recently.


Video Sequence Strips & Modifiers
=================================

Compositor functionality can be used in the Sequencer in two ways:

- :ref:`Compositor Strips <bpy.types.CompositorStrip>` process one or more
  strips through a compositor node group and output the result as a strip.
- :ref:`Compositor Modifiers <bpy.types.SequencerCompositorModifierData>` apply compositor
  node groups as modifiers to existing strips.

Both workflows use compositor node groups and support many of the same
compositor nodes and operations available in the regular Compositor editor.


Compositor Strips
-----------------

Compositor strips create effects directly in the Sequencer timeline.

They can be used for transitions, stylized effects, color processing,
image manipulation, blurs, distortions, overlays, and custom workflows.

Depending on the strip type, compositor strips can process:

- A single strip.
- Two input strips for transitions and blend effects.
- No inputs for fully procedural effects.


Compositor Modifiers
--------------------

Compositor modifiers apply a compositor node group directly to an existing strip.

Unlike compositor strips, modifiers do not create a separate strip in the timeline.
Instead, the effect is evaluated as part of the strip itself.

This is useful for reusable effects such as:

- Color correction.
- Glows and blurs.
- Stylization effects.
- Distortion and warping.
- Overlays and masks.


Node Groups
-----------

Both compositor strips and modifiers use compositor node groups.

The available inputs depend on the compositor strip or modifier type.

.. note::

   - The first node group output socket must use the ``Color`` type.
   - Some strip types automatically provide image inputs to matching sockets.
   - If a compositor strip does not contain a ``Float`` input socket,
     the strip Fade control has no effect.
