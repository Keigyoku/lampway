Mixie Operators
===============

.. module:: bpy.ops.mixie

.. function:: moodboard_attachment_flight(*, image_name="", delay=0.0)

   Show a newly attached reference flying into Lampway Chat

   :param image_name: Image, (optional, never None)
   :type image_name: str
   :param delay: Delay, (in [0, 0.3], optional)
   :type delay: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_box_select(*, xmin=0, xmax=0, ymin=0, ymax=0, wait_for_input=True, mode='SET')

   Select multiple moodboard items using box selection

   :param xmin: X Min, (in [-inf, inf], optional)
   :type xmin: int
   :param xmax: X Max, (in [-inf, inf], optional)
   :type xmax: int
   :param ymin: Y Min, (in [-inf, inf], optional)
   :type ymin: int
   :param ymax: Y Max, (in [-inf, inf], optional)
   :type ymax: int
   :param wait_for_input: Wait for Input, (optional)
   :type wait_for_input: bool
   :param mode: Mode, (optional)

      - ``SET``
        Set -- Set a new selection.
      - ``ADD``
        Extend -- Extend existing selection.
      - ``SUB``
        Subtract -- Subtract existing selection.
   :type mode: Literal['SET', 'ADD', 'SUB']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_context_menu()

   Resolve the node under the pointer and open its context menu

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: moodboard_crop_image(*, image_index=-1, x1=0.0, y1=0.0, x2=1.0, y2=1.0)

   Crop an image in the moodboard (C++ accelerated)

   :param image_index: Image Index, Index of the source image in moodboard (in [-1, inf], optional)
   :type image_index: int
   :param x1: X1, Crop start X (normalized 0-1) (in [0, 1], optional)
   :type x1: float
   :param y1: Y1, Crop start Y (normalized 0-1) (in [0, 1], optional)
   :type y1: float
   :param x2: X2, Crop end X (normalized 0-1) (in [0, 1], optional)
   :type x2: float
   :param y2: Y2, Crop end Y (normalized 0-1) (in [0, 1], optional)
   :type y2: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_drop_image(*, filepath="", image_name="", multi_filepaths="", files=None, position_x=0.0, position_y=0.0, from_drop=False, center_on_drop=False)

   Add an image or video to the moodboard at the drop position

   :param filepath: File Path, Path to image or video file (optional, never None)
   :type filepath: str
   :param image_name: Image Name, Name of existing image datablock (optional, never None)
   :type image_name: str
   :param multi_filepaths: Multi File Paths, Pipe-separated list of file paths for multi-file drops (optional, never None)
   :type multi_filepaths: str
   :param files: Files, Dropped paths (optional)
   :type files: :class:`bpy_prop_collection`\ [:class:`OperatorFileListElement`] | None
   :param position_x: Position X, X position on the moodboard canvas (in [-inf, inf], optional)
   :type position_x: float
   :param position_y: Position Y, Y position on the moodboard canvas (in [-inf, inf], optional)
   :type position_y: float
   :param from_drop: From Drop, Whether this was invoked from a drag-drop operation (optional)
   :type from_drop: bool
   :param center_on_drop: Center, Center viewport references in the drawer (optional)
   :type center_on_drop: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_drop_template(*, template_label="")

   Place an editable node where the template is dropped

   :param template_label: Template, Template to place (optional, never None)
   :type template_label: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_ensure_visible(*, x=0.0, y=0.0, width=0.0, height=0.0, margin=50.0)

   Zoom the moodboard out if needed so a canvas region is visible

   :param x: X, Target rect left edge (canvas) (in [-1e+07, 1e+07], optional)
   :type x: float
   :param y: Y, Target rect bottom edge (canvas) (in [-1e+07, 1e+07], optional)
   :type y: float
   :param width: Width, Target rect width (canvas) (in [0, 1e+07], optional)
   :type width: float
   :param height: Height, Target rect height (canvas) (in [0, 1e+07], optional)
   :type height: float
   :param margin: Margin, Extra canvas margin to keep around the rect (in [0, 1e+07], optional)
   :type margin: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_frame(*, selected_only=False)

   Fit the view to the whole board, or to the selection

   :param selected_only: Selected Only, Frame just the selected items (optional)
   :type selected_only: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_frame_select(*, extend=False)

   Select a frame by its border or title strip and drag it with its contents

   :param extend: Extend, Toggle this frame in the existing selection instead of replacing it (optional)
   :type extend: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_generate_box_mask(*, image_index=-1, x1=0.0, y1=0.0, x2=1.0, y2=1.0, invert=False, offset_x=750.0)

   Generate a black and white box mask image (C++ accelerated)

   :param image_index: Image Index, Index of the source image in moodboard (in [-1, inf], optional)
   :type image_index: int
   :param x1: X1, Box start X (normalized 0-1) (in [0, 1], optional)
   :type x1: float
   :param y1: Y1, Box start Y (normalized 0-1) (in [0, 1], optional)
   :type y1: float
   :param x2: X2, Box end X (normalized 0-1) (in [0, 1], optional)
   :type x2: float
   :param y2: Y2, Box end Y (normalized 0-1) (in [0, 1], optional)
   :type y2: float
   :param invert: Invert, Invert the mask (optional)
   :type invert: bool
   :param offset_x: Offset X, X offset for placing the mask image (in [-inf, inf], optional)
   :type offset_x: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_generate_lasso_mask(*, image_index=-1, invert=False, offset_x=750.0)

   Generate a black and white lasso mask image (C++ accelerated). Reads points from scene.mixie_edit_tool_state.lasso_points

   :param image_index: Image Index, Index of the source image in moodboard (in [-1, inf], optional)
   :type image_index: int
   :param invert: Invert, Invert the mask (optional)
   :type invert: bool
   :param offset_x: Offset X, X offset for placing the mask image (in [-inf, inf], optional)
   :type offset_x: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_graph_select(*, extend=False)

   Select and move an inference or 3D asset node

   :param extend: Extend, Toggle this card in the existing selection instead of replacing it (optional)
   :type extend: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_preview_media(*, node_id="", media_id="")

   Open this image or video in its own preview window. Several can be open at once

   :param node_id: Node ID, Node whose result to open (optional, never None)
   :type node_id: str
   :param media_id: Media ID, Board image or video (by its own graph id) to open (optional, never None)
   :type media_id: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_rename_frame(*, frame_id="")

   Rename this frame in place. Enter applies the new name, Escape keeps the old one

   :param frame_id: Frame ID, Frame to rename; empty renames the one selected frame (optional, never None)
   :type frame_id: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_rename_media(*, media_id="")

   Rename this image or video in place. Enter applies the new name, Escape keeps the old one

   :param media_id: Media ID, Board image or video (by its own graph id) to rename; empty renames the one selected reference (optional, never None)
   :type media_id: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_select_image(*, extend=False)

   Select and move an image on the moodboard

   :param extend: Extend, Extend selection instead of deselecting everything first (optional)
   :type extend: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: moodboard_zoom()

   Zoom the moodboard canvas

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: sam3d_preview_delete()

   Delete a segmented image from the preview history

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
.. function:: sam3d_preview_select()

   Select a segmented image from the preview history

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
