.. index:: Geometry Nodes; Sample Sound Frequencies
.. _bpy.types.GeometryNodeSampleSoundFrequencies:

*****************************
Sample Sound Frequencies Node
*****************************

.. figure:: /images/node-types_GeometryNodeSampleSoundFrequencies.webp
   :align: center
   :alt: Sample Sound Frequencies node.

The *Sample Sound Frequencies* node retrieves the amplitude of a frequency range
from a sound data-block at a given point in time.

This can be used to drive animations, procedural effects, or geometry based on
the intensity of specific frequency bands in an audio file.


Inputs
======

Sound
   The sound data-block to sample.

Time
   The time, in seconds, at which to sample the sound.

All Channels
   Mix all audio channels together before sampling.

   For example, a stereo sound is converted to a single mono signal.

Channel
   The audio channel to sample when *All Channels* is disabled.

Low
   The lower bound of the sampled frequency range, in Hertz.

High
   The upper bound of the sampled frequency range, in Hertz.


FFT
---

Settings that control the Fourier transform used for frequency analysis.

FFT Size
   The number of audio samples processed in each discrete Fourier transform.

   Higher values provide better frequency resolution but lower time resolution.
   Lower values provide better time resolution but lower frequency resolution.

   :128: Very high time resolution with coarse frequency resolution.
   :256: High time resolution with coarse frequency resolution.
   :512: Balanced toward time resolution.
   :1024: Moderate frequency and time resolution.
   :2048: Good balance between frequency and time resolution.
   :4096: Increased frequency resolution with reduced time resolution.
   :8192: High frequency resolution for detailed spectral analysis.
   :16384: Very high frequency resolution with low time resolution.
   :32768: Maximum frequency resolution with the lowest time resolution.

Window Function
   Applies a weighting function to the analyzed samples before performing the
   Fourier transform. This reduces discontinuities at the edges of the sample
   window, helping to reduce spectral artifacts.

   :Hann: General-purpose window with good frequency analysis characteristics.
   :Hamming: Similar to Hann with slightly different side-lobe behavior.
   :Blackman:
      Provides stronger suppression of spectral leakage at the cost of wider frequency peaks.
   :Rectangular: No windowing is applied.


Outputs
=======

Amplitude
   The summed amplitude of all frequencies within the specified frequency range.
