.. index:: Geometry Nodes; Vector
.. _bpy.types.FunctionNodeInputVector:
.. --- copy below this line ---

***********
Vector Node
***********

.. figure:: /images/node-types_FunctionNodeInputVector.webp
   :align: right
   :alt: Vector Node.

The *Vector* node outputs a constant vector value with 2, 3, or 4 components.
This node is commonly used to provide fixed directions, coordinates, or offsets to other nodes.


Inputs
======

This node has no inputs.


Properties
==========

Dimensions
   The number of components in the vector. Valid values range from 2 to 4.
   Increasing the dimension adds additional components to the vector.

   *This option can only be found in the Sidebar.*

X, Y, Z, W
   The value of each vector component.

   Only the components corresponding to the selected *Dimensions* are shown.


Outputs
=======

Vector
   The resulting vector value.
