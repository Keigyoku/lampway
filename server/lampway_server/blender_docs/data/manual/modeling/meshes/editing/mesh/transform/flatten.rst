.. _bpy.ops.mesh.flatten:

*******
Flatten
*******

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Mesh --> Transform --> Flatten`

Flatten selected vertices onto a plane.

The operator calculates a target plane and moves vertices toward it while
preserving their relative positions along the unlocked axes.


Options
=======

Factor
   Strength of the flatten operation.

   A value of ``1`` fully flattens the selection onto the target plane,
   while lower values partially move vertices toward the plane.

Method
   Method used to determine the flattening plane.

   :Best Fit: Calculates a plane that best fits the selected vertices.
   :Normal: Derives the plane from the averaged normals of the selected faces.
   :View: Uses a plane perpendicular to the current view direction.

Lock
   Prevents movement along selected axes while flattening.

   This can be used to constrain the flatten operation to specific directions.


Example
=======

.. list-table::
   :widths: 1 1 1

   * - .. figure:: /images/modeling_meshes_editing_mesh_transform_flatten_example-1.png

          Before.

     - .. figure:: /images/modeling_meshes_editing_mesh_transform_flatten_example-2.png

          Flattened using Best Fit.

     - .. figure:: /images/modeling_meshes_editing_mesh_transform_flatten_example-3.png

          Flattened with axis locking.
