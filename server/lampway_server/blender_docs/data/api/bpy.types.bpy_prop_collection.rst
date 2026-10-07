bpy_prop_collection
===================

.. currentmodule:: bpy.types

base classes --- :class:`bpy_prop`

.. class:: bpy_prop_collection(bpy_prop)

   built-in class used for all collections.

   .. method:: find(key)
   
      Returns the index of a key in a collection or -1 when not found
      (matches Python's string find function of the same name).
   
      :param key: The identifier for the collection member.
      :type key: str
      :return: index of the key.
      :rtype: int


   .. method:: foreach_get(attr, seq)
   
      Fast access to a basic-type attribute within a collection.
   
      :param attr: Name of the item attribute to read (for example ``co``, ``normal`` or
         ``select``). The attribute must be a basic type (bool, int or float).
   
         For geometry attribute types, see :attr:`Attribute.data_type`.
      :type attr: str
      :param seq: Writable sequence or buffer receiving flattened values.
         For array attributes, the length must be ``len(collection) * array_length``.
      :type seq: MutableSequence[bool | int | float] | buffer


      Only works for 'basic type' properties (bool, int and float)!
      Multi-dimensional arrays (like array of vectors) will be flattened into seq.

      .. literalinclude:: ../examples/bpy.types.bpy_prop_collection.foreach_get.0.py
         :lines: 5-


   .. method:: foreach_set(attr, seq)
   
      Fast access to a basic-type attribute within a collection.
   
      :param attr: Name of the item attribute to write (for example ``co`` or
         ``select``). The attribute must be a basic type (bool, int or float).
   
         For geometry attribute types, see :attr:`Attribute.data_type`.
      :type attr: str
      :param seq: Sequence or buffer containing flattened values.
         For array attributes, the length must be ``len(collection) * array_length``.
      :type seq: Sequence[bool | int | float] | buffer


      Only works for 'basic type' properties (bool, int and float)!
      seq must be uni-dimensional, multi-dimensional arrays (like array of vectors) will be re-created from it.

      .. literalinclude:: ../examples/bpy.types.bpy_prop_collection.foreach_set.0.py
         :lines: 5-


   .. method:: get(key, default=None)
   
      Returns the value of the item assigned to key or default when not found
      (matches Python's dictionary function of the same name).
   
      :param key: The identifier for the collection member.
      :type key: str
      :param default: Optional argument for the value to return if
         *key* is not found.
      :type default: Any
      :return: The collection member or default.
      :rtype: :class:`bpy_struct`


   .. method:: items()
   
      Return the identifiers of collection members
      (matching Python's dict.items() functionality).
   
      :return: (key, value) pairs for each member of this collection.
      :rtype: list[tuple[str, :class:`bpy.types.bpy_struct`]]


   .. method:: keys()
   
      Return the identifiers of collection members
      (matching Python's dict.keys() functionality).
   
      :return: the identifiers for each member of this collection.
      :rtype: list[str]


   .. method:: values()
   
      Return the values of collection
      (matching Python's dict.values() functionality).
   
      :return: The members of this collection.
      :rtype: list[:class:`bpy.types.bpy_struct` | None]


   .. details:: Special Methods

      .. method:: __contains__(item)

         :param item: Item to test for membership.
         :type item: object
         :rtype: bool

      .. method:: __getitem__(key)

         :param key: Index or key.
         :type key: int
         :rtype: :class:`bpy_struct`

      .. method:: __iter__()

         :rtype: typing.Iterator[:class:`bpy_struct`]

      .. method:: __len__()

         :rtype: int

      .. method:: __setitem__(key, value)

         :param key: Index or key.
         :type key: int
         :param value: Value to assign.
         :type value: object

