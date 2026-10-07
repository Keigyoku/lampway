.. index:: Video Sequencer Modifiers; Mask Modifier

*************
Mask Modifier
*************

The mask modifier is used to affect the :term:`Alpha Channel` of the current strip.

.. _bpy.types.StripModifier.input_mask_type:

Mask Input Type
   Type of input data used for the mask.

   :Strip:
      Use the grayscale representation of another strip to affect the alpha of the current strip.
   :Mask:
      Use a mask data-block to affect the alpha of the current strip.

.. _bpy.types.StripModifier.input_mask_id:
.. _bpy.types.StripModifier.input_mask_strip:

Mask
   The Strip or Mask data-block to use.

.. _bpy.types.StripModifier.mask_time:

Mask Time :guilabel:`Mask Input Only`
   How the start frame of the mask is calculated.

   :Relative: Mask animation is offset to the start of the strip.
   :Absolute: Mask animation is in sync with the scene frame.
