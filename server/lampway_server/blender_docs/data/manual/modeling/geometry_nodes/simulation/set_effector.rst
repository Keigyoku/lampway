.. index:: Geometry Nodes; Set Effector

************
Set Effector
************

.. figure:: /images/node-types_GeometryNodeSetEffector.webp
   :align: right
   :alt: Set Effector node.

Add an effector definition to a geometry. Simulations can access this information and include the
effector in the simulation world.

Inputs
======

Geometry
   Geometry in which to store the effector.

Effector
   Bundle making up the effector definition. This can be generated using for example the
   :doc:`Custom Effector </modeling/geometry_nodes/simulation/custom_effector>` node.

Name
   Unique name of the effector. If the name is empty then the effector is stored as the default
   effector.

Outputs
=======

Geometry
   Geometry with the effector stored in its
   :doc:`Geometry Bundle </modeling/geometry_nodes/geometry/write/set_geometry_bundle>`.