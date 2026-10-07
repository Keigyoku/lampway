FFmpegSettings(bpy_struct)
==========================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: FFmpegSettings(bpy_struct)

   FFmpeg related settings for the scene

   .. attribute:: audio_bitrate

      Audio bitrate (kb/s) (in [32, 2048], default 192)

      :type: int

   .. attribute:: audio_channels

      Audio channel count (default ``'STEREO'``)

      - ``MONO``
        Mono -- Set audio channels to mono.
      - ``STEREO``
        Stereo -- Set audio channels to stereo.
      - ``SURROUND4``
        4 Channels -- Set audio channels to 4 channels.
      - ``SURROUND51``
        5.1 Surround -- Set audio channels to 5.1 surround sound.
      - ``SURROUND71``
        7.1 Surround -- Set audio channels to 7.1 surround sound.

      :type: Literal['MONO', 'STEREO', 'SURROUND4', 'SURROUND51', 'SURROUND71']

   .. attribute:: audio_codec

      FFmpeg audio codec to use (default ``'NONE'``)

      - ``NONE``
        No Audio -- Disables audio output, for video-only renders.
      - ``AAC``
        AAC.
      - ``AC3``
        AC3.
      - ``FLAC``
        FLAC.
      - ``MP2``
        MP2.
      - ``MP3``
        MP3.
      - ``OPUS``
        Opus.
      - ``PCM``
        PCM.
      - ``VORBIS``
        Vorbis.

      :type: Literal['NONE', 'AAC', 'AC3', 'FLAC', 'MP2', 'MP3', 'OPUS', 'PCM', 'VORBIS']

   .. attribute:: audio_mixrate

      Audio sample rate (samples/s) (in [8000, 192000], default 48000)

      :type: int

   .. attribute:: audio_volume

      Audio volume (in [0, 1], default 1.0)

      :type: float

   .. attribute:: buffersize

      Rate control: buffer size (kb) (in [0, 2000], default 0)

      :type: int

   .. attribute:: codec

      FFmpeg codec to use for video output (default ``'H264'``)

      - ``NONE``
        No Video -- Disables video output, for audio-only renders.
      - ``AV1``
        AV1.
      - ``H264``
        H.264.
      - ``H265``
        H.265 / HEVC.
      - ``WEBM``
        WebM / VP9.
      - ``DNXHD``
        DNxHD.
      - ``DV``
        DV.
      - ``FFV1``
        FFmpeg video codec #1.
      - ``FLASH``
        Flash Video.
      - ``HUFFYUV``
        HuffYUV.
      - ``MPEG1``
        MPEG-1.
      - ``MPEG2``
        MPEG-2.
      - ``MPEG4``
        MPEG-4 (divx).
      - ``PNG``
        PNG.
      - ``PRORES``
        ProRes.
      - ``QTRLE``
        QuickTime Animation.
      - ``THEORA``
        Theora.

      :type: Literal['NONE', 'AV1', 'H264', 'H265', 'WEBM', 'DNXHD', 'DV', 'FFV1', 'FLASH', 'HUFFYUV', 'MPEG1', 'MPEG2', 'MPEG4', 'PNG', 'PRORES', 'QTRLE', 'THEORA']

   .. attribute:: constant_rate_factor

      Constant Rate Factor (CRF); tradeoff between video quality and file size (default ``'MEDIUM'``)

      - ``NONE``
        Constant Bitrate -- Configure constant bit rate, rather than constant output quality.
      - ``LOSSLESS``
        Lossless.
      - ``PERC_LOSSLESS``
        Perceptually Lossless.
      - ``HIGH``
        High Quality.
      - ``MEDIUM``
        Medium Quality.
      - ``LOW``
        Low Quality.
      - ``VERYLOW``
        Very Low Quality.
      - ``LOWEST``
        Lowest Quality.
      - ``CUSTOM``
        Custom Quality -- Set a custom Constant Rate Factor (CRF)..

      :type: Literal['NONE', 'LOSSLESS', 'PERC_LOSSLESS', 'HIGH', 'MEDIUM', 'LOW', 'VERYLOW', 'LOWEST', 'CUSTOM']

   .. attribute:: custom_constant_rate_factor

      A smaller Constant Rate Factor (CRF) results in better video quality but larger file size. The range of allowed CRF values is dependent on the codec. (in [0, 63], default 23)

      :type: int

   .. attribute:: ffmpeg_preset

      Tradeoff between encoding speed and compression ratio (default ``'GOOD'``)

      - ``BEST``
        Slowest -- Recommended if you have lots of time and want the best compression efficiency.
      - ``GOOD``
        Good -- The default and recommended for most applications.
      - ``REALTIME``
        Realtime -- Recommended for fast encoding.

      :type: Literal['BEST', 'GOOD', 'REALTIME']

   .. attribute:: ffmpeg_prores_profile

      ProRes Profile (default ``'422_STD'``)

      :type: Literal['422_PROXY', '422_LT', '422_STD', '422_HQ', '4444', '4444_XQ']

   .. attribute:: format

      Output file container (default ``'MKV'``)

      :type: Literal['MPEG4', 'MKV', 'WEBM', 'AVI', 'DV', 'FLASH', 'MPEG1', 'MPEG2', 'OGG', 'QUICKTIME']

   .. attribute:: gopsize

      Distance between key frames, also known as GOP size; influences file size and seekability (in [0, 500], default 25)

      :type: int

   .. attribute:: max_b_frames

      Maximum number of B-frames between non-B-frames; influences file size and seekability (in [0, 16], default 0)

      :type: int

   .. attribute:: maxrate

      Rate control: max rate (kbit/s) (in [-inf, inf], default 0)

      :type: int

   .. attribute:: minrate

      Rate control: min rate (kbit/s) (in [-inf, inf], default 0)

      :type: int

   .. attribute:: muxrate

      Mux rate (bits/second) (in [0, inf], default 0)

      :type: int

   .. attribute:: packetsize

      Mux packet size (byte) (in [0, 16384], default 0)

      :type: int

   .. attribute:: use_autosplit

      Autosplit output at 2GB boundary (default False)

      :type: bool

   .. attribute:: use_lossless_output

      Use lossless output for video streams (default False)

      :type: bool

   .. attribute:: use_max_b_frames

      Set a maximum number of B-frames (default False)

      :type: bool

   .. attribute:: video_bitrate

      Video bitrate (kbit/s) (in [-inf, inf], default 0)

      :type: int

   .. classmethod:: bl_rna_get_subclass(id, default=None, /)
   
      :param id: The RNA type identifier.
      :type id: str
      :param default: The value to return when not found.
      :type default: :class:`bpy.types.Struct` | None
      :return: The RNA type or default when not found.
      :rtype: :class:`bpy.types.Struct`


   .. classmethod:: bl_rna_get_subclass_py(id, default=None, /)
   
      :param id: The RNA type identifier.
      :type id: str
      :param default: The value to return when not found.
      :type default: type | None
      :return: The class or default when not found.
      :rtype: type


