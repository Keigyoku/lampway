Audio System (aud)
==================

.. module:: aud

Audaspace (pronounced "outer space") is a high level audio library.


Basic Sound Playback
++++++++++++++++++++

This script shows how to use the classes: :class:`Device`, :class:`Sound` and
:class:`Handle`.

.. literalinclude:: ../examples/aud.0.py
   :lines: 8-

.. data:: AP_LOCATION

   Constant value 3

   :type: int

.. data:: AP_ORIENTATION

   Constant value 4

   :type: int

.. data:: AP_PANNING

   Constant value 1

   :type: int

.. data:: AP_PITCH

   Constant value 2

   :type: int

.. data:: AP_PITCH_SCALE

   Constant value 6

   :type: int

.. data:: AP_TIME_STRETCH

   Constant value 5

   :type: int

.. data:: AP_VOLUME

   Constant value 0

   :type: int

.. data:: CHANNELS_INVALID

   Constant value 0

   :type: int

.. data:: CHANNELS_MONO

   Constant value 1

   :type: int

.. data:: CHANNELS_STEREO

   Constant value 2

   :type: int

.. data:: CHANNELS_STEREO_LFE

   Constant value 3

   :type: int

.. data:: CHANNELS_SURROUND4

   Constant value 4

   :type: int

.. data:: CHANNELS_SURROUND5

   Constant value 5

   :type: int

.. data:: CHANNELS_SURROUND51

   Constant value 6

   :type: int

.. data:: CHANNELS_SURROUND61

   Constant value 7

   :type: int

.. data:: CHANNELS_SURROUND71

   Constant value 8

   :type: int

.. data:: CODEC_AAC

   Constant value 1

   :type: int

.. data:: CODEC_AC3

   Constant value 2

   :type: int

.. data:: CODEC_FLAC

   Constant value 3

   :type: int

.. data:: CODEC_INVALID

   Constant value 0

   :type: int

.. data:: CODEC_MP2

   Constant value 4

   :type: int

.. data:: CODEC_MP3

   Constant value 5

   :type: int

.. data:: CODEC_OPUS

   Constant value 8

   :type: int

.. data:: CODEC_PCM

   Constant value 6

   :type: int

.. data:: CODEC_VORBIS

   Constant value 7

   :type: int

.. data:: CONTAINER_AAC

   Constant value 8

   :type: int

.. data:: CONTAINER_AC3

   Constant value 1

   :type: int

.. data:: CONTAINER_FLAC

   Constant value 2

   :type: int

.. data:: CONTAINER_INVALID

   Constant value 0

   :type: int

.. data:: CONTAINER_MATROSKA

   Constant value 3

   :type: int

.. data:: CONTAINER_MP2

   Constant value 4

   :type: int

.. data:: CONTAINER_MP3

   Constant value 5

   :type: int

.. data:: CONTAINER_OGG

   Constant value 6

   :type: int

.. data:: CONTAINER_WAV

   Constant value 7

   :type: int

.. data:: DISTANCE_MODEL_EXPONENT

   Constant value 5

   :type: int

.. data:: DISTANCE_MODEL_EXPONENT_CLAMPED

   Constant value 6

   :type: int

.. data:: DISTANCE_MODEL_INVALID

   Constant value 0

   :type: int

.. data:: DISTANCE_MODEL_INVERSE

   Constant value 1

   :type: int

.. data:: DISTANCE_MODEL_INVERSE_CLAMPED

   Constant value 2

   :type: int

.. data:: DISTANCE_MODEL_LINEAR

   Constant value 3

   :type: int

.. data:: DISTANCE_MODEL_LINEAR_CLAMPED

   Constant value 4

   :type: int

.. data:: FORMAT_FLOAT32

   Constant value 36

   :type: int

.. data:: FORMAT_FLOAT64

   Constant value 40

   :type: int

.. data:: FORMAT_INVALID

   Constant value 0

   :type: int

.. data:: FORMAT_S16

   Constant value 18

   :type: int

.. data:: FORMAT_S24

   Constant value 19

   :type: int

.. data:: FORMAT_S32

   Constant value 20

   :type: int

.. data:: FORMAT_U8

   Constant value 1

   :type: int

.. data:: RATE_11025

   Constant value 11025

   :type: int

.. data:: RATE_16000

   Constant value 16000

   :type: int

.. data:: RATE_192000

   Constant value 192000

   :type: int

.. data:: RATE_22050

   Constant value 22050

   :type: int

