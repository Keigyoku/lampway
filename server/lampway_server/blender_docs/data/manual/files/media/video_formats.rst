
*******************************
Supported Video & Audio Formats
*******************************

Blender uses `FFmpeg <https://ffmpeg.org/>`__ to handle video encoding and decoding.
These formats are primarily used to compress rendered image sequences into playable movies.

A video file is typically composed of:

* A **container** -- wraps video, audio, and metadata into a single file.
* A **video codec** -- compresses the video stream.
* An **audio codec** -- compresses the audio stream (optional).



.. _files-video-containers:

Supported Video Containers
==========================

The container stores encoded streams but does not define how they are compressed.

:`MPEG-4 <https://en.wikipedia.org/wiki/MPEG-4>`__:
   While also referring to a family of codecs, MPEG-4 is a container format
   capable of storing video and audio streams encoded with various codecs.
   It is widely supported across modern software and hardware.

   File Extensions: ``.mp4``, ``.mpg``, ``.mpeg``
:`Matroska <https://en.wikipedia.org/wiki/Matroska>`__:
   A free open-standard container format capable of holding multiple
   video, audio, subtitle, and metadata tracks in a single file.

   File Extension: ``.mkv``
:`WebM <https://en.wikipedia.org/wiki/WebM>`__:
   A free open-standard container designed primarily for web streaming.
   This container supports VP9 or AV1 video and Vorbis or Opus audio codecs.

   File Extension: ``.webm``

-----

:`AVI <https://en.wikipedia.org/wiki/Audio_Video_Interleave>`__:
   One of the earliest and most widely used video container formats,
   derived from the Resource Interchange File Format (RIFF).

   File Extension: ``.avi``
:`DV <https://en.wikipedia.org/wiki/DV>`__:
   A digital video container used by many legacy camcorders.
   This container enforces the DV video codec and stores audio uncompressed.

   File Extension: ``.dv``
:`Flash <https://en.wikipedia.org/wiki/Flash_Video>`__:
   A container format formerly used for internet video delivery
   through Adobe Flash Player. This container enforces specific codecs.

   File Extension: ``.flv``
:`MPEG-1 <https://en.wikipedia.org/wiki/MPEG-1>`__:
   A container format for lossy video and audio compression.
   It enforces the MPEG-1 codec family.

   File Extensions: ``.mpg``, ``.mpeg``
:`MPEG-2 <https://en.wikipedia.org/wiki/MPEG-2>`__:
   A container used for DVD and broadcast video.
   It enforces MPEG-2 encoding for video and associated audio streams.

   File Extensions: ``.dvd``, ``.vob``, ``.mpg``, ``.mpeg``
:`Ogg <https://en.wikipedia.org/wiki/Ogg>`__:
   A free open-standard container capable of holding multiple
   video, audio, subtitle, or metadata streams.

   File Extensions: ``.ogg``, ``.ogv``
:`QuickTime <https://en.wikipedia.org/wiki/.mov>`__:
   A multi-track container format. It shares many codecs with MP4.
   While largely interchangeable in some workflows, MP4 is more widely supported.

   File Extension: ``.mov``


.. _files-video-codecs:

Supported Video Codecs
======================

Codecs compress video and audio data to reduce file size and enable continuous playback.

*Lossy* codecs reduce file size by discarding some data.
They produce smaller files at the expense of image or audio quality.

*Lossless* codecs preserve all original data while still applying compression.
They result in larger files but maintain full fidelity.

Some codecs are optimized for distribution and streaming (e.g., H.264, AV1),
while others are designed for editing and intermediate workflows (e.g., ProRes, DNxHD).

Because codecs are required for both encoding and decoding,
they must be available on both the system creating the file and the device playing it.

Not all codecs are available in all containers.

:No Video: For audio-only encoding.
:`AV1 <https://en.wikipedia.org/wiki/AV1>`__:
   A free open-standard lossy video compression format designed as a successor to VP9.
   Offers high compression efficiency and supports HDR output.
:`H.264 <https://en.wikipedia.org/wiki/Advanced_Video_Coding>`__:
   A widely used lossy codec offering a strong compression-to-quality ratio.
   Common for streaming and general delivery.

:`H.265 / HEVC <https://en.wikipedia.org/wiki/High_Efficiency_Video_Coding>`__:
   An improved successor to H.264 with better compression efficiency.
   Supports HDR output and higher bit depths.
:`WEBM / VP9 <https://en.wikipedia.org/wiki/VP9>`__:
   A free open-standard lossy video codec widely used for internet streaming.
   Supports alpha channel transparency.

-----

:`DNxHD <https://en.wikipedia.org/wiki/Avid_DNxHD>`__:
   Intended as an intermediate editing format.
   Can operate in either lossy or lossless modes.
:`DV <https://en.wikipedia.org/wiki/DV>`__:
   See :ref:`Containers <files-video-containers>`.
:`FFmpeg video codec #1 <https://en.wikipedia.org/wiki/FFV1>`__:
   A lossless intra-frame video codec.
   Supports alpha channel transparency.
:`Flash Video <https://en.wikipedia.org/wiki/Flash_Video>`__:
   See :ref:`Containers <files-video-containers>`.
