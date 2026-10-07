Font Drawing Types (blf.types)
==============================

.. module:: blf.types

This module provides access to font drawing types.

.. class:: BLFImBufContext

   Context manager returned by :func:`blf.bind_imbuf` that binds an image buffer
   as the destination for text drawing.

   .. details:: Special Methods

      .. method:: __enter__()

         :rtype: :class:`BLFImBufContext`

      .. method:: __exit__(exc_type, exc_value, traceback)

         :param exc_type: Exception type, or ``None``.
         :type exc_type: type | None
         :param exc_value: Exception instance, or ``None``.
         :type exc_value: BaseException | None
         :param traceback: Traceback object, or ``None``.
         :type traceback: BaseException | None
         :rtype: bool



