ThemeMixieChat(bpy_struct)
==========================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: ThemeMixieChat(bpy_struct)

   Theme settings for Lampway Chat

   .. attribute:: chat_action_button_corner_radius

      Corner radius for action buttons (in [0, 16], default 4.0)

      :type: float

   .. attribute:: chat_action_button_height

      Height of action buttons (in [16, 48], default 24.0)

      :type: float

   .. attribute:: chat_action_button_padding

      Padding inside action buttons (in [0, 32], default 8.0)

      :type: float

   .. attribute:: chat_action_button_spacing

      Spacing between action buttons (in [0, 16], default 6.0)

      :type: float

   .. attribute:: chat_agent_bubble

      Background color for agent message bubbles (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_agent_text

      Text color for agent messages (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_attach_button_size

      Size of the attachment button (paperclip) icon (in [16, 128], default 40.0)

      :type: float

   .. attribute:: chat_bubble_h_padding

      Horizontal padding inside message bubbles (in [0, 64], default 16.0)

      :type: float

   .. attribute:: chat_bubble_hover

      Background color when hovering over interactive bubbles (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_bubble_spacing

      Vertical spacing between message bubbles (in [0, 64], default 14.0)

      :type: float

   .. attribute:: chat_bubble_v_padding

      Vertical padding inside message bubbles (in [0, 64], default 14.0)

      :type: float

   .. attribute:: chat_button_bg

      Background color for chat buttons (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_button_hover

      Color for footer buttons on hover (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_button_text

      Text color for chat buttons (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_corner_radius

      Corner radius for chat UI elements (in [0, 32], default 8.0)

      :type: float

   .. attribute:: chat_font_size

      Font size for chat messages (in [8, 32], default 14.0)

      :type: float

   .. attribute:: chat_footer_bottom_padding

      Padding below the input row in the footer (in pixels) (in [0, 20], default 6)

      :type: int

   .. attribute:: chat_footer_button_row_height

      Height of the footer button row (in [8, 128], default 44.0)

      :type: float

   .. attribute:: chat_footer_general_padding

      General padding for footer elements (in [0, 32], default 6.0)

      :type: float

   .. attribute:: chat_footer_input_height

      Height of the multi-line text input field (in [20, 400], default 60.0)

      :type: float

   .. attribute:: chat_footer_row_spacing

      Vertical spacing between footer rows (in [0, 32], default 2.0)

      :type: float

   .. attribute:: chat_footer_side_padding

      Left and right padding for footer (in [0, 64], default 8.0)

      :type: float

   .. attribute:: chat_footer_thumbnail_size

      Size of attachment thumbnails (in [32, 128], default 48.0)

      :type: float

   .. attribute:: chat_footer_thumbnail_spacing

      Spacing between attachment thumbnails (in [0, 32], default 6.0)

      :type: float

   .. attribute:: chat_footer_thumbnail_top_margin

      Vertical margin above attachment thumbnails (in [0, 32], default 8.0)

      :type: float

   .. attribute:: chat_footer_top_padding

      Padding above input field when no thumbnails are present (in [0, 32], default 6.0)

      :type: float

   .. attribute:: chat_history_row_hover

      Hover wash behind rows in the past-chats overlay (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_image_corner_radius

      Corner radius for images in chat bubbles (in [0, 32], default 12.0)

      :type: float

   .. attribute:: chat_image_margin

      Margin around chat images (in [0, 32], default 8.0)

      :type: float

   .. attribute:: chat_image_max_height

      Maximum height for chat images (in [100, 600], default 180.0)

      :type: float

   .. attribute:: chat_image_max_width

      Maximum width for chat images (in [100, 800], default 240.0)

      :type: float

   .. attribute:: chat_input_bg

      Background color for the chat input field (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_label_color

      Color for chat labels and secondary text (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_label_font_size

      Font size for chat labels (in [6, 24], default 11.0)

      :type: float

   .. attribute:: chat_label_height

      Height of chat labels (in [12, 64], default 24.0)

      :type: float

   .. attribute:: chat_main_footer_gap

      Internal spacing above the input field inside the footer (in [0, 64], default 16.0)

      :type: float

   .. attribute:: chat_mode_button

      Background color for mode selection buttons (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_mode_button_active

      Background color for the active mode button (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_padding

      General padding for chat interface (in [0, 64], default 16.0)

      :type: float

   .. attribute:: chat_placeholder_text

      Color for placeholder text in input fields (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_plan_toggle_on

      Track color for the plan mode toggle when enabled (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_prompt_button

      Background color for prompt suggestion buttons (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_send_arrow_color

      Color of the arrow shape in the send button icon (array of 4 items, in [0, 1], default (0.054902, 0.0627451, 0.0862745, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_send_button_size

      Size of the send button icon (in [16, 128], default 40.0)

      :type: float

   .. attribute:: chat_send_icon_gradient_end

      End color for the send button icon gradient (bottom-right) (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_send_icon_gradient_start

      Start color for the send button icon gradient (top-left) (array of 4 items, in [0, 1], default (0.929412, 0.72549, 0.266667, 1.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_thumbnail_border

      Border color for image thumbnails (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_thumbnail_border_radius

      Border radius for image thumbnail previews (in [0, 32], default 8.0)

      :type: float

   .. attribute:: chat_thumbnail_padding

      Padding inside image thumbnail previews (in [0, 16], default 4.0)

      :type: float

   .. attribute:: chat_user_bubble

      Background color for user message bubbles (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. attribute:: chat_user_text

      Text color for user messages (array of 4 items, in [0, 1], default (0.0, 0.0, 0.0, 0.0))

      :type: :class:`bpy_prop_array`\ [float]

   .. data:: space

      Settings for space (readonly, never None)

      :type: :class:`ThemeSpaceGeneric`

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

   - :class:`Theme.mixie_chat`

