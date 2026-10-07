.. index:: Video Sequencer Modifiers; Color Balance Modifier
.. _bpy.types.ColorBalanceModifier:

**********************
Color Balance Modifier
**********************

Color balance adjustments, either by the Lift/Gamma/Gain or the Offset/Power/Slope method.

This modifier works similar to the :doc:`Color Balance Node </compositing/types/color/adjust/color_balance>`.

.. figure:: /images/video-editing_sequencer_sidebar_color-balance-modifier.webp
   :align: right

Depending on the selected method, the following operations can be applied to the color values in the
sequencer color space:

Lift/Gamma/Gain
   Lift
      Increases the value of dark colors.
   Gamma
      Adjusts midtones.
   Gain
      Adjusts highlights.

Offset/Power/Slope (ASC-CDL)
   The following formula is applied to each RGB color value separately: :math:`c_{out} =  (c_{in}×s + o)^p`

   Slope
      The multiplier :math:`s` influences all color values except black. Its effect is stronger
      the brighter the source color is.
   Offset
      Shifts color values after applying Slope by adding the Offset :math:`o` to them. Note that
      the selected value shown in the UI will be reduced by 1, so the default value of 1 means
      effectively no offset is applied.
   Power
      Overall exponent :math:`p`, which mainly adjusts the midtones.

.. include:: _common/masking.rst.frag
