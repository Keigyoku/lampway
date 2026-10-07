.. index:: Compositor Nodes; Split Toning

*****************
Split Toning Node
*****************

.. figure:: /images/node-types_CompositorNodeSplitToning.webp
   :align: right
   :alt: Split Toning Node.

.. --- modifier-intro-start ---

*Split Toning* applies different color tints to the highlights and shadows of an image.
This technique is widely used in photography and color grading to create mood, enhance contrast,
or stylize an image by giving distinct color tones to bright and dark regions.

For example, warm highlights and cool shadows can evoke a cinematic or nostalgic look,
while complementary tones can create stylized or dramatic effects.

.. --- modifier-intro-end ---


Inputs
======

Image
   Standard color input image.

.. --- modifier-options-start ---

Highlights
   The color tint applied to the bright areas of the image.

Factor Highlights
   Controls how strongly the *Highlights* color affects the bright regions.
   A value of 0 disables the effect, while 1 applies it fully.

Shadows
   The color tint applied to the darker areas of the image.

Factor Shadows
   Controls the strength of the *Shadows* tint.


Transition
----------

Balance
   Shifts the midpoint that defines what parts of the image are considered highlights or shadows.
   Increasing this value favors the highlight color; decreasing it favors the shadow color.

Smoothness
   Adjusts how gradually the image transitions between tinted shadows and highlights.
   Higher values create a smooth, natural blend; lower values make the transition more abrupt.

.. --- modifier-options-end ---


Outputs
=======

Image
   The input image with the split toning effect applied.
