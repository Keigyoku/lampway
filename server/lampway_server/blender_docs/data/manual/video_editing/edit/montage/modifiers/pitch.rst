.. index:: Video Sequencer Modifiers; Sound Pitch Modifier
.. _bpy.types.PitchModifier:

**************
Pitch Modifier
**************

The *Pitch* modifier changes the pitch of a sound strip without altering its timing.
It can be used to correct pitch, create voice effects, or match the key of other audio.

Mode
   Mode of the pitch shift.

   :Semitones:
      Shift pitch using musical intervals.

      Semitones
         Number of semitones to shift the pitch.
         Positive values raise the pitch, negative values lower it.
      Cents
         Fine adjustment in cents (1/100 of a semitone).

   :Ratio:
      Shift pitch using a direct multiplier.

      Ratio
         Factor by which the audio pitch is scaled.
         Values greater than 1 raise the pitch, values less than 1 lower it.

Preserve Vocal Formants
   Preserve vocal formants when shifting pitch.
   This helps keep speech sounding more natural (for example, raising pitch without making the voice
   sound "chipmunk-like"), but may introduce additional processing artifacts depending on the audio.

Quality
   Quality of the pitch shifting.

   :High:
      Prioritize high-quality pitch processing, typically at the cost of performance.
      Best for final renders.
   :Fast:
      Prioritize speed over audio quality.
      Useful for editing and preview playback.
   :Consistent:
      Prioritize stability when pitch changes dynamically over time (for example, when animated).
      This can reduce sudden changes in processing quality, at the cost of additional artifacts in some cases.
