.. _bpy.types.ShaderNodeCombineColor:

******************
Combine Color Node
******************

.. figure:: /images/node-types_ShaderNodeCombineColor.webp
   :align: right
   :alt: Combine Color Node.

Combines three color channels into one color,
based on a particular :term:`Color Model`.


Inputs
======

The inputs of this node depend on the Mode property (see below).


Properties
==========

Mode
   The color model to use.

   :RGB: Red, Green, Blue.
   :HSV: Hue, Saturation, Value.
   :HSL: Hue, Saturation, Lightness.


Output
======

Color
   Standard color output.
