.. index:: Geometry Nodes; Set NURBS Order
.. _bpy.types.GeometryNodeSetNURBSOrder:

********************
Set NURBS Order Node
********************

.. figure:: /images/node-types_GeometryNodeSetNURBSOrder.webp
   :align: right
   :alt: Set NURBS Order node.

Controls how many control points influence each evaluated point of a NURBS curve
by modifying the ``nurbs_order`` attribute.

Higher order values result in smoother curves with broader influence from control points,
while lower values make the curve follow control points more closely.

Typical use cases include:

- Increasing smoothness for organic or flowing shapes.
- Reducing order to tighten control around sharp features.
- Matching curve behavior between different NURBS splines.
- Refining procedural curve generation.


Inputs
======

Curve
   Input curves. The node only affects curves of type NURBS.

Selection
   The points whose NURBS order will be changed.

Order
   The number of control points influencing each evaluated point.

   Valid values depend on the number of control points in the spline.
   Higher values increase smoothness but require more points.


Outputs
=======

Curve
   Standard curve output.
