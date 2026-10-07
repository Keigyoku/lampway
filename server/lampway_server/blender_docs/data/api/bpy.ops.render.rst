Render Operators
================

.. module:: bpy.ops.render

.. function:: clear_texture_cache()

   Delete Cycles texture cache files from disk

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: color_management_white_balance_preset_add(*, name="", remove_name=False, remove_active=False)

   Add or remove a white balance preset

   :param name: Name, Name of the preset, used to make the path name (optional, never None)
   :type name: str
   :param remove_name: remove_name, (optional)
   :type remove_name: bool
   :param remove_active: remove_active, (optional)
   :type remove_active: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/presets.py\:119 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/presets.py#L119>`__


.. function:: cycles_integrator_preset_add(*, name="", remove_name=False, remove_active=False)

   Add an Integrator Preset

   :param name: Name, Name of the preset, used to make the path name (optional, never None)
   :type name: str
   :param remove_name: remove_name, (optional)
   :type remove_name: bool
   :param remove_active: remove_active, (optional)
   :type remove_active: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/presets.py\:119 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/presets.py#L119>`__


.. function:: cycles_performance_preset_add(*, name="", remove_name=False, remove_active=False)

   Add an Performance Preset

   :param name: Name, Name of the preset, used to make the path name (optional, never None)
   :type name: str
   :param remove_name: remove_name, (optional)
   :type remove_name: bool
   :param remove_active: remove_active, (optional)
   :type remove_active: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/presets.py\:119 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/presets.py#L119>`__


.. function:: cycles_sampling_preset_add(*, name="", remove_name=False, remove_active=False)

   Add a Sampling Preset

   :param name: Name, Name of the preset, used to make the path name (optional, never None)
   :type name: str
   :param remove_name: remove_name, (optional)
   :type remove_name: bool
   :param remove_active: remove_active, (optional)
   :type remove_active: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/presets.py\:119 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/presets.py#L119>`__


.. function:: cycles_viewport_sampling_preset_add(*, name="", remove_name=False, remove_active=False)

   Add a Viewport Sampling Preset

   :param name: Name, Name of the preset, used to make the path name (optional, never None)
   :type name: str
   :param remove_name: remove_name, (optional)
   :type remove_name: bool
   :param remove_active: remove_active, (optional)
   :type remove_active: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/presets.py\:119 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/presets.py#L119>`__


.. function:: eevee_raytracing_preset_add(*, name="", remove_name=False, remove_active=False)

   Add or remove an EEVEE ray-tracing preset

   :param name: Name, Name of the preset, used to make the path name (optional, never None)
   :type name: str
   :param remove_name: remove_name, (optional)
   :type remove_name: bool
   :param remove_active: remove_active, (optional)
   :type remove_active: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/presets.py\:119 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/presets.py#L119>`__


.. function:: generate_texture_cache(*, generate_sequences=True)

   Generate Cycles texture cache files for all images used in shader nodes

   :param generate_sequences: Image Sequences, Generate texture cache files for all frames of image sequences (optional)
   :type generate_sequences: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: opengl(*, animation=False, render_keyed_only=False, sequencer=False, write_still=False, view_context=True)

   Take a snapshot of the active viewport

   :param animation: Animation, Render files from the animation range of this scene (optional)
   :type animation: bool
   :param render_keyed_only: Render Keyframes Only, Render only those frames where selected objects have a key in their animation data. Only used when rendering animation (optional)
   :type render_keyed_only: bool
   :param sequencer: Sequencer, Render using the sequencer's OpenGL display (optional)
   :type sequencer: bool
   :param write_still: Write Image, Save the rendered image to the output path (used only when animation is disabled) (optional)
   :type write_still: bool
   :param view_context: View Context, Use the current 3D view for rendering, else use scene settings (optional)
   :type view_context: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: play_rendered_anim()

   Play back rendered frames/movies using an external player

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/screen_play_rendered_anim.py\:137 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/screen_play_rendered_anim.py#L137>`__

.. function:: preset_add(*, name="", remove_name=False, remove_active=False)

   Add or remove a Render Preset

   :param name: Name, Name of the preset, used to make the path name (optional, never None)
   :type name: str
   :param remove_name: remove_name, (optional)
   :type remove_name: bool
   :param remove_active: remove_active, (optional)
   :type remove_active: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/presets.py\:119 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/presets.py#L119>`__


.. function:: render(*, animation=False, write_still=False, use_viewport=False, use_sequencer_scene=False, layer="", scene="", frame_start=0, frame_end=0)

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :param animation: Animation, Render files from the animation range of this scene (optional)
   :type animation: bool
   :param write_still: Write Image, Save the rendered image to the output path (used only when animation is disabled) (optional)
   :type write_still: bool
   :param use_viewport: Use 3D Viewport, When inside a 3D viewport, use layers and camera of the viewport (optional)
   :type use_viewport: bool
   :param use_sequencer_scene: Use Sequencer Scene, Render the sequencer scene instead of the active scene (optional)
   :type use_sequencer_scene: bool
   :param layer: Render Layer, Single render layer to re-render (used only when animation is disabled) (optional, never None)
   :type layer: str
   :param scene: Scene, Scene to render, current scene if not specified (optional, never None)
   :type scene: str
   :param frame_start: Start Frame, Frame to start rendering animation at. If not specified, the scene start frame will be assumed. This should only be specified if doing an animation render (in [-inf, inf], optional)
   :type frame_start: int
   :param frame_end: End Frame, Frame to end rendering animation at. If not specified, the scene end frame will be assumed. This should only be specified if doing an animation render (in [-inf, inf], optional)
   :type frame_end: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: shutter_curve_preset(*, shape='SMOOTH')

   Set shutter curve

   :param shape: Mode, (optional)
   :type shape: Literal['SHARP', 'SMOOTH', 'MAX', 'LINE', 'ROUND', 'ROOT']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: swap_dimensions()

   Flip X and Y resolutions

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/render.py\:14 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/render.py#L14>`__

.. function:: view_cancel()

   Cancel showing the render view

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: view_show()

   Toggle show render view

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