.. data:: RATE_32000

   Constant value 32000

   :type: int

.. data:: RATE_44100

   Constant value 44100

   :type: int

.. data:: RATE_48000

   Constant value 48000

   :type: int

.. data:: RATE_8000

   Constant value 8000

   :type: int

.. data:: RATE_88200

   Constant value 88200

   :type: int

.. data:: RATE_96000

   Constant value 96000

   :type: int

.. data:: RATE_INVALID

   Constant value 0

   :type: int

.. data:: STATUS_INVALID

   Constant value 0

   :type: int

.. data:: STATUS_PAUSED

   Constant value 2

   :type: int

.. data:: STATUS_PLAYING

   Constant value 1

   :type: int

.. data:: STATUS_STOPPED

   Constant value 3

   :type: int

.. data:: STRETCHER_QUALITY_CONSISTENT

   Constant value 2

   :type: int

.. data:: STRETCHER_QUALITY_FAST

   Constant value 1

   :type: int

.. data:: STRETCHER_QUALITY_HIGH

   Constant value 0

   :type: int

.. class:: AnimateableProperty(count, value=0.0, /)

   An AnimateableProperty object stores an array of float values for animating sound properties (e.g. pan, volume, pitch-scale).

   :arg count: The number of float values to store per frame.
   :type count: int
   :arg value: The initial value for all elements.
   :type value: float

   .. method:: read(position)
   
      Reads the properties value at the given position.
   
      :param position: The position in the animation in frames.
      :type position: float
      :return: A numpy array of values representing the properties value.
      :rtype: :class:`numpy.ndarray`


   .. method:: readSingle(position)
   
      Reads the properties value at the given position, assuming there is exactly one value.
   
      :param position: The position in the animation in frames.
      :type position: float
      :return: The value at that position.
      :rtype: float


   .. method:: write(data[, position])
   
      Writes the properties value.
   
      If `position` is also given, the property is marked animated and
      the values are written starting at `position`.
   
      :param data: numpy array of float32 values.
      :type data: numpy.ndarray
      :param position: The starting position in frames.
      :type position: int


   .. method:: writeConstantRange(data, position_start, position_end)
   
      Fills the properties frame range with a constant value and marks it animated.
   
      :param data: numpy array of float values representing the constant value.
      :type data: numpy.ndarray
      :param position_start: The start position in frames.
      :type position_start: int
      :param position_end: The end position in frames.
      :type position_end: int


   .. attribute:: animated

      Whether the property is animated.


   .. attribute:: count

      The count of floats for a property.




.. class:: Device(type='', rate=48000.0, channels=2, format=36, buffer_size=1024, name='')

   Device objects represent an audio output backend like OpenAL or SDL, but might also represent a file output or RAM buffer output.

   :arg type: The device type. An empty string means the default device.
   :type type: string
   :arg rate: The sample rate in Hz.
   :type rate: double
   :arg channels: The number of channels.
   :type channels: int
   :arg format: The sample format.
   :type format: int
   :arg buffer_size: The size of the audio buffer in samples.
   :type buffer_size: int
   :arg name: The name of the device.
   :type name: string

   .. method:: lock()
   
      Locks the device so that it's guaranteed, that no samples are
      read from the streams until :meth:`unlock` is called.
      This is useful if you want to do start/stop/pause/resume some
      sounds at the same time.
   
      .. note::
   
         The device has to be unlocked as often as locked to be
         able to continue playback.
   
      .. warning::
   
         Make sure the time between locking and unlocking is
         as short as possible to avoid clicks.


   .. method:: play(sound, keep=False)
   
      Plays a sound.
   
      :arg sound: The sound to play.
      :type sound: :class:`Sound`
      :arg keep: See :attr:`Handle.keep`.
      :type keep: bool
      :return: The playback handle with which playback can be
         controlled with.
      :rtype: :class:`Handle`


   .. method:: stopAll()
   
      Stops all playing and paused sounds.


   .. method:: unlock()
   
      Unlocks the device after a lock call, see :meth:`lock` for
      details.


   .. attribute:: channels

      The channel count of the device.


   .. attribute:: distance_model

      The distance model of the device.
      
      .. seealso:: `OpenAL Documentation <https://www.openal.org/documentation/>`__


   .. attribute:: doppler_factor

      The doppler factor of the device.
      This factor is a scaling factor for the velocity vectors in doppler calculation. So a value bigger than 1 will exaggerate the effect as it raises the velocity.


   .. attribute:: format

      The native sample format of the device.


   .. attribute:: listener_location

      The listeners's location in 3D space, a 3D tuple of floats.


   .. attribute:: listener_orientation

      The listener's orientation in 3D space as quaternion, a 4 float tuple.


   .. attribute:: listener_velocity

      The listener's velocity in 3D space, a 3D tuple of floats.


   .. attribute:: rate

      The sampling rate of the device in Hz.


   .. attribute:: speed_of_sound

      The speed of sound of the device.
      The speed of sound in air is typically 343.3 m/s.


   .. attribute:: volume

      The overall volume of the device.




