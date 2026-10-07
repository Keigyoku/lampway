.. index:: Compositor Nodes; Object Info

****************
Object Info Node
****************

.. figure:: /images/node-types_GeometryNodeObjectInfo-compositor.webp
   :align: right
   :alt: Object Info node.

The *Object Info* node outputs transformation information from an object in the scene.
This can be used to drive compositor effects using the position, rotation, or scale
of objects without manually entering values.

An *Object Info* node can be added quickly by dragging an object into the node editor.


Inputs
======

Object
   Object to get the properties from.


Outputs
=======

Transform
   :term:`Transformation Matrix` containing the location, rotation and scale of the object.
Location
   Location of the object in world space.
Rotation
   Rotation of the object in world space.
Scale
   Scale of the object in world space.
