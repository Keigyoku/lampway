.. index:: Geometry Nodes; Sort List
.. _bpy.types.GeometryNodeSortList:

**************
Sort List Node
**************

.. figure:: /images/node-types_GeometryNodeSortList.webp
   :align: center
   :alt: Sort List node.

The *Sort List* node sorts the elements of a list according to a weight value.

The sort order is ascending, with elements having lower weights placed
before elements with higher weights.


Inputs
======

List
   The input list to sort.

Selection
   Controls which list elements are sorted.

   Deselected elements remain in their original positions.

Group ID
   Separates the list into independent groups.

   Elements with the same group ID are sorted together, while elements in
   different groups are sorted independently.

Sort Weight
   Value used to determine the order of the list elements.

   Lower values are placed before higher values.


Properties
==========

Data Type
   The data type of the input list.


Outputs
=======

List
   The sorted list.
