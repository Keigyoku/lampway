Cycles Operators
================

.. module:: bpy.ops.cycles

.. function:: denoise_animation(*, input_filepath="", output_filepath="")

   Denoise rendered animation sequence using current scene and view layer settings. Requires denoising data passes and output to OpenEXR multilayer files

   :param input_filepath: Input Filepath, File path for image to denoise. If not specified, uses the render file path and frame range from the scene (optional, never None)
   :type input_filepath: str
   :param output_filepath: Output Filepath, If not specified, renders will be denoised in-place (optional, never None)
   :type output_filepath: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/cycles/operators.py\:49 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/cycles/operators.py#L49>`__


.. function:: merge_images(*, input_filepath1="", input_filepath2="", output_filepath="")

   Combine OpenEXR multi-layer images rendered with different sample ranges into one image with reduced noise

   :param input_filepath1: Input Filepath, File path for image to merge (optional, never None)
   :type input_filepath1: str
   :param input_filepath2: Input Filepath, File path for image to merge (optional, never None)
   :type input_filepath2: str
   :param output_filepath: Output Filepath, File path for merged image (optional, never None)
   :type output_filepath: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/cycles/operators.py\:137 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/cycles/operators.py#L137>`__


.. function:: use_shading_nodes()

   Enable nodes on a light

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/cycles/operators.py\:23 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/cycles/operators.py#L23>`__

