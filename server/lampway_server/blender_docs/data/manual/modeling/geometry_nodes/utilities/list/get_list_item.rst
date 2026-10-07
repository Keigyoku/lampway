.. index:: Geometry Nodes; Get List Item
.. _bpy.types.GeometryNodeListGetItem:

******************
Get List Item Node
******************

.. figure:: /images/node-types_GeometryNodeListGetItem.webp
   :align: center
   :alt: Get List Item node.

The *Get List Item* node returns the value stored at a specific index in a list.


Inputs
======

List
   The input list.

Index
   The index of the item to retrieve.

   Indices are zero-based, meaning the first item in the list has an index of ``0``.


Properties
==========

Data Type
   The data type of the input list and output value.


Outputs
=======

Value
   The value stored at the specified index in the input list.

   If the index is outside the bounds of the list,
   the default value for the selected data type is returned.