Inherited Properties
--------------------

.. hlist::
   :columns: 2

   - :class:`bpy_struct.id_data`

Inherited Functions
-------------------

.. hlist::
   :columns: 2

   - :class:`bpy_struct.as_pointer`
   - :class:`bpy_struct.driver_add`
   - :class:`bpy_struct.driver_remove`
   - :class:`bpy_struct.get`
   - :class:`bpy_struct.id_properties_clear`
   - :class:`bpy_struct.id_properties_ensure`
   - :class:`bpy_struct.id_properties_ui`
   - :class:`bpy_struct.is_property_hidden`
   - :class:`bpy_struct.is_property_overridable_library`
   - :class:`bpy_struct.is_property_readonly`
   - :class:`bpy_struct.is_property_set`
   - :class:`bpy_struct.items`
   - :class:`bpy_struct.keyframe_delete`
   - :class:`bpy_struct.keyframe_insert`
   - :class:`bpy_struct.keys`
   - :class:`bpy_struct.path_from_id`
   - :class:`bpy_struct.path_from_module`
   - :class:`bpy_struct.path_resolve`
   - :class:`bpy_struct.pop`
   - :class:`bpy_struct.property_overridable_library_set`
   - :class:`bpy_struct.property_unset`
   - :class:`bpy_struct.rna_ancestors`
   - :class:`bpy_struct.type_recast`
   - :class:`bpy_struct.values`

References
----------

.. hlist::
   :columns: 2

   - :class:`RenderSettings.ffmpeg`