.. class:: DynamicMusic(device, /)

   The DynamicMusic object allows to play music depending on a current scene, scene changes are managed by the class, with the possibility of custom transitions.
   The default transition is a crossfade effect, and the default scene is silent and has id 0.

   :arg device: The device that will be used to play sounds.
   :type device: :class:`Device`

   .. method:: addScene(scene)
   
      Adds a new scene.
   
      :arg scene: The scene sound.
      :type scene: :class:`Sound`
      :return: The new scene id.
      :rtype: int


   .. method:: addTransition(ini, end, transition)
   
      Adds a new scene.
   
      :arg ini: the initial scene foor the transition.
      :type ini: int
      :arg end: The final scene for the transition.
      :type end: int
      :arg transition: The transition sound.
      :type transition: :class:`Sound`
      :return: false if the ini or end scenes don't exist, true otherwise.
      :rtype: bool


   .. method:: pause()
   
      Pauses playback of the scene.
   
      :return: Whether the action succeeded.
      :rtype: bool


   .. method:: resume()
   
      Resumes playback of the scene.
   
      :return: Whether the action succeeded.
      :rtype: bool


   .. method:: stop()
   
      Stops playback of the scene.
   
      :return: Whether the action succeeded.
      :rtype: bool


   .. attribute:: fadeTime

      The length in seconds of the crossfade transition


   .. attribute:: position

      The playback position of the scene in seconds.


   .. attribute:: scene

      The current scene


   .. attribute:: status

      Whether the scene is playing, paused or stopped (=invalid).


   .. attribute:: volume

      The volume of the scene.




.. class:: HRTF()

   An HRTF object represents a set of head related transfer functions as impulse responses. It's used for binaural sound.

   .. method:: loadLeftHrtfSet(extension, directory)
   
      Loads all HRTFs from a directory.
   
      :arg extension: The file extension of the hrtfs.
      :type extension: string
      :arg directory: The path to where the HRTF files are located.
      :type extension: string
      :return: The loaded :class:`HRTF` object.
      :rtype: :class:`HRTF`


   .. method:: loadRightHrtfSet(extension, directory)
   
      Loads all HRTFs from a directory.
   
      :arg extension: The file extension of the hrtfs.
      :type extension: string
      :arg directory: The path to where the HRTF files are located.
      :type extension: string
      :return: The loaded :class:`HRTF` object.
      :rtype: :class:`HRTF`


   .. method:: addImpulseResponseFromSound(sound, azimuth, elevation)
   
      Adds a new hrtf to the HRTF object
   
      :arg sound: The sound that contains the hrtf.
      :type sound: :class:`Sound`
      :arg azimuth: The azimuth angle of the hrtf.
      :type azimuth: float
      :arg elevation: The elevation angle of the hrtf.
      :type elevation: float
      :return: Whether the action succeeded.
      :rtype: bool




