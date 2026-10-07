ContextTempOverride
===================

.. currentmodule:: bpy.types

.. class:: ContextTempOverride


   .. method:: logging_set(enable, *, hide_missing=False)
   
      Set context member logging options for this temporary override.
   
      :param enable: Enable logging of context member access.
      :type enable: bool
      :param hide_missing: When true, suppress logging access to members that
         are not available in the current context.
      :type hide_missing: bool


   .. details:: Special Methods

      .. method:: __enter__()

         :rtype: :class:`ContextTempOverride`

      .. method:: __exit__(exc_type, exc_value, traceback)

         :param exc_type: Exception type, or ``None``.
         :type exc_type: type | None
         :param exc_value: Exception instance, or ``None``.
         :type exc_value: BaseException | None
         :param traceback: Traceback object, or ``None``.
         :type traceback: BaseException | None
         :rtype: bool



