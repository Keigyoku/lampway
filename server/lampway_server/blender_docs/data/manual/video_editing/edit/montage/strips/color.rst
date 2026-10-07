.. _bpy.types.ColorStrip:

***********
Color Strip
***********

A Color strip generates a solid color for its entire duration.

Color strips are useful as simple backgrounds, mattes, overlays, title
backgrounds, or as inputs to effects and transitions. They can also be
combined with opacity or blend modes to create fade-ins, fade-outs, flashes,
or color tints.


Options
=======

Color
   Color displayed by the strip.


Transform
=========

Width
   Width of the generated color image.

   Increasing the width extends the color beyond the scene resolution,
   while decreasing it creates transparent borders that can be positioned
   with the strip's transform properties.

Height
   Height of the generated color image.

   Increasing the height extends the color beyond the scene resolution,
   while decreasing it creates transparent borders that can be positioned
   with the strip's transform properties.
