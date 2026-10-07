.. index:: Geometry Nodes; 3D to Screen Space
.. --- copy below this line ---

***********************
3D to Screen Space Node
***********************

.. figure:: /images/node-types_GeometryNode3dToScreenSpace.webp
   :align: right
   :alt: 3D to Screen Space node.

The *3D to Screen Space* node transforms 3D positions into normalized screen
coordinates relative to a camera.

The output coordinates are normalized such that ``(0, 0)`` corresponds to the
bottom-left corner of the camera view and ``(1, 1)`` corresponds to the
top-right corner. Values outside this range represent positions outside the
camera frame.


Inputs
======

Vector
   Position to transform into screen space.

Camera
   Camera used for the transformation.

Clamp Depth
   Clamp the output depth to the camera's clipping range.


Outputs
=======

Normalized
   Normalized screen-space coordinates.

Depth
   Distance of the input position from the camera.

   Values outside the camera's clipping range are only returned when
   *Clamp Depth* is disabled.
