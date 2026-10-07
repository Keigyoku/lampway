Mixar Operators
===============

.. module:: bpy.ops.mixar

.. function:: agent_bubble_drag_history()

   Toggle the chat history pane open or closed

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/agent_bubble/ui/operators/bubble_history_ops.py\:43 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/agent_bubble/ui/operators/bubble_history_ops.py#L43>`__

.. function:: agent_bubble_open_window()

   Open the Agent Bubble in its own floating window

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/agent_bubble/ui/operators/window_ops.py\:48 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/agent_bubble/ui/operators/window_ops.py#L48>`__

.. function:: agent_bubble_purge_windows(*, closed_count=0)

   Close all transient Agent Bubble overlay windows

   :param closed_count: Closed Count, Number of Agent Bubble windows closed (in [0, inf], optional)
   :type closed_count: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: agent_bubble_show_window(*, start_minimised=False)

   Open the Agent Bubble chat in a small floating Blender window

   :param start_minimised: Start Minimised, Open with the full bubble window hidden and only the status pill visible at the centre-bottom (optional)
   :type start_minimised: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: bubble_block_context_menu()

   Block Context Menu

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/agent_bubble/ui/operators/bubble_close_op.py\:323 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/agent_bubble/ui/operators/bubble_close_op.py#L323>`__

.. function:: bubble_close()

   Minimise

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/agent_bubble/ui/operators/bubble_close_op.py\:134 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/agent_bubble/ui/operators/bubble_close_op.py#L134>`__

.. function:: bubble_header_drag()

   Drag the Agent Bubble window to move it across the screen.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/agent_bubble/ui/operators/bubble_header_drag_op.py\:103 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/agent_bubble/ui/operators/bubble_header_drag_op.py#L103>`__

.. function:: bubble_hover_tick()

   Maintain island focus, Scribble and animation

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: bubble_minimise()

   Minimise

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: bubble_pill_voice()

   Start or stop dictating into the sketch draft

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: bubble_restore()

   Restore

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: bubble_restore_user()

   Restore

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/agent_bubble/ui/operators/bubble_close_op.py\:182 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/agent_bubble/ui/operators/bubble_close_op.py#L182>`__

.. function:: bubble_set_bg_color(*, r=0.0, g=0.0, b=0.0, a=1.0)

   Set the background colour (RGBA) of the Agent Bubble window

   :param r: Red, (in [0, 1], optional)
   :type r: float
   :param g: Green, (in [0, 1], optional)
   :type g: float
   :param b: Blue, (in [0, 1], optional)
   :type b: float
   :param a: Alpha, (in [0, 1], optional)
   :type a: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: bubble_set_size(*, width=678, height=230)

   Internal: resize the Agent Bubble floating window

   :param width: Width, Target window width in Blender pixels (in [100, 4000], optional)
   :type width: int
   :param height: Height, Target window height in Blender pixels (in [100, 4000], optional)
   :type height: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: bubble_sync_attachment_size(*, force_attachment_height=False)

   Internal: sync Agent Bubble size with pending image attachments

   :param force_attachment_height: Force Attachment Height, Force the visible bubble to the attachment collapsed height (optional)
   :type force_attachment_height: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: bubble_tab_locked()

   Tabs stay on this one while sketching or dictating

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: bubble_toggle_expand()

   Expand

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: bubble_toggle_expand_tracked()

   Python bridge for the native expand toggle so the user action is visible.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/agent_bubble/ui/operators/bubble_close_op.py\:294 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/agent_bubble/ui/operators/bubble_close_op.py#L294>`__

.. function:: bubble_toggle_minimise()

   Minimise the Agent Bubble to its pill, or restore it

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/agent_bubble/ui/operators/bubble_close_op.py\:227 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/agent_bubble/ui/operators/bubble_close_op.py#L227>`__

.. function:: bubble_window_begin_drag()

   Internal: start Agent Bubble window drag

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: bubble_window_end_drag()

   Internal: end Agent Bubble window drag

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: bubble_window_update_drag()

   Internal: update Agent Bubble window position during drag

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: credits_banner(*, image_path="")

   Show the out-of-credits banner over the whole window

   :param image_path: Image, Banner art to draw (optional, never None)
   :type image_path: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: director_nudge_camera(*, direction='FORWARD')

   Move the shot camera walk-style while the key is held

   :param direction: Direction, Direction the first press moves the camera in (optional)

      - ``FORWARD``
        Forward -- Move the camera along its view direction.
      - ``BACK``
        Back -- Move the camera against its view direction.
      - ``LEFT``
        Left -- Strafe the camera left.
      - ``RIGHT``
        Right -- Strafe the camera right.
      - ``UP``
        Up -- Raise the camera along the world Z axis.
      - ``DOWN``
        Down -- Lower the camera along the world Z axis.
   :type direction: Literal['FORWARD', 'BACK', 'LEFT', 'RIGHT', 'UP', 'DOWN']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: director_place_camera()

   Move the shot camera to the point under the cursor on the aerial map or, in the aerial view, in the stage, keeping its height and aim

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: director_scroll_cameras(*, delta=1)

   Scroll the My Cameras list

   :param delta: Delta, Rows to scroll (in [-16, 16], optional)
   :type delta: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: director_walk()

   Drive the shot camera: W A S D to move, Q E for height, Shift to sprint, Alt to creep, hold the left mouse button to look. The Walk button starts and stops it

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: generations_navigate(*, action='STEP', delta=1.0)

   Scroll Library assets or connected libraries under the pointer

   :param action: Action, (optional)

      - ``STEP``
        Scroll -- Scroll library content.
      - ``PAGE``
        Page -- Move by the viewport height.
      - ``FIRST``
        First -- Show the first items.
      - ``LAST``
        Last -- Show the last items.
   :type action: Literal['STEP', 'PAGE', 'FIRST', 'LAST']
   :param delta: Rows, (in [-10000, 10000], optional)
   :type delta: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: preview_sketch(*, image_name="")

   Open the completed drawing in a larger preview. Close it to return to chat

   :param image_name: Sketch, Image to preview (optional, never None)
   :type image_name: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: queue_navigate(*, action='STEP', delta=1.0)

   Browse generation jobs in the island Queue

   :param action: Action, (optional)

      - ``STEP``
        Scroll -- Scroll queue rows.
      - ``PAGE``
        Page -- Move by the visible row count.
      - ``FIRST``
        First -- Show newest jobs.
      - ``LAST``
        Last -- Show oldest jobs.
   :type action: Literal['STEP', 'PAGE', 'FIRST', 'LAST']
   :param delta: Rows, (in [-10000, 10000], optional)
   :type delta: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: reference_scroll(*, delta=1.0)

   Browse attached reference images

   :param delta: Distance, (in [-10000, 10000], optional)
   :type delta: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: set_ui_mode_ai()

   Switch Lampway into Lamplight (minimal viewport + Agent Bubble + moodboard)

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/workflow/ui/operators/ui_mode_ops.py\:181 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/workflow/ui/operators/ui_mode_ops.py#L181>`__

.. function:: set_ui_mode_pro()

   Switch Lampway into the Workshop (full Blender-style workspaces)

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `mixar/modules/workflow/ui/operators/ui_mode_ops.py\:228 <https://projects.blender.org/blender/blender/src/branch/main/scripts/mixar/modules/workflow/ui/operators/ui_mode_ops.py#L228>`__

