Mixie Chat Operators
====================

.. module:: bpy.ops.mixie_chat

.. function:: agent_bubble_show()

   Open the floating agent bubble overlay that lets the user chat with the AI agent from anywhere in the Lampway interface

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: copy()

   Copy selected chat text to clipboard

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: drop_asset_pick(*, value="")

   Place the dragged library asset where it is dropped and answer the agent with it

   :param value: Pick, Action value of the dropped pick (optional, never None)
   :type value: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: drop_image(*, filepath="", files=None, image_name="")

   Add a dropped image as a chat attachment

   :param filepath: File Path, Path to image file (optional, never None)
   :type filepath: str
   :param files: Files, Dropped paths (optional)
   :type files: :class:`bpy_prop_collection`\ [:class:`OperatorFileListElement`] | None
   :param image_name: Image, Dropped image datablock (optional, never None)
   :type image_name: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: focus_composer()

   Resume editing the visible chat draft after voice transcription

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: ink_flush()

   Convert any pending handwritten strokes on the scribble canvas now

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: ink_local_poll()

   Move one finished on-device recognition result into the window-manager properties

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: ink_recognize_local(*, job=0, image_path="")

   Start on-device recognition of one rasterized ink batch

   :param job: Job, Batch id echoed back with the result (in [0, inf], optional)
   :type job: int
   :param image_path: Image Path, PNG of the ink batch (dark strokes on a light page) (optional, never None)
   :type image_path: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: ink_release_composer()

   Exit any active chat composer text edit so recognized handwriting can append safely

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: lightbox(*, bubble_id="", index=0)

   Show an agent capture large over the whole window

   :param bubble_id: Bubble ID, (optional, never None)
   :type bubble_id: str
   :param index: Index, slot_images index of the tile (in [0, inf], optional)
   :type index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: retitle_document(*, filepath="")

   Give the open document a file path (or none) without writing anything to disk; used by the turn checkpoint restore

   :param filepath: File Path, The document's path; empty leaves it untitled (optional, never None)
   :type filepath: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: select_text()

   Select text in chat message by clicking and dragging

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: undo_stamp()

   Write a fingerprint of the undo stack to WindowManager.mixie_chat_undo_stamp; used by the turn checkpoints to tell whether the document changed

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: voice_poll()

   Move one speech recogniser event into the window-manager properties

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: voice_start()

   Start dictating into the chat composer

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: voice_stop()

   Stop dictating

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
