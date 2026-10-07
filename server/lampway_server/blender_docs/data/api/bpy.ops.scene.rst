Scene Operators
===============

.. module:: bpy.ops.scene

.. function:: delete()

   Delete active scene

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: drop_scene_asset(*, session_uid=0)

   Import scene and set it as the active one in the window

   :param session_uid: Session UID, Session UID of the data-block to use by the operator (in [-inf, inf], optional)
   :type session_uid: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: freestyle_add_edge_marks_to_keying_set()

   Add the data paths to the Freestyle Edge Mark property of selected edges to the active keying set

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/freestyle.py\:139 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/freestyle.py#L139>`__

.. function:: freestyle_add_face_marks_to_keying_set()

   Add the data paths to the Freestyle Face Mark property of selected polygons to the active keying set

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/freestyle.py\:170 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/freestyle.py#L170>`__

.. function:: freestyle_alpha_modifier_add(*, type='ALONG_STROKE')

   Add an alpha transparency modifier to the line style associated with the active lineset

   :param type: Type, (optional)
   :type type: Literal[:ref:`rna_enum_linestyle_alpha_modifier_type_items`]
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: freestyle_color_modifier_add(*, type='ALONG_STROKE')

   Add a line color modifier to the line style associated with the active lineset

   :param type: Type, (optional)
   :type type: Literal[:ref:`rna_enum_linestyle_color_modifier_type_items`]
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: freestyle_fill_range_by_selection(*, type='COLOR', name="")

   Fill the Range Min/Max entries by the min/max distance between selected mesh objects and the source object (either a user-specified object or the active camera)

   :param type: Type, Type of the modifier to work on (optional)

      - ``COLOR``
        Color -- Color modifier type.
      - ``ALPHA``
        Alpha -- Alpha modifier type.
      - ``THICKNESS``
        Thickness -- Thickness modifier type.
   :type type: Literal['COLOR', 'ALPHA', 'THICKNESS']
   :param name: Name, Name of the modifier to work on (optional, never None)
   :type name: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/freestyle.py\:45 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/freestyle.py#L45>`__


.. function:: freestyle_geometry_modifier_add(*, type='2D_OFFSET')

   Add a stroke geometry modifier to the line style associated with the active lineset

   :param type: Type, (optional)
   :type type: Literal[:ref:`rna_enum_linestyle_geometry_modifier_type_items`]
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: freestyle_lineset_add()

   Add a line set into the list of line sets

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_lineset_copy()

   Copy the active line set to the internal clipboard

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_lineset_move(*, direction='UP')

   Change the position of the active line set within the list of line sets

   :param direction: Direction, Direction to move the active line set towards (optional)
   :type direction: Literal['UP', 'DOWN']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: freestyle_lineset_paste()

   Paste the internal clipboard content to the active line set

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_lineset_remove()

   Remove the active line set from the list of line sets

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_linestyle_new()

   Create a new line style, reusable by multiple line sets

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_modifier_copy()

   Duplicate the modifier within the list of modifiers

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_modifier_move(*, direction='UP')

   Move the modifier within the list of modifiers

   :param direction: Direction, Direction to move the chosen modifier towards (optional)
   :type direction: Literal['UP', 'DOWN']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: freestyle_modifier_remove()

   Remove the modifier from the list of modifiers

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_module_add()

   Add a style module into the list of modules

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_module_move(*, direction='UP')

   Change the position of the style module within in the list of style modules

   :param direction: Direction, Direction to move the chosen style module towards (optional)
   :type direction: Literal['UP', 'DOWN']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: freestyle_module_open(*, filepath="", make_internal=True)

   Open a style module file

   :param filepath: filepath, (optional, never None)
   :type filepath: str
   :param make_internal: Make internal, Make module file internal after loading (optional)
   :type make_internal: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/freestyle.py\:215 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/freestyle.py#L215>`__


