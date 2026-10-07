.. index:: Geometry Nodes; Project with Depth
.. --- copy below this line ---

***********************
Project with Depth Node
***********************

.. figure:: /images/node-types_GeometryNodeProjectWithDepth.webp
   :align: right
   :alt: Project with Depth node.

The *Project with Depth* node reconstructs a 3D position from normalized
screen coordinates and a depth value using the given transform and projection
matrices.

This is a lower-level version of the :doc:`Screen Space to 3D <screen_space_to_3d>`
node that operates directly on projection data instead of a camera object.


Inputs
======

Normalized
   Normalized screen-space coordinates.

   A value of ``(0, 0)`` corresponds to the bottom-left corner of the
   projected view and ``(1, 1)`` corresponds to the top-right corner.

Depth
   Depth of the point relative to the projection.

Projection
   Projection matrix used to reconstruct the position.

Transform
   Transformation matrix applied after reconstructing the position.

Clip Start
   Near clipping distance used by the projection.

Clip End
   Far clipping distance used by the projection.


Outputs
=======

Vector
   Reconstructed 3D position.
