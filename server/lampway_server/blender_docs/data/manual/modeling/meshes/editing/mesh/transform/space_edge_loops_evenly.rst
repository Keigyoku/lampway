.. _bpy.ops.mesh.space_edge_loops_evenly:

***********************
Space Edge Loops Evenly
***********************

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Mesh --> Transform --> Space Edge Loops Evenly`

Redistribute the vertices of the selected edge loops so they are spaced more
evenly along the loop while preserving its overall shape.

This is useful for improving the distribution of vertices after modeling
operations such as extrusion, subdivision, or manual editing.


Options
=======

Factor
   Strength of the operation.

   A value of ``0`` leaves the mesh unchanged, while ``1`` fully redistributes the vertices.

Interpolation
   Algorithm used to compute the new vertex positions.

   :Cubic:
      Uses a natural cubic spline to produce a smooth distribution that better
      preserves the curvature of the loop.
   :Linear:
      Interpolates directly along the existing edges.
      This is faster and preserves straight edge segments.

Lock
   Restrict movement to the selected axes.
