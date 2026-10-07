.. index:: Geometry Nodes; Cluster by Connected
.. _bpy.types.GeometryNodeClusterByConnected:

*************************
Cluster by Connected Node
*************************

.. figure:: /images/node-types_GeometryNodeClusterByConnected.webp
   :align: right
   :alt: Cluster by Connected node.

The *Cluster by Connected* node assigns a cluster ID to connected regions of a mesh.

Vertices are considered part of the same cluster when they are connected by
edges and the distance between connected vertices does not exceed the specified threshold.

For clustering based solely on spatial proximity, regardless of mesh topology,
see the :doc:`Cluster by Distance </modeling/geometry_nodes/utilities/field/cluster_by_distance>` node.


Inputs
======

Selection
   Boolean field indicating which vertices participate in the clustering.

   Unselected vertices are ignored and do not connect neighboring vertices into the same cluster.

Position
   Position of each vertex used when measuring the distance between connected vertices.

Distance
   Maximum allowed distance between connected vertices for them to belong to the same cluster.


Outputs
=======

Cluster ID
   Integer field identifying the connected cluster for each selected vertex.

   Vertices with the same cluster ID belong to the same connected region.
