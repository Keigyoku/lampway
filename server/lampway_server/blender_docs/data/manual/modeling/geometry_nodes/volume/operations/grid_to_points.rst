.. index:: Geometry Nodes; Grid to Points
.. _bpy.types.GeometryNodeGridToPoints:

*******************
Grid to Points Node
*******************

.. figure:: /images/node-types_GeometryNodeGridToPoints.webp
   :align: right
   :alt: Grid to Points node.

The *Grid to Points* node converts a voxel grid into a point cloud.
Each active voxel or tile in the grid becomes a point.

The voxel value is stored as an anonymous attribute on the generated
points and is available as a field output. Additional information about
the voxel or tile is provided in index space.

This node is useful for creating custom visualizations of volume grids
or for further processing voxel data as points.


Inputs
======

Grid
   The input voxel grid to convert into points.


Properties
==========

Data Type
   The data type stored in the grid (e.g. *Float*, *Integer*, *Boolean*, *Vector*).
   This determines the type of the *Value* output.


Outputs
=======

Points
   A point cloud containing one point for each active voxel or tile.

Value
   The value stored in the grid at each voxel.
   For tiles, this represents the shared value for all voxels in that tile.

Voxel Index
-----------

X
   The X coordinate of the voxel in index space,
   or the minimum X coordinate of a tile.

Y
   The Y coordinate of the voxel in index space,
   or the minimum Y coordinate of a tile.

Z
   The Z coordinate of the voxel in index space,
   or the minimum Z coordinate of a tile.

Is Tile
   True when the point represents a tile (multiple voxels)
   rather than a single voxel.

Extent
   The size of the voxel or tile.
   For individual voxels this is ``1``.
   For tiles this represents the cubic dimension of the tile in voxels.
