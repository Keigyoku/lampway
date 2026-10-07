.. index:: Geometry Nodes; Transform and Project
.. --- copy below this line ---

**************************
Transform and Project Node
**************************

.. figure:: /images/node-types_GeometryNodeTransformAndProject.webp
   :align: right
   :alt: Transform and Project node.

The *Transform and Project* node transforms a 3D position and projects it
into normalized screen coordinates using the given transform and projection
matrices.

This is a lower-level version of the :doc:`3D to Screen Space <3d_to_screen_space>`
node that operates directly on projection data instead of a camera object.


Inputs
======

Vector
   Position to project.

Transform
   Transformation matrix applied before projection.

Projection
   Projection matrix used to project the transformed position.


Outputs
=======

Normalized
   Normalized screen-space coordinates.

   A value of ``(0, 0)`` corresponds to the bottom-left corner of the
   projected view and ``(1, 1)`` corresponds to the top-right corner.

Depth
   Depth of the transformed position relative to the projection.
