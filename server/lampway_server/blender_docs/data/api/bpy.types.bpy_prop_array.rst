bpy_prop_array
==============

.. currentmodule:: bpy.types

base classes --- :class:`bpy_prop`

.. class:: bpy_prop_array(bpy_prop)

   built-in class used for array properties.

   .. method:: foreach_get(seq)
   
      This is a function to give fast access to array data.
   
      :param seq: Buffer to read element values into, must match the length of this array.
      :type seq: MutableSequence[Any]


   .. method:: foreach_set(seq)
   
      This is a function to give fast access to array data.
   
      :param seq: Element values to write, must match the length of this array.
      :type seq: Sequence[Any]


   .. details:: Special Methods

      .. method:: __contains__(item)

         :param item: Item to test for membership.
         :type item: object
         :rtype: bool

      .. method:: __getitem__(key)

         :param key: Index or key.
         :type key: int
         :rtype: float

      .. method:: __iter__()

         :rtype: :class:`bpy_prop_array`

      .. method:: __len__()

         :rtype: int

      .. method:: __repr__()

         :rtype: str

      .. method:: __setitem__(key, value)

         :param key: Index or key.
         :type key: int
         :param value: Value to assign.
         :type value: object

