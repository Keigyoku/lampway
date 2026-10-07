.. index:: Geometry Nodes; Principal Components

*************************
Principal Components Node
*************************

.. figure:: /images/node-types_GeometryNodePrincipalComponents.webp
   :align: right
   :alt: Principal Components node.

The *Principal Components* node performs a Principal Component Analysis (PCA)
on a field of positions.

PCA analyzes how the positions are distributed, finding the center of the
data along with the orthogonal axes that best describe its orientation and
shape. The resulting axes are ordered by how much the data varies along each
direction, from greatest to least.

This is useful for determining the dominant orientation of geometry,
aligning objects to point clouds, generating local coordinate systems,
or measuring the extent of a distribution.


Inputs
======

Position
   Position values to analyze.

Group ID
   Integer field defining independent analysis groups.

   Elements with the same group ID are analyzed together, while elements
   with different group IDs are processed independently.


Outputs
=======

Group Center
   Center of the analyzed group.

Rotation
   Rotation whose local axes correspond to the principal axes of the data.

Principal Components
   Variance of the data along each principal axis.

   Larger values indicate greater spread along the corresponding axis.


Principal Axes
--------------

Longest Axis
   Unit vector corresponding to the direction of greatest variance.

Intermediate Axis
   Unit vector corresponding to the direction of intermediate variance.

   Together with the other axes, it forms a right-handed orthogonal basis.

Shortest Axis
   Unit vector corresponding to the direction of least variance.
