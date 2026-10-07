.. index:: Geometry Nodes; Custom Effector

***************
Custom Effector
***************

.. figure:: /images/node-types_GeometryNodeCustomEffector.webp
   :align: right
   :alt: Custom Effector node.

Create a custom effector for use in a simulation. This can be used to modify geometry or the
simulation world as a whole. A closure must be provided which is evaluated by the simulation
at some point during the time step update, depending on the *Stage*.


Inputs
======

Type
   Defines the data the effector is applied to and the closure signature used.

   :Geometry:
      Apply the effector to all geometries in the simulation world that match the *Filter* tags.
   :World:
      Apply the effector to the simulation world as a whole.

Stage
   Stage during the simulation update at which the effector is executed.

   :Default:
      Executed at the end of each time step (same as *Post-Solve*).
   :Pre-Simulation:
      Executed at the beginning of each frame before simulation state is applied.
   :Pre-Solve:
      Executed during the time step before the simulation is updated.
   :Post-Solve:
      Executed during the time step after the simulation is updated.
   :Custom:
      Named effector stage for custom solver builds. This is not used by the XPBD simulation Nodes
      but is intended for experimentation.

Geometry Effector :guilabel:`Geometry`
   Closure that is used with *Geometry* type effectors. The closure has a *Geometry* input and
   output that can be modified by the effector. It also has a *To World Transform* input which
   transforms from *simulation space* to world space.

World Effector :guilabel:`World`
   Closure that is used with *World* type effectors. The closure has a *World* bundle input and
   output that can be modified by the effector. It also has a *To World Transform* input which
   transforms from *simulation space* to world space.

Filter :guilabel:`Geometry`
   Optional comma-separated list of filter tags to limit the geometries that effector is applied to.
   Only geometries with at least one matching tag will be processed by the effector.


Outputs
=======

Effector
   Resulting effector bundle. This should be stored in the simulation world.
