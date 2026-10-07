.. index:: Compositor Nodes; Blank Image
.. _bpy.types.CompositorNodeBlankImage:

****************
Blank Image Node
****************

.. figure:: /images/node-types_CompositorNodeBlankImage.webp
   :align: right
   :alt: Blank Image Node.

The *Blank Image* node generates an image of a specified size filled with a constant color.

This node is commonly used for procedural workflows, such as generating masks, creating
custom kernels for convolution or bokeh effects, and building images for compositing operations.


Inputs
======

Color
   The color of all pixels in the image.
Size
   The size of the image.


Outputs
=======

Image
   The generated image of the given size and constant color.
