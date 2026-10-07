.. index:: Geometry Nodes; Geometry Principal Components

**********************************
Geometry Principal Components Node
**********************************

.. figure:: /images/node-types_GeometryNodePrincipalComponents.webp
   :align: right
   :alt: Geometry Principal Components node.

The *Geometry Principal Components* node performs a Principal Component Analysis (PCA)
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

Geometry
   Geometry containing the points to analyze.

   All geometry component types except volumes are supported.

Position
   Position values used in the analysis.


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