.. class:: Handle

   Handle objects are playback handles that can be used to control playback of a sound. If a sound is played back multiple times then there are as many handles.

   .. method:: pause()
   
      Pauses playback.
   
      :return: Whether the action succeeded.
      :rtype: bool


   .. method:: resume()
   
      Resumes playback.
   
      :return: Whether the action succeeded.
      :rtype: bool


   .. method:: stop()
   
      Stops playback.
   
      :return: Whether the action succeeded.
      :rtype: bool
   
      .. note:: This makes the handle invalid.


   .. attribute:: attenuation

      This factor is used for distance based attenuation of the source.
      
      .. seealso:: :attr:`Device.distance_model`


   .. attribute:: cone_angle_inner

      The opening angle of the inner cone of the source. If the cone values of a source are set there are two (audible) cones with the apex at the :attr:`location` of the source and with infinite height, heading in the direction of the source's :attr:`orientation`.
      In the inner cone the volume is normal. Outside the outer cone the volume will be :attr:`cone_volume_outer` and in the area between the volume will be interpolated linearly.


   .. attribute:: cone_angle_outer

      The opening angle of the outer cone of the source.
      
      .. seealso:: :attr:`cone_angle_inner`


   .. attribute:: cone_volume_outer

      The volume outside the outer cone of the source.
      
      .. seealso:: :attr:`cone_angle_inner`


   .. attribute:: distance_maximum

      The maximum distance of the source.
      If the listener is further away the source volume will be 0.
      
      .. seealso:: :attr:`Device.distance_model`


   .. attribute:: distance_reference

      The reference distance of the source.
      At this distance the volume will be exactly :attr:`volume`.
      
      .. seealso:: :attr:`Device.distance_model`


   .. attribute:: keep

      Whether the sound should be kept paused in the device when its end is reached.
      This can be used to seek the sound to some position and start playback again.
      
      .. warning:: If this is set to true and you forget stopping this equals a memory leak as the handle exists until the device is destroyed.


   .. attribute:: location

      The source's location in 3D space, a 3D tuple of floats.


   .. attribute:: loop_count

      The (remaining) loop count of the sound. A negative value indicates infinity.


   .. attribute:: orientation

      The source's orientation in 3D space as quaternion, a 4 float tuple.


   .. attribute:: pitch

      The pitch of the sound.


   .. attribute:: position

      The playback position of the sound in seconds.


   .. attribute:: relative

      Whether the source's location, velocity and orientation is relative or absolute to the listener.


   .. attribute:: status

      Whether the sound is playing, paused or stopped (=invalid).


   .. attribute:: velocity

      The source's velocity in 3D space, a 3D tuple of floats.


   .. attribute:: volume

      The volume of the sound.


   .. attribute:: volume_maximum

      The maximum volume of the source.
      
      .. seealso:: :attr:`Device.distance_model`


   .. attribute:: volume_minimum

      The minimum volume of the source.
      
      .. seealso:: :attr:`Device.distance_model`




.. class:: ImpulseResponse(sound, /)

   An ImpulseResponse object represents a filter with which to convolve a sound.

   :arg sound: The sound to use as the impulse response.
   :type sound: :class:`Sound`



.. class:: PlaybackManager(device, /)

   A PlaybackManager object allows to easily control groups of sounds organized in categories.

   :arg device: The device that will be used to play sounds.
   :type device: :class:`Device`

   .. method:: addCategory(volume)
   
      Adds a category with a custom volume.
   
      :arg volume: The volume for ther new category.
      :type volume: float
      :return: The key of the new category.
      :rtype: int


   .. method:: clean()
   
      Cleans all the invalid and finished sound from the playback manager.


   .. method:: getVolume(catKey)
   
      Retrieves the volume of a category.
   
      :arg catKey: the key of the category.
      :type catKey: int
      :return: The volume of the category.
      :rtype: float


   .. method:: pause(catKey)
   
      Pauses playback of the category.
   
      :arg catKey: the key of the category.
      :type catKey: int
      :return: Whether the action succeeded.
      :rtype: bool


   .. method:: play(sound, catKey)
   
      Plays a sound through the playback manager and assigns it to a category.
   
      :arg sound: The sound to play.
      :type sound: :class:`Sound`
      :arg catKey: the key of the category in which the sound will be added,
         if it doesn't exist, a new one will be created.
      :type catKey: int
      :return: The playback handle with which playback can be controlled with.
      :rtype: :class:`Handle`


   .. method:: resume(catKey)
   
      Resumes playback of the catgory.
   
      :arg catKey: the key of the category.
      :type catKey: int
      :return: Whether the action succeeded.
      :rtype: bool


   .. method:: setVolume(volume, catKey)
   
      Changes the volume of a category.
   
      :arg volume: the new volume value.
      :type volume: float
      :arg catKey: the key of the category.
      :type catKey: int
      :return: Whether the action succeeded.
      :rtype: int


   .. method:: stop(catKey)
   
      Stops playback of the category.
   
      :arg catKey: the key of the category.
      :type catKey: int
      :return: Whether the action succeeded.
      :rtype: bool




