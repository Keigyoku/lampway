.. _bpy.types.ShaderNodeSeparateColor:

*******************
Separate Color Node
*******************

.. figure:: /images/node-types_ShaderNodeSeparateColor.webp
   :align: right
   :alt: Separate Color Node.

Splits a color into its channels,
based on a particular :term:`Color Model`.


Inputs
======

Color
   Standard color input.


Properties
==========

Mode
   The color model to output.

   :RGB: Red, Green, Blue.
   :HSV: Hue, Saturation, Value.
   :HSL: Hue, Saturation, Lightness.


Outputs
=======

The outputs of this node depend on the Mode property (see above).