.. function:: freestyle_module_remove()

   Remove the style module from the stack

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_stroke_material_create()

   Create Freestyle stroke material for testing

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: freestyle_thickness_modifier_add(*, type='ALONG_STROKE')

   Add a line thickness modifier to the line style associated with the active lineset

   :param type: Type, (optional)
   :type type: Literal[:ref:`rna_enum_linestyle_thickness_modifier_type_items`]
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: gltf2_action_filter_refresh()

   Refresh list of actions

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/io_scene_gltf2/blender/com/gltf2_blender_ui.py\:681 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/io_scene_gltf2/blender/com/gltf2_blender_ui.py#L681>`__

.. function:: gpencil_brush_preset_add(*, name="", remove_name=False, remove_active=False)

   Add or remove Grease Pencil brush preset

   :param name: Name, Name of the preset, used to make the path name (optional, never None)
   :type name: str
   :param remove_name: remove_name, (optional)
   :type remove_name: bool
   :param remove_active: remove_active, (optional)
   :type remove_active: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/presets.py\:119 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/presets.py#L119>`__


.. function:: gpencil_material_preset_add(*, name="", remove_name=False, remove_active=False)

   Add or remove Grease Pencil material preset

   :param name: Name, Name of the preset, used to make the path name (optional, never None)
   :type name: str
   :param remove_name: remove_name, (optional)
   :type remove_name: bool
   :param remove_active: remove_active, (optional)
   :type remove_active: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `startup/bl_operators/presets.py\:119 <https://projects.blender.org/blender/blender/src/branch/main/scripts/startup/bl_operators/presets.py#L119>`__


.. function:: new(*, type='NEW')

   Add new scene by type

   :param type: Type, (optional)

      - ``NEW``
        New -- Add a new, empty scene with default settings.
      - ``EMPTY``
        Copy Settings -- Add a new, empty scene, and copy settings from the current scene.
      - ``LINK_COPY``
        Linked Copy -- Link in the collections from the current scene (shallow copy).
      - ``FULL_COPY``
        Full Copy -- Make a full copy of the current scene.
   :type type: Literal['NEW', 'EMPTY', 'LINK_COPY', 'FULL_COPY']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: new_sequencer(*, type='NEW')

   Add new scene by type in the sequence editor and assign to active strip

   :param type: Type, (optional)

      - ``NEW``
        New -- Add a new, empty scene with default settings.
      - ``EMPTY``
        Copy Settings -- Add a new, empty scene, and copy settings from the current scene.
      - ``LINK_COPY``
        Linked Copy -- Link in the collections from the current scene (shallow copy).
      - ``FULL_COPY``
        Full Copy -- Make a full copy of the current scene.
   :type type: Literal['NEW', 'EMPTY', 'LINK_COPY', 'FULL_COPY']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: new_sequencer_scene(*, type='NEW')

   Add new scene to be used by the sequencer

   :param type: Type, (optional)

      - ``NEW``
        New -- Add a new, empty scene with default settings.
      - ``EMPTY``
        Copy Settings -- Add a new, empty scene, and copy settings from the current scene.
      - ``LINK_COPY``
        Linked Copy -- Link in the collections from the current scene (shallow copy).
      - ``FULL_COPY``
        Full Copy -- Make a full copy of the current scene.
   :type type: Literal['NEW', 'EMPTY', 'LINK_COPY', 'FULL_COPY']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: render_view_add()

   Add a render view

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: render_view_remove()

   Remove the selected render view

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: view_layer_add(*, type='NEW')

   Add a view layer

   :param type: Type, (optional)

      - ``NEW``
        New -- Add a new view layer.
      - ``COPY``
        Copy Settings -- Copy settings of current view layer.
      - ``EMPTY``
        Blank -- Add a new view layer with all collections disabled.
   :type type: Literal['NEW', 'COPY', 'EMPTY']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: view_layer_add_aov()

   Add a Shader AOV

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: view_layer_add_lightgroup(*, name="")

   Add a Light Group

   :param name: Name, Name of newly created lightgroup (optional, never None)
   :type name: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: view_layer_add_used_lightgroups()

   Add all used Light Groups

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: view_layer_remove()

   Remove the selected view layer

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: view_layer_remove_aov()

   Remove Active AOV

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: view_layer_remove_lightgroup()

   Remove Active Lightgroup

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: view_layer_remove_unused_lightgroups()

   Remove all unused Light Groups

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
