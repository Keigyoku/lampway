.. index:: Video Sequencer Modifiers; Sound Echo Modifier
.. _bpy.types.EchoModifierModifier:

*************
Echo Modifier
*************

The *Echo* modifier adds delayed repetitions of the sound, creating an echo effect.
It can be used to simulate reflections, add depth, or create rhythmic audio effects.

Delay
   Time between each echo repetition in seconds.
   Larger values increase the spacing between echoes, while smaller values create
   a tighter, more rapid echo effect.

Feedback
   Amount of the echoed signal that is fed back into the effect.
   Higher values produce more repetitions and a longer decay,
   while lower values result in fewer echoes.

Mix
   Balance between the original (dry) signal and the echoed (wet) signal.
   A value of 0 uses only the original sound, while a value of 1 outputs only
   the echoed signal.
