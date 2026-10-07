Image Buffer (imbuf)
====================

.. module:: imbuf

This module provides access to Blender's image manipulation API.

It provides access to image buffers outside of Blender's
:class:`bpy.types.Image` data-block context.

.. toctree::
   :maxdepth: 1
   :caption: Submodules

   imbuf.types.rst

.. function:: file_type_from_buffer(buffer)

   Detect the image file type from a buffer.

   :param buffer: A buffer containing image data.
   :type buffer: collections.abc.Buffer
   :return: The detected file type, or None if unrecognized.
   :rtype: :class:`ImBufFileType` or None


.. function:: load(filepath)

   Load an image from a file.

   :param filepath: The filepath of the image.
   :type filepath: str | bytes
   :return: The newly loaded image.
   :rtype: :class:`ImBuf`


.. function:: load_from_buffer(buffer)

   Load an image from a buffer.

   :param buffer: A buffer containing the image data.
   :type buffer: collections.abc.Buffer
   :return: The newly loaded image.
   :rtype: :class:`ImBuf`


.. function:: new(size, *, planes=32, buffer_type='BYTE')

   Create a new image.

   :param size: The size of the image in pixels.
   :type size: tuple[int, int]
   :param planes: Number of bits per pixel.
   :type planes: Literal[8, 16, 24, 32]
   :param buffer_type: The buffer type.
   :type buffer_type: Literal['BYTE', 'FLOAT']
   :return: The newly created image.
   :rtype: :class:`ImBuf`


.. function:: write(image, *, filepath=None)

   Write an image.

   :param image: The image to write.
   :type image: :class:`ImBuf`
   :param filepath: Optional filepath of the image (fallback to the image's file path).
   :type filepath: str | bytes | None


.. function:: write_to_buffer(image, file)

   Write an image to a file-like object.

   :param image: The image to write.
   :type image: :class:`ImBuf`
   :param file: A writable file-like object (e.g. :class:`io.BytesIO`).
   :type file: :class:`BinaryIO`