:`HuffYUV <https://en.wikipedia.org/wiki/Huffyuv>`__:
   A lossless codec designed to replace uncompressed YCbCr capture formats.
:`MPEG-1 <https://en.wikipedia.org/wiki/MPEG-1>`__:
   See :ref:`Containers <files-video-containers>`.
:`MPEG-2 <https://en.wikipedia.org/wiki/MPEG-2>`__:
   See :ref:`Containers <files-video-containers>`.
:`MPEG-4(DivX) <https://en.wikipedia.org/wiki/MPEG-4>`__:
   A lossy codec extending MPEG standards with additional compression features.
:`ProRes <https://en.wikipedia.org/wiki/Apple_ProRes>`__:
   A high-quality, visually lossless codec commonly used in professional post-production.

   Supports configurable :ref:`Profile <bpy.types.FFmpegSettings.ffmpeg_prores_profile>`.

:`PNG <https://en.wikipedia.org/wiki/Portable_Network_Graphics>`__:
   Stores each frame as an independent image in the stream.
   Lossless and supports alpha channel transparency.
:`QuickTime Animation <https://en.wikipedia.org/wiki/QuickTime_Animation>`__:
   Legacy lossless QuickTime codec supporting alpha channel transparency.
:`Theora <https://en.wikipedia.org/wiki/Theora>`__:
   A free open-standard lossy codec designed for the Ogg container.


Supported Features
------------------

.. |tick|  unicode:: U+2713
.. |cross| unicode:: U+2717

.. list-table::
   :header-rows: 1
   :class: valign
   :widths: 30 20 20 10 10

   * - Codec
     - Compression
     - Color Depth
     - Alpha
     - HDR
   * - AV1
     - Lossy
     - 8, 10, 12bit
     - |cross|
     - |tick|
   * - H.264
     - Lossy
     - 8, 10bit
     - |cross|
     - |cross|
   * - H.265 / HEVC
     - Lossy
     - 8, 10, 12bit
     - |cross|
     - |tick|
   * - WEBM / VP9
     - Lossy
     - 8bit
     - |tick|
     - |cross|
   * - DNxHD
     - Lossy / Lossless
     - 8bit
     - |cross|
     - |cross|
   * - DV
     - Lossy
     - 8bit
     - |cross|
     - |cross|
   * - FFmpeg video codec #1
     - Lossless
     - 8, 10, 12, 16bit
     - |tick|
     - |cross|
   * - Flash Video
     - Lossy
     - 8bit
     - |cross|
     - |cross|
   * - HuffYUV
     - Lossless
     - 8bit
     - |cross|
     - |cross|
   * - MPEG-1
     - Lossy
     - 8bit
     - |cross|
     - |cross|
   * - MPEG-2
     - Lossy
     - 8bit
     - |cross|
     - |cross|
   * - MPEG-4 (DivX)
     - Lossy
     - 8bit
     - |cross|
     - |cross|
   * - ProRes
     - Visually Lossless
     - 8, 10bit
     - |cross|
     - |cross|
   * - PNG
     - Lossless
     - 8bit
     - |tick|
     - |cross|
   * - QuickTime Animation
     - Lossless
     - 8bit
     - |tick|
     - |cross|
   * - Theora
     - Lossy
     - 8bit
     - |cross|
     - |cross|


.. _files-audio-codecs:

FFmpeg Audio Codecs
===================

:No Audio:
   For video-only encoding.
:`AAC <https://en.wikipedia.org/wiki/Advanced_Audio_Coding>`__:
   A standardized lossy audio codec providing better quality than MP3 at similar bit rates.
:`AC3 <https://en.wikipedia.org/wiki/Dolby_Digital>`__:
   Dolby Digital audio compression format.
:`FLAC <https://en.wikipedia.org/wiki/FLAC>`__:
   A free lossless audio codec reducing file size while preserving full fidelity.
:`MP2 <https://en.wikipedia.org/wiki/MPEG-1_Audio_Layer_II>`__:
   A lossy audio compression format.
:`MP3 <https://en.wikipedia.org/wiki/MP3>`__:
   A widely supported lossy audio compression format.
:`Opus <https://en.wikipedia.org/wiki/Opus_(audio_format)>`__:
   A modern lossy codec designed for speech and general audio.
   Intended as a successor to Vorbis.
:`PCM <https://en.wikipedia.org/wiki/PCM>`__:
   Uncompressed digital audio format.
:`Vorbis <https://en.wikipedia.org/wiki/Vorbis>`__:
   A free open-standard lossy audio codec comparable to AAC or MP3.


HDR Support
===========

Videos can be rendered using wide-gamut and HDR color spaces.

To export HDR video:

* Set Color Management Display to Rec.2100 PQ or HLG.
* Set Video Codec to H.265 / HEVC or AV1.
* Set Bit Depth to 10 or 12.

HDR videos are written with 100 nits diffuse white
to match common video player conventions.

Compatibility varies between players and devices.
10-bit PQ is generally the most compatible HDR configuration.


Known Limitations
=================

Video Output Size
-----------------

Some codecs impose output size restrictions.
For example, H.264 requires both width and height to be divisible by 2.
