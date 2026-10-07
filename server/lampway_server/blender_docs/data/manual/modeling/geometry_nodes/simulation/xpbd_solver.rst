.. index:: Geometry Nodes; XPBD Solver

***********
XPBD Solver
***********

.. figure:: /images/node-types_GeometryNodeXPBDSolver.webp
   :align: right
   :alt: XPBD Solver node.

The *XPBD Solver* node provides a physics simulation system for hair, cloth, and particles.
It implements the "extended position-based dynamics" (XPBD) procedure.

This node is used in the
:doc:`Hair Dynamics </modeling/geometry_nodes/simulation/hair_dynamics>` and
:doc:`Cloth Dynamics </modeling/geometry_nodes/simulation/cloth_dynamics>` experimental node assets.

The node expects data to be provided in the form of *Typed Bundles* through its *World* input.
This includes both the simulated geometry components, structural constraint declarations targeting
the geometry, and external effectors such as damping and collision.

The *XPBD Solver* node is complex and intended to used inside more user-friendly assets. Full
documentation of its behavior and supported components of the *World* input can be found in the
`developer documentation <https://developer.blender.org/docs/features/nodes/xpbd_solver/>`__.


Inputs
======

World
   Bundle of geometry, behaviors, and effectors making up the simulation. Bundles can be nested
   inside each other; the world data does not have to follow any particular structure.
   Geometry and effectors can be grouped into logical sub-bundles, or kept in a flat bundle.

Delta Time
   Size of the overall time step in seconds. The step size is subdivided if a *Substeps* value
   greater than 1 is used.

Filter
   Comma-separated list of filter tags to limit which geometries are being simulated. Each geometry
   may be associated with list of tags, and the solver node will only simulate geometries that have
   at least one matching filter tag.

Simulation to World
   Optional transform from object space into simulation space. This defines the space in which all
   physical simulation takes place. All geometry attributes, forces, and other properties should be
   transformed accordingly beforehand. Collider geometry is converted to simulation space
   internally.


Solver
------

Substeps
   Number of substeps used by the simulation. Increasing substeps can help improve stability in some
   cases, but also increases cost due to repeated collision detection.

Constraint Iterations
   Number of iterations performed by the constraint solver to ensure all constraints are satisfied.
   If the residual error is larger than 1 then increasing the constraint iterations is recommended.

Path
   Optional output path for solver result data. If the path is not empty a new bundle is added to
   the *World* output with the results of the solver step.


Interpolation Range
-------------------

Begin
   Fractional start of the substep interval. This can be used for executing an external substep
   loop.

End
   Fractional end of the substep interval. This can be used for executing an external substep
   loop.


Outputs
=======

World
   Modified simulation data after a single time step has been applied. Geometry attributes for
   positions and rotations are updated according to physical motion, external forces, and
   constraints.

   Additional information about the simulation result may be stored in a bundle by setting the
   *Path* input. This includes a residual error value which describes the quality of the solution.
