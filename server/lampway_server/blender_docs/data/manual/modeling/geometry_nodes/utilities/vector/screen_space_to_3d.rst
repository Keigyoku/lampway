.. index:: Geometry Nodes; Screen to 3D Space
.. --- copy below this line ---

***********************
Screen to 3D Space Node
***********************

.. figure:: /images/node-types_GeometryNodeScreenSpaceTo3D.webp
   :align: right
   :alt: Screen to 3D Space node.

The *Screen to 3D Space* node reconstructs a 3D position from normalized
screen coordinates and a depth value relative to a camera.

This is the inverse operation of the :doc:`3D to Screen Space <3d_to_screen_space>` node.


Inputs
======

Normalized
   Normalized screen-space coordinates.

   A value of ``(0, 0)`` corresponds to the bottom-left corner of the camera
   view and ``(1, 1)`` corresponds to the top-right corner.

Depth
   Depth of the point relative to the camera.

Camera
   Camera used to reconstruct the 3D position.


Outputs
=======

Vector
   Reconstructed 3D position.