.. class:: Sequence(channels=2, rate=48000.0, fps=30.0, muted=False)

   This sound represents sequenced entries to play a sound sequence.

   :arg channels: The number of channels.
   :type channels: int
   :arg rate: The sample rate in Hz.
   :type rate: double
   :arg fps: The frames per second of the sequence.
   :type fps: float
   :arg muted: Whether the sequence is muted.
   :type muted: bool

   .. method:: add()
   
      Adds a new entry to the sequence.
   
      :arg sound: The sound this entry should play.
      :type sound: :class:`Sound`
      :arg begin: The start time.
      :type begin: double
      :arg end: The end time or a negative value if determined by the sound.
      :type end: double
      :arg skip: How much seconds should be skipped at the beginning.
      :type skip: double
      :return: The entry added.
      :rtype: :class:`SequenceEntry`


   .. method:: remove()
   
      Removes an entry from the sequence.
   
      :arg entry: The entry to remove.
      :type entry: :class:`SequenceEntry`


   .. method:: setAnimationData()
   
      Writes animation data to a sequence.
   
      :arg type: The type of animation data.
      :type type: int
      :arg frame: The frame this data is for.
      :type frame: int
      :arg data: The data to write.
      :type data: sequence of float
      :arg animated: Whether the attribute is animated.
      :type animated: bool


   .. attribute:: channels

      The channel count of the sequence.


   .. attribute:: distance_model

      The distance model of the sequence.
      
      .. seealso:: `OpenAL Documentation <https://www.openal.org/documentation/>`__


   .. attribute:: doppler_factor

      The doppler factor of the sequence.
      This factor is a scaling factor for the velocity vectors in doppler calculation. So a value bigger than 1 will exaggerate the effect as it raises the velocity.


   .. attribute:: fps

      The listeners's location in 3D space, a 3D tuple of floats.


   .. attribute:: muted

      Whether the whole sequence is muted.


   .. attribute:: rate

      The sampling rate of the sequence in Hz.


   .. attribute:: speed_of_sound

      The speed of sound of the sequence.
      The speed of sound in air is typically 343.3 m/s.




.. class:: SequenceEntry

   SequenceEntry objects represent an entry of a sequenced sound.

   .. method:: move()
   
      Moves the entry.
   
      :arg begin: The new start time.
      :type begin: double
      :arg end: The new end time or a negative value if unknown.
      :type end: double
      :arg skip: How many seconds to skip at the beginning.
      :type skip: double


   .. method:: setAnimationData()
   
      Writes animation data to a sequenced entry.
   
      :arg type: The type of animation data.
      :type type: int
      :arg frame: The frame this data is for.
      :type frame: int
      :arg data: The data to write.
      :type data: sequence of float
      :arg animated: Whether the attribute is animated.
      :type animated: bool


   .. attribute:: attenuation

      This factor is used for distance based attenuation of the source.
      
      .. seealso:: :attr:`Device.distance_model`


   .. attribute:: cone_angle_inner

      The opening angle of the inner cone of the source. If the cone values of a source are set there are two (audible) cones with the apex at the :attr:`location` of the source and with infinite height, heading in the direction of the source's :attr:`orientation`.
      In the inner cone the volume is normal. Outside the outer cone the volume will be :attr:`cone_volume_outer` and in the area between the volume will be interpolated linearly.


   .. attribute:: cone_angle_outer

      The opening angle of the outer cone of the source.
      
      .. seealso:: :attr:`cone_angle_inner`


   .. attribute:: cone_volume_outer

      The volume outside the outer cone of the source.
      
      .. seealso:: :attr:`cone_angle_inner`


   .. attribute:: distance_maximum

      The maximum distance of the source.
      If the listener is further away the source volume will be 0.
      
      .. seealso:: :attr:`Device.distance_model`


   .. attribute:: distance_reference

      The reference distance of the source.
      At this distance the volume will be exactly :attr:`volume`.
      
      .. seealso:: :attr:`Device.distance_model`


   .. attribute:: muted

      Whether the entry is muted.


   .. attribute:: relative

      Whether the source's location, velocity and orientation is relative or absolute to the listener.


   .. attribute:: sound

      The sound the entry is representing and will be played in the sequence.


   .. attribute:: volume_maximum

      The maximum volume of the source.
      
      .. seealso:: :attr:`Device.distance_model`


   .. attribute:: volume_minimum

      The minimum volume of the source.
      
      .. seealso:: :attr:`Device.distance_model`




