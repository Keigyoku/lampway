.. index:: Geometry Nodes; Filter List
.. _bpy.types.GeometryNodeFilterList:

****************
Filter List Node
****************

.. figure:: /images/node-types_GeometryNodeFilterList.webp
   :align: center
   :alt: Filter List node.

The *Filter List* node splits a list into two lists based on a boolean selection.

Items with a corresponding selection value of ``true`` are placed in the
*Selection* output, while items with a selection value of ``false`` are placed
in the *Inverted* output.


Inputs
======

List
   The input list to filter.

Selection
   A boolean list used to determine which items are included in each output.

   The selection list is matched to the input list by index.


Properties
==========

Data Type
   The data type of the input and output lists.


Outputs
=======

Selection
   A list containing all items whose corresponding selection value is ``true``.

Inverted
   A list containing all items whose corresponding selection value is ``false``.
