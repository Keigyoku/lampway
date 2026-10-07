.. index:: Geometry Nodes; Custom Force

************
Custom Force
************

.. figure:: /images/node-types_GeometryNodeCustomForce.webp
   :align: right
   :alt: Custom Force node.

Apply a custom force to simulated geometry.

Inputs
======

Mode
   How the force field is defined.

   :Field:
      Define the force with a vector field and transformation spaces.

      Transformation spaces can be:

      :Custom Space:
         Defined by a matrix input.
      :World Space:
         Common world space.
      :Object Space:
         Transform of a given object.

   :Closure:
      Compute the force vectors with a closure during the time step.

Selection :guilabel:`Field`
   Selection of points that the force is applied to.

Force :guilabel:`Field`
   The force vector at each point, defined in *Force Space*.

Geometry Space :guilabel:`Field`
   The space the geometry is transformed to before the field is evaluated.

Force Space :guilabel:`Field`
   The space in which the output vector is computed.

Closure :guilabel:`Closure`
   A closure that computes the force field on demand.
   
   It has a *Geometry* input and output, receiving the geometry to which the force is applied.
   The output geometry may be modified, but any changes are temporary and only used during field
   evaluation. The input geometry is in simulation space.
   
   It receives a *To World Transform* matrix which transforms from simulation space to world space.

   The closure must output a *Selection* boolean field defining the points to which force is applied
   as well as a *Force* vector field which defines the actual force vectors in simulation space.

Filter
   Comma-separated list of tags to limit the effect of the force. The force is only applied to
   geometries that have at least one matching tag.

Outputs
=======

Force
   Resulting effector bundle that should be stored in the simulation world.