.. class:: Sound(filename, stream=0)

   Sound objects are immutable and represent a sound that can be played simultaneously multiple times. They are called factories because they create reader objects internally that are used for playback.

   :arg filename: Path of the file.
   :type filename: string
   :arg stream: The index of the audio stream within the file if it
      contains multiple audio streams, 0 by default.
   :type stream: int

   .. classmethod:: buffer(data, rate)
   
      Creates a sound from a data buffer.
   
      :arg data: The data as two dimensional numpy array.
      :type data: :class:`numpy.ndarray`
      :arg rate: The sample rate.
      :type rate: double
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. classmethod:: file(filename)
   
      Creates a sound object of a sound file.
   
      :arg filename: Path of the file.
      :type filename: string
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. warning::
   
         If the file doesn't exist or can't be read you will
         not get an exception immediately, but when you try to start
         playback of that sound.


   .. classmethod:: list()
   
      Creates an empty sound list that can contain several sounds.
   
      :arg random: whether the playback will be random or not.
      :type random: int
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. classmethod:: sawtooth(frequency, rate=48000)
   
      Creates a sawtooth sound which plays a sawtooth wave.
   
      :arg frequency: The frequency of the sawtooth wave in Hz.
      :type frequency: float
      :arg rate: The sampling rate in Hz. It's recommended to set this
         value to the playback device's sampling rate to avoid resampling.
      :type rate: int
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. classmethod:: silence(rate=48000)
   
      Creates a silence sound which plays simple silence.
   
      :arg rate: The sampling rate in Hz. It's recommended to set this
         value to the playback device's sampling rate to avoid resampling.
      :type rate: int
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. classmethod:: sine(frequency, rate=48000)
   
      Creates a sine sound which plays a sine wave.
   
      :arg frequency: The frequency of the sine wave in Hz.
      :type frequency: float
      :arg rate: The sampling rate in Hz. It's recommended to set this
         value to the playback device's sampling rate to avoid resampling.
      :type rate: int
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. classmethod:: square(frequency, rate=48000)
   
      Creates a square sound which plays a square wave.
   
      :arg frequency: The frequency of the square wave in Hz.
      :type frequency: float
      :arg rate: The sampling rate in Hz. It's recommended to set this
         value to the playback device's sampling rate to avoid resampling.
      :type rate: int
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. classmethod:: triangle(frequency, rate=48000)
   
      Creates a triangle sound which plays a triangle wave.
   
      :arg frequency: The frequency of the triangle wave in Hz.
      :type frequency: float
      :arg rate: The sampling rate in Hz. It's recommended to set this
         value to the playback device's sampling rate to avoid resampling.
      :type rate: int
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: ADSR(attack, decay, sustain, release)
   
      Attack-Decay-Sustain-Release envelopes the volume of a sound.
      Note: there is currently no way to trigger the release with this API.
   
      :arg attack: The attack time in seconds.
      :type attack: float
      :arg decay: The decay time in seconds.
      :type decay: float
      :arg sustain: The sustain level.
      :type sustain: float
      :arg release: The release level.
      :type release: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: accumulate(additive=False)
   
      Accumulates a sound by summing over positive input
      differences thus generating a monotonic sigal.
      If additivity is set to true negative input differences get added too,
      but positive ones with a factor of two.
   
      Note that with additivity the signal is not monotonic anymore.
   
      :arg additive: Whether the accumulation should be additive or not.
      :type time: bool
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: addSound(sound)
   
      Adds a new sound to a sound list.
   
      :arg sound: The sound that will be added to the list.
      :type sound: :class:`Sound`
   
      .. note:: You can only add a sound to a sound list.


   .. method:: animateableTimeStretchPitchScale(fps[, time_stretch, pitch_scale, quality, preserve_formant])
   
      Applies time-stretching and pitch-scaling to the sound.
   
      :arg fps: The FPS of the animation system.
      :type fps: float
      :arg time_stretch: The factor by which to stretch or compress time.
      :type time_stretch: float or :class:`AnimateablePropertyP`
      :arg pitch_scale: The factor by which to adjust the pitch.
      :type pitch_scale: float or :class:`AnimateablePropertyP`
       :arg quality: Rubberband stretcher quality (STRETCHER_QUALITY_*).
      :type quality: int
      :arg preserve_formant: Whether to preserve the vocal formants during pitch-shifting.
      :type preserve_formant: bool
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: binaural()
   
      Creates a binaural sound using another sound as source. The original sound must be mono
   
      :arg hrtfs: An HRTF set.
      :type hrtf: :class:`HRTF`
      :arg source: An object representing the source position of the sound.
      :type source: :class:`Source`
      :arg threadPool: A thread pool used to parallelize convolution.
      :type threadPool: :class:`ThreadPool`
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: cache()
   
      Caches a sound into RAM.
   
      This saves CPU usage needed for decoding and file access if the
      underlying sound reads from a file on the harddisk,
      but it consumes a lot of memory.
   
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note:: Only known-length factories can be buffered.
   
      .. warning::
   
         Raw PCM data needs a lot of space, only buffer
         short factories.


   .. method:: convolver()
   
      Creates a sound that will apply convolution to another sound.
   
      :arg impulseResponse: The filter with which convolve the sound.
      :type impulseResponse: :class:`ImpulseResponse`
      :arg threadPool: A thread pool used to parallelize convolution.
      :type threadPool: :class:`ThreadPool`
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: data()
   
      Retrieves the data of the sound as numpy array.
   
      :return: A two dimensional numpy float array.
      :rtype: :class:`numpy.ndarray`
   
      .. note:: Best efficiency with cached sounds.


   .. method:: delay(time)
   
      Delays by playing adding silence in front of the other sound's data.
   
      :arg time: How many seconds of silence should be added before the sound.
      :type time: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: Echo(delay, feedback, mix)
   
      Adds Echo effect to the sound.
   
      :arg delay: The delay time in seconds.
      :type delay: float
      :arg feedback: The feedback amount (0.0 to 1.0).
      :type feedback: float
      :arg mix: The wet/dry mix (0.0 to 1.0).
      :type mix: float
      :arg reset_buffer: Whether to reset the delay buffer on seek.
      :type reset_buffer: bool
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: envelope(attack, release, threshold, arthreshold)
   
      Delays by playing adding silence in front of the other sound's data.
   
      :arg attack: The attack factor.
      :type attack: float
      :arg release: The release factor.
      :type release: float
      :arg threshold: The general threshold value.
      :type threshold: float
      :arg arthreshold: The attack/release threshold value.
      :type arthreshold: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: fadein(start, length)
   
      Fades a sound in by raising the volume linearly in the given
      time interval.
   
      :arg start: Time in seconds when the fading should start.
      :type start: float
      :arg length: Time in seconds how long the fading should last.
      :type length: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note:: Before the fade starts it plays silence.


   .. method:: fadeout(start, length)
   
      Fades a sound in by lowering the volume linearly in the given
      time interval.
   
      :arg start: Time in seconds when the fading should start.
      :type start: float
      :arg length: Time in seconds how long the fading should last.
      :type length: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note::
   
         After the fade this sound plays silence, so that
         the length of the sound is not altered.


   .. method:: filter(b, a = (1,))
   
      Filters a sound with the supplied IIR filter coefficients.
      Without the second parameter you'll get a FIR filter.
   
      If the first value of the a sequence is 0,
      it will be set to 1 automatically.
      If the first value of the a sequence is neither 0 nor 1, all
      filter coefficients will be scaled by this value so that it is 1
      in the end, you don't have to scale yourself.
   
      :arg b: The nominator filter coefficients.
      :type b: sequence of float
      :arg a: The denominator filter coefficients.
      :type a: sequence of float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: highpass(frequency, Q=0.5)
   
      Creates a second order highpass filter based on the transfer
      function :math:`H(s) = s^2 / (s^2 + s/Q + 1)`
   
      :arg frequency: The cut off trequency of the highpass.
      :type frequency: float
      :arg Q: Q factor of the lowpass.
      :type Q: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: join(sound)
   
      Plays two factories in sequence.
   
      :arg sound: The sound to play second.
      :type sound: :class:`Sound`
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note::
   
         The two factories have to have the same specifications
         (channels and samplerate).


   .. method:: limit(start, end)
   
      Limits a sound within a specific start and end time.
   
      :arg start: Start time in seconds.
      :type start: float
      :arg end: End time in seconds.
      :type end: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: loop(count)
   
      Loops a sound.
   
      :arg count: How often the sound should be looped.
         Negative values mean endlessly.
      :type count: integer
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note::
   
         This is a filter function, you might consider using
         :attr:`Handle.loop_count` instead.


   .. method:: lowpass(frequency, Q=0.5)
   
      Creates a second order lowpass filter based on the transfer    function :math:`H(s) = 1 / (s^2 + s/Q + 1)`
   
      :arg frequency: The cut off trequency of the lowpass.
      :type frequency: float
      :arg Q: Q factor of the lowpass.
      :type Q: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: mix(sound)
   
      Mixes two factories.
   
      :arg sound: The sound to mix over the other.
      :type sound: :class:`Sound`
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note::
   
         The two factories have to have the same specifications
         (channels and samplerate).


   .. method:: modulate(sound)
   
      Modulates two factories.
   
      :arg sound: The sound to modulate over the other.
      :type sound: :class:`Sound`
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note::
   
         The two factories have to have the same specifications
         (channels and samplerate).


   .. method:: mutable()
   
      Creates a sound that will be restarted when sought backwards.
      If the original sound is a sound list, the playing sound can change.
   
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: pingpong()
   
      Plays a sound forward and then backward.
      This is like joining a sound with its reverse.
   
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: pitch(factor)
   
      Changes the pitch of a sound with a specific factor.
   
      :arg factor: The factor to change the pitch with.
      :type factor: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note::
   
         This is done by changing the sample rate of the
         underlying sound, which has to be an integer, so the factor
         value rounded and the factor may not be 100 % accurate.
   
      .. note::
   
         This is a filter function, you might consider using
         :attr:`Handle.pitch` instead.


   .. method:: rechannel(channels)
   
      Rechannels the sound.
   
      :arg channels: The new channel configuration.
      :type channels: int
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: resample(rate, quality)
   
      Resamples the sound.
   
      :arg rate: The new sample rate.
      :type rate: double
      :arg quality: Resampler performance vs quality choice (0=fastest, 3=slowest).
      :type quality: int
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: reverse()
   
      Plays a sound reversed.
   
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note::
   
         The sound has to have a finite length and has to be seekable.
         It's recommended to use this only with factories with
         fast and accurate seeking, which is not true for encoded audio
         files, such ones should be buffered using :meth:`cache` before
         being played reversed.
   
      .. warning::
   
         If seeking is not accurate in the underlying sound
         you'll likely hear skips/jumps/cracks.


   .. method:: sum()
   
      Sums the samples of a sound.
   
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: threshold(threshold = 0)
   
      Makes a threshold wave out of an audio wave by setting all samples
      with a amplitude >= threshold to 1, all <= -threshold to -1 and
      all between to 0.
   
      :arg threshold: Threshold value over which an amplitude counts
         non-zero.
   
      :type threshold: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: timeStretchPitchScale(time_stretch, pitch_scale, quality, preserve_formant)
   
      Applies time-stretching and pitch-scaling to the sound.
   
      :arg time_stretch: The factor by which to stretch or compress time.
      :type time_stretch: float
      :arg pitch_scale: The factor by which to adjust the pitch.
      :type pitch_scale: float
      :arg quality: Rubberband stretcher quality (STRETCHER_QUALITY_*).
      :type quality: int
      :arg preserve_formant: Whether to preserve the vocal formants during pitch-shifting.
      :type preserve_formant: bool
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`


   .. method:: volume(volume)
   
      Changes the volume of a sound.
   
      :arg volume: The new volume..
      :type volume: float
      :return: The created :class:`Sound` object.
      :rtype: :class:`Sound`
   
      .. note::
   
         Should be in the range [0, 1] to avoid clipping.
   
      .. note::
   
         This is a filter function, you might consider using
         :attr:`Handle.volume` instead.


   .. method:: write(filename, rate, channels, format, container, codec, bitrate, buffersize)
   
      Writes the sound to a file.
   
      :arg filename: The path to write to.
      :type filename: string
      :arg rate: The sample rate to write with.
      :type rate: int
      :arg channels: The number of channels to write with.
      :type channels: int
      :arg format: The sample format to write with.
      :type format: int
      :arg container: The container format for the file.
      :type container: int
      :arg codec: The codec to use in the file.
      :type codec: int
      :arg bitrate: The bitrate to write with.
      :type bitrate: int
      :arg buffersize: The size of the writing buffer.
      :type buffersize: int


   .. attribute:: length

      The sample specification of the sound as a tuple with rate and channel count.


   .. attribute:: specs

      The sample specification of the sound as a tuple with rate and channel count.




.. class:: Source(azimuth, elevation, distance, /)

   The source object represents the source position of a binaural sound.

   :arg azimuth: The azimuth angle in degrees.
   :type azimuth: float
   :arg elevation: The elevation angle in degrees.
   :type elevation: float
   :arg distance: The distance of the source.
   :type distance: float

   .. attribute:: azimuth

      The azimuth angle.


   .. attribute:: distance

      The distance value. 0 is min, 1 is max.


   .. attribute:: elevation

      The elevation angle.




.. class:: ThreadPool(nThreads, /)

   A ThreadPool is used to parallelize convolution efficiently.

   :arg nThreads: The number of threads in the pool.
   :type nThreads: int



.. class:: error




