ID Property Access (idprop.types)
=================================

.. module:: idprop.types

.. class:: IDPropertyArray

   An array of values with a fixed type, supporting indexing and slicing.

   .. method:: to_list()
   
      Return the array as a list.
   
      :return: The array as a list.
      :rtype: list[int] | list[float] | list[bool]


   .. attribute:: typecode

      The type of the data in the array {'f': float (32-bit), 'd': double (64-bit), 'i': int, 'b': bool}. Both 'f' and 'd' use Python's :class:`float` type but differ in storage precision.
      
      :type: Literal['f', 'd', 'i', 'b']


   .. details:: Special Methods

      .. method:: __getitem__(key)

         :param key: Index or key.
         :type key: int
         :rtype: float | int | bool

      .. method:: __getitem__(key)
         :noindex:

         :param key: Index or key.
         :type key: slice
         :rtype: list[float] | list[int] | list[bool]

      .. method:: __len__()

         :rtype: int

      .. method:: __repr__()

         :rtype: str

      .. method:: __setitem__(key, value)

         :param key: Index.
         :type key: int
         :param value: Value to assign.
         :type value: float | int | bool



.. class:: IDPropertyGroup

   A dictionary-like group of ID properties, supporting key access, iteration, and membership testing.
   
   .. note::
   
      Only supports a maximum of 1024 levels of nesting.

   .. method:: clear()
   
      Clear all members from this group.


   .. method:: get(key, default=None)
   
      Return the value for key, if it exists, else default.
   
      :param key: The key to look up.
      :type key: str
      :param default: Value to return if *key* is not found.
      :type default: Any
      :return: The value for the key, or *default* if not found.
      :rtype: Any


   .. method:: items()
   
      Return a view of the items in the group, behaves like dictionary method items.
   
      :return: A view of the items.
      :rtype: :class:`IDPropertyGroupViewItems`


   .. method:: keys()
   
      Return a view of the keys in the group.
   
      :return: A view of the keys.
      :rtype: :class:`IDPropertyGroupViewKeys`


   .. method:: pop(key, default)
   
      Remove an item from the group, returning a Python representation.
   
      :raises KeyError: When the item doesn't exist and no *default* is given.
   
      :param key: Name of item to remove.
      :type key: str
      :param default: Value to return when *key* isn't found (optional, a :exc:`KeyError` is raised when omitted and the key is not found).
      :type default: Any
      :return: A Python representation of the removed item, or *default*.
      :rtype: Any


   .. method:: to_dict()
   
      Return a purely Python version of the group.
   
      :return: A dictionary representation of the group.
      :rtype: dict[str, Any]


   .. method:: update(other)
   
      Update key-value pairs from *other*, overwriting existing keys.
   
      .. note::
   
         Unlike :meth:`dict.update`, keyword arguments are not supported.
   
      :param other: Updates the values in the group with this.
      :type other: :class:`IDPropertyGroup` | dict[str, Any]


   .. method:: values()
   
      Return the values associated with this group.
   
      :return: A view of the values.
      :rtype: :class:`IDPropertyGroupViewValues`


   .. attribute:: name

      The name of this Group.
      
      :type: str


   .. details:: Special Methods

      .. method:: __contains__(item)

         :param item: Item to test for membership.
         :type item: object
         :rtype: bool

      .. method:: __getitem__(key)

         :param key: Property name.
         :type key: str
         :rtype: Any

      .. method:: __hash__()

         :rtype: int

      .. method:: __iter__()

         :rtype: :class:`IDPropertyGroupIterKeys`

      .. method:: __len__()

         :rtype: int

      .. method:: __repr__()

         :rtype: str

      .. method:: __setitem__(key, value)

         :param key: Property name.
         :type key: str
         :param value: Value to assign.
         :type value: Any



.. class:: IDPropertyGroupIterItems

   Iterator over :class:`IDPropertyGroup` items (key/value pairs).

   .. details:: Special Methods

      .. method:: __eq__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __hash__()

         :rtype: int

      .. method:: __iter__()

         :rtype: :class:`IDPropertyGroupIterItems`

      .. method:: __ne__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __next__()

         :rtype: tuple[str, Any]

      .. method:: __repr__()

         :rtype: str

      .. method:: __str__()

         :rtype: str



.. class:: IDPropertyGroupIterKeys

   Iterator over :class:`IDPropertyGroup` keys.

   .. details:: Special Methods

      .. method:: __eq__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __hash__()

         :rtype: int

      .. method:: __iter__()

         :rtype: :class:`IDPropertyGroupIterKeys`

      .. method:: __ne__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __next__()

         :rtype: str

      .. method:: __repr__()

         :rtype: str

      .. method:: __str__()

         :rtype: str



.. class:: IDPropertyGroupIterValues

   Iterator over :class:`IDPropertyGroup` values.

   .. details:: Special Methods

      .. method:: __eq__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __hash__()

         :rtype: int

      .. method:: __iter__()

         :rtype: :class:`IDPropertyGroupIterValues`

      .. method:: __ne__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __next__()

         :rtype: Any

      .. method:: __repr__()

         :rtype: str

      .. method:: __str__()

         :rtype: str



.. class:: IDPropertyGroupViewItems

   A view of :class:`IDPropertyGroup` items as key/value pairs (supports ``len()``, ``in``, iteration, and ``reversed()``).

   .. details:: Special Methods

      .. method:: __contains__(item)

         :param item: Item to test for membership.
         :type item: object
         :rtype: bool

      .. method:: __eq__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __hash__()

         :rtype: int

      .. method:: __iter__()

         :rtype: :class:`IDPropertyGroupIterItems`

      .. method:: __len__()

         :rtype: int

      .. method:: __ne__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __repr__()

         :rtype: str

      .. method:: __str__()

         :rtype: str



.. class:: IDPropertyGroupViewKeys

   A view of :class:`IDPropertyGroup` keys (supports ``len()``, ``in``, iteration, and ``reversed()``).

   .. details:: Special Methods

      .. method:: __contains__(item)

         :param item: Item to test for membership.
         :type item: object
         :rtype: bool

      .. method:: __eq__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __hash__()

         :rtype: int

      .. method:: __iter__()

         :rtype: :class:`IDPropertyGroupIterKeys`

      .. method:: __len__()

         :rtype: int

      .. method:: __ne__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __repr__()

         :rtype: str

      .. method:: __str__()

         :rtype: str



.. class:: IDPropertyGroupViewValues

   A view of :class:`IDPropertyGroup` values (supports ``len()``, ``in``, iteration, and ``reversed()``).

   .. details:: Special Methods

      .. method:: __contains__(item)

         :param item: Item to test for membership.
         :type item: object
         :rtype: bool

      .. method:: __eq__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __hash__()

         :rtype: int

      .. method:: __iter__()

         :rtype: :class:`IDPropertyGroupIterValues`

      .. method:: __len__()

         :rtype: int

      .. method:: __ne__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __repr__()

         :rtype: str

      .. method:: __str__()

         :rtype: str



