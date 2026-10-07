.. index:: Geometry Nodes; Clip Grid
.. _bpy.types.GeometryNodeGridClip:

**************
Clip Grid Node
**************

.. figure:: /images/node-types_GeometryNodeGridClip.webp
   :align: right
   :alt: Clip Grid node.

The *Clip Grid* node restricts a voxel grid to a bounding box defined in
index space.

Voxels outside the specified minimum and maximum indices are deactivated
and their values are set to the grid's background value.

If a tile is partially inside the clipping bounds, it is fully voxelized
so that individual voxels can be clipped correctly.


Inputs
======

Grid
   The input voxel grid to clip.

Min X
   Minimum X index of the clipping bounding box.

Min Y
   Minimum Y index of the clipping bounding box.

Min Z
   Minimum Z index of the clipping bounding box.

Max X
   Maximum X index of the clipping bounding box.

Max Y
   Maximum Y index of the clipping bounding box.

Max Z
   Maximum Z index of the clipping bounding box.


Properties
==========

Data Type
   The type of data stored in the grid (for example *Float*, *Integer*,
   *Boolean*, or *Vector*).
   Must match the data type of the input grid.


Outputs
=======

Grid
   The clipped voxel grid with voxels outside the specified bounds
   deactivated and reset to the background value.
