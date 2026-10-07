.. index:: Geometry Nodes; Closure to List
.. _bpy.types.GeometryNodeClosureToList:

********************
Closure to List Node
********************

.. figure:: /images/node-types_GeometryNodeClosureToList.webp
   :align: center
   :alt: Closure to List node.

The *Closure to List* node evaluates a closure multiple times and stores the
resulting values in a list.

This is useful for generating lists procedurally, where each iteration can
produce a different value based on the current index or other inputs.


Inputs
======

Count
   The number of elements to generate in the output list.

Closure
   The closure that is evaluated once for each list element.


Properties
==========

Items
-----

A list of all items evaluated from the input closure.

Each item definition creates a corresponding list output.

Socket Type
   The data type of the values stored in the generated list.

Shape
   The data structure used for the list items. This can be any supported
   socket shape, such as single values, fields or grids.


Outputs
=======

Each item defined in the node properties creates a separate list output.
