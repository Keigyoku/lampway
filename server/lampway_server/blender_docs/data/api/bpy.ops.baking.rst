Baking Operators
================

.. module:: bpy.ops.baking

.. function:: batch_linear_to_srgb(*, image="", width=1024, height=1024, convert_r=True, convert_g=True, convert_b=True)

   Convert entire image from linear to sRGB (per-channel control)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param convert_r: Convert Red, (optional)
   :type convert_r: bool
   :param convert_g: Convert Green, (optional)
   :type convert_g: bool
   :param convert_b: Convert Blue, (optional)
   :type convert_b: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: batch_srgb_to_linear(*, image="", width=1024, height=1024, convert_r=True, convert_g=True, convert_b=True)

   Convert entire image from sRGB to linear (per-channel control)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param convert_r: Convert Red, (optional)
   :type convert_r: bool
   :param convert_g: Convert Green, (optional)
   :type convert_g: bool
   :param convert_b: Convert Blue, (optional)
   :type convert_b: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: bilateral_filter(*, image="", width=1024, height=1024, radius=3, sigma_space=3.0, sigma_color=0.1)

   Apply edge-preserving bilateral filter (C++ accelerated)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param radius: Radius, (in [1, 20], optional)
   :type radius: int
   :param sigma_space: Sigma Space, (in [0.1, 50], optional)
   :type sigma_space: float
   :param sigma_color: Sigma Color, (in [0.01, 1], optional)
   :type sigma_color: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: blend_images(*, base_image="", blend_image="", width=1024, height=1024, opacity=1.0, blend_mode='MIX')

   Blend two images using various blend modes

   :param base_image: Base Image, Base image (modified in place) (optional, never None)
   :type base_image: str
   :param blend_image: Blend Image, Image to blend on top (optional, never None)
   :type blend_image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param opacity: Opacity, (in [0, 1], optional)
   :type opacity: float
   :param blend_mode: Blend Mode, How to blend images (optional)

      - ``MIX``
        Mix -- Simple alpha blend.
      - ``ADD``
        Add -- Additive blend.
      - ``MULTIPLY``
        Multiply -- Multiply blend.
      - ``SCREEN``
        Screen -- Screen blend.
      - ``OVERLAY``
        Overlay -- Overlay blend.
      - ``SOFT_LIGHT``
        Soft Light -- Soft light blend.
      - ``DIFFERENCE``
        Difference -- Difference blend.
   :type blend_mode: Literal['MIX', 'ADD', 'MULTIPLY', 'SCREEN', 'OVERLAY', 'SOFT_LIGHT', 'DIFFERENCE']
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: blend_normal_maps(*, base_image="", detail_image="", width=1024, height=1024, detail_strength=1.0)

   Blend two normal maps using Reoriented Normal Mapping

   :param base_image: Base Image, Base normal map (modified in place) (optional, never None)
   :type base_image: str
   :param detail_image: Detail Image, Detail normal map to blend (optional, never None)
   :type detail_image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param detail_strength: Detail Strength, (in [0, 2], optional)
   :type detail_strength: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: box_blur(*, image="", width=1024, height=1024, radius=3)

   Apply box blur to image (C++ accelerated)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param radius: Radius, (in [1, 100], optional)
   :type radius: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: copy_image_channel_pixels(*, src_image="", dest_image="", src_width=1024, src_height=1024, dest_width=1024, dest_height=1024, src_idx=0, dest_idx=0, start_x=0, start_y=0, src_start_x=0, src_start_y=0, copy_width=1024, copy_height=1024, invert_value=False)

   Copy a single channel from one image to another (C++ accelerated)

   :param src_image: Source Image, (optional, never None)
   :type src_image: str
   :param dest_image: Destination Image, (optional, never None)
   :type dest_image: str
   :param src_width: Source Width, (in [1, 32768], optional)
   :type src_width: int
   :param src_height: Source Height, (in [1, 32768], optional)
   :type src_height: int
   :param dest_width: Destination Width, (in [1, 32768], optional)
   :type dest_width: int
   :param dest_height: Destination Height, (in [1, 32768], optional)
   :type dest_height: int
   :param src_idx: Source Channel, (in [0, 3], optional)
   :type src_idx: int
   :param dest_idx: Destination Channel, (in [0, 3], optional)
   :type dest_idx: int
   :param start_x: Start X, (in [0, 32768], optional)
   :type start_x: int
   :param start_y: Start Y, (in [0, 32768], optional)
   :type start_y: int
   :param src_start_x: Source Start X, (in [0, 32768], optional)
   :type src_start_x: int
   :param src_start_y: Source Start Y, (in [0, 32768], optional)
   :type src_start_y: int
   :param copy_width: Copy Width, (in [1, 32768], optional)
   :type copy_width: int
   :param copy_height: Copy Height, (in [1, 32768], optional)
   :type copy_height: int
   :param invert_value: Invert Value, Invert the copied value (optional)
   :type invert_value: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: copy_image_pixels(*, src_image="", dest_image="", src_width=1024, src_height=1024, dest_width=1024, dest_height=1024, start_x=0, start_y=0, src_start_x=0, src_start_y=0, copy_width=1024, copy_height=1024)

   Copy pixels from one image to another (C++ accelerated)

   :param src_image: Source Image, (optional, never None)
   :type src_image: str
   :param dest_image: Destination Image, (optional, never None)
   :type dest_image: str
   :param src_width: Source Width, (in [1, 32768], optional)
   :type src_width: int
   :param src_height: Source Height, (in [1, 32768], optional)
   :type src_height: int
   :param dest_width: Destination Width, (in [1, 32768], optional)
   :type dest_width: int
   :param dest_height: Destination Height, (in [1, 32768], optional)
   :type dest_height: int
   :param start_x: Start X, (in [0, 32768], optional)
   :type start_x: int
   :param start_y: Start Y, (in [0, 32768], optional)
   :type start_y: int
   :param src_start_x: Source Start X, (in [0, 32768], optional)
   :type src_start_x: int
   :param src_start_y: Source Start Y, (in [0, 32768], optional)
   :type src_start_y: int
   :param copy_width: Copy Width, (in [1, 32768], optional)
   :type copy_width: int
   :param copy_height: Copy Height, (in [1, 32768], optional)
   :type copy_height: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: dilate(*, image="", width=1024, height=1024, radius=1, channel=0)

   Dilate image channel (expand bright areas)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param radius: Radius, (in [1, 50], optional)
   :type radius: int
   :param channel: Channel, Channel to dilate (0=R, 1=G, 2=B, 3=A) (in [0, 3], optional)
   :type channel: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: dither_image(*, image="", width=1024, height=1024, amount=0.004, seed=0)

   Add dithering noise to reduce banding artifacts

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param amount: Amount, Dither amount (1/255 ≈ 0.004 for 8-bit) (in [0, 0.1], optional)
   :type amount: float
   :param seed: Seed, Random seed for reproducibility (in [0, inf], optional)
   :type seed: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: divide_rgb_by_alpha(*, image="", width=1024, height=1024, start_x=0, start_y=0, region_width=1024, region_height=1024)

   Unpremultiply RGB channels by alpha (C++ accelerated)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param start_x: Start X, (in [0, 32768], optional)
   :type start_x: int
   :param start_y: Start Y, (in [0, 32768], optional)
   :type start_y: int
   :param region_width: Region Width, (in [1, 32768], optional)
   :type region_width: int
   :param region_height: Region Height, (in [1, 32768], optional)
   :type region_height: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: erode(*, image="", width=1024, height=1024, radius=1, channel=0)

   Erode image channel (shrink bright areas)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param radius: Radius, (in [1, 50], optional)
   :type radius: int
   :param channel: Channel, Channel to erode (0=R, 1=G, 2=B, 3=A) (in [0, 3], optional)
   :type channel: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: fxaa(*, image="", width=1024, height=1024)

   Apply FXAA anti-aliasing to image (C++ accelerated)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: gaussian_blur(*, image="", width=1024, height=1024, radius=3, sigma=1.0)

   Apply Gaussian blur to image (C++ accelerated)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param radius: Radius, (in [1, 100], optional)
   :type radius: int
   :param sigma: Sigma, (in [0.1, 100], optional)
   :type sigma: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: get_image_minmax(*, image="", width=1024, height=1024, min_value=0.0, max_value=1.0)

   Calculate minimum and maximum pixel values in image

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param min_value: Min Value, Minimum pixel value found (in [-inf, inf], optional)
   :type min_value: float
   :param max_value: Max Value, Maximum pixel value found (in [-inf, inf], optional)
   :type max_value: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: height_to_normal(*, image="", width=1024, height=1024, strength=1.0)

   Convert height map to tangent space normal map

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param strength: Strength, (in [0.01, 10], optional)
   :type strength: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: multiply_rgb_by_alpha(*, image="", width=1024, height=1024, start_x=0, start_y=0, region_width=1024, region_height=1024)

   Premultiply RGB channels by alpha (C++ accelerated)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param start_x: Start X, (in [0, 32768], optional)
   :type start_x: int
   :param start_y: Start Y, (in [0, 32768], optional)
   :type start_y: int
   :param region_width: Region Width, (in [1, 32768], optional)
   :type region_width: int
   :param region_height: Region Height, (in [1, 32768], optional)
   :type region_height: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: normalize_image(*, image="", width=1024, height=1024, target_min=0.0, target_max=1.0)

   Normalize image values to target range

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param target_min: Target Min, (in [-inf, inf], optional)
   :type target_min: float
   :param target_max: Target Max, (in [-inf, inf], optional)
   :type target_max: float
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: pixels_to_linear(*, image="", width=1024, height=1024, start_x=0, start_y=0, convert_width=1024, convert_height=1024)

   Convert image region from sRGB to linear color space

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param start_x: Start X, (in [0, 32768], optional)
   :type start_x: int
   :param start_y: Start Y, (in [0, 32768], optional)
   :type start_y: int
   :param convert_width: Convert Width, (in [1, 32768], optional)
   :type convert_width: int
   :param convert_height: Convert Height, (in [1, 32768], optional)
   :type convert_height: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: pixels_to_srgb(*, image="", width=1024, height=1024, start_x=0, start_y=0, convert_width=1024, convert_height=1024)

   Convert image region from linear to sRGB color space

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param start_x: Start X, (in [0, 32768], optional)
   :type start_x: int
   :param start_y: Start Y, (in [0, 32768], optional)
   :type start_y: int
   :param convert_width: Convert Width, (in [1, 32768], optional)
   :type convert_width: int
   :param convert_height: Convert Height, (in [1, 32768], optional)
   :type convert_height: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: set_image_pixels(*, image="", width=1024, height=1024, start_x=0, start_y=0, fill_width=1024, fill_height=1024, color=(0.0, 0.0, 0.0, 0.0))

   Fill image region with a solid color (C++ accelerated)

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :param start_x: Start X, (in [0, 32768], optional)
   :type start_x: int
   :param start_y: Start Y, (in [0, 32768], optional)
   :type start_y: int
   :param fill_width: Fill Width, (in [1, 32768], optional)
   :type fill_width: int
   :param fill_height: Fill Height, (in [1, 32768], optional)
   :type fill_height: int
   :param color: Color, Fill color (RGBA) (array of 4 items, in [0, 1], optional)
   :type color: Sequence[float]
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

.. function:: sobel_edge_detect(*, image="", width=1024, height=1024)

   Detect edges using Sobel operator

   :param image: Image, (optional, never None)
   :type image: str
   :param width: Width, (in [1, 32768], optional)
   :type width: int
   :param height: Height, (in [1, 32768], optional)
   :type height: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

