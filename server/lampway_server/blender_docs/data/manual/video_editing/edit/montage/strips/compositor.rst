.. _bpy.types.CompositorStrip:

****************
Compositor Strip
****************

The *Compositor* strip applies a :doc:`Compositor </compositing/index>` node group
directly inside the Video Sequence Editor.

Unlike built-in effect strips with fixed behavior, compositor strips allow creating
custom effects, transitions, and procedural visuals using compositor nodes.
The effect behavior depends entirely on the assigned node group.

Compositor strips can operate as:

- A transition between two strips.
- A single-input effect applied to one strip.
- A procedural effect with no strip inputs.

The type is determined automatically from the selected strips when the strip is created.


Add
===

.. reference::

   :Mode:      Sequencer
   :Menu:      :menuselection:`Add --> Compositor`

The type of compositor strip created depends on the current strip selection.

The selected strips become the inputs of the compositor effect and can later be
reassigned using the same workflow as other VSE effect strips.
For two-input compositor strips, the inputs can also be swapped.

- **No Strips Selected** -- Creates a compositor strip without inputs.
- **One Strip Selected** -- Creates a single-input compositor effect.
- **Two Strips Selected** -- Creates a two-input compositor effect or transition.


Properties
==========

Node Group
   The compositing node group to use.

Input 1
   The first strip used as an input for the compositor effect.

Input 2
   The second strip used as an input for the compositor effect.

   Only available for two-input compositor strips.

Default Fade
   Automatically drives the *Effect Fader* compositor input from ``0.0`` to ``1.0`` across the strip duration.

   When disabled, the *Effect Fader* value becomes manually editable,
   allowing custom animation using keyframes or drivers.

Effect Fader
   Controls the blend amount of the effect.

   Typically, a value of ``0.0`` represents the start or disabled state of the effect,
   while ``1.0`` represents the fully applied state.

   This property is only available when *Default Fade* is disabled.


Node Group
==========

The compositor strip uses a compositor node group to define its behavior.

The node group selector is available in the strip properties.


Group Inputs
------------

The available node group inputs depend on the compositor strip type.

.. note::

   - The first node group output socket must be a ``Color`` type.
   - If the node group does not contain a ``Float`` input socket,
     the strip Fade control has no effect.


Zero-Input Effects
^^^^^^^^^^^^^^^^^^

Used for procedural effects such as gradients, textures, or generated visuals.

The node group contains:

Effect Fader
   A float value automatically animated from ``0`` to ``1`` over the strip duration.


Single-Input Effects
^^^^^^^^^^^^^^^^^^^^

Used for screen-space processing effects such as blur, glow, or stylization.

The node group contains:

Input
   The image from the input strip.

Effect Fader
   A float value automatically animated from ``0`` to ``1`` over the strip duration.


Two-Input Effects
^^^^^^^^^^^^^^^^^

Used for transitions and combining two strips together.

The node group contains:

Input 1
   The first strip input.

Input 2
   The second strip input.

Effect Fader
   A float value automatically animated from ``0`` to ``1`` over the strip duration.


Usage
=====

Compositor strips support all compositor nodes that operate on image data,
allowing custom effects directly in the timeline.

Typical use cases include:

- Custom transitions.
- Stylized screen-space effects.
- Color processing pipelines.
- Procedural overlays and gradients.
- Glows, blurs, and distortion effects.
- Multi-layer image compositing.

.. note::

   Compositor strips process images in screen space after strip transformations
   are applied.

   This differs from strip modifiers, which process strips in their local image space
   before transformations.
