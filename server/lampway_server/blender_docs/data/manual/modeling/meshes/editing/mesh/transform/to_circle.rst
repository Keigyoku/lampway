.. _bpy.ops.mesh.circularize:

*********
To Circle
*********

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Mesh --> Transform --> To Circle`

Transforms selected vertices into a circular shape.

The operator works best on edge loops but can also be used on arbitrary vertex selections,
including open loops or multiple disconnected selections.


Options
=======

Factor
   Controls the strength of the transformation.

   A value of 0 leaves the geometry unchanged,
   while 1 fully transforms the selection into a circle.

Method
   Determines how the circle is calculated.

   :Best Fit:
      Computes a circle that best fits the selected vertices using a least-squares method.

      This preserves the overall shape of the selection while making it circular.
   :Interior Fit:
      Computes a circle that fits inside the existing selection.

      Vertices are not moved farther away from the center,
      which helps preserve surrounding topology.

Rotation
   Rotates (twists) the resulting circle around its center.

Radius
   Overrides the automatically calculated radius.

   Useful for creating circles of consistent size or for precise control.

Space Evenly
   Distributes vertices evenly along the circle.

   When disabled, vertex spacing follows the original distribution.

Flatten
   Controls how much the selection is flattened to a best-fit plane before circularizing.

   A value of 0 keeps the original shape,
   while a value of 1 fully flattens the selection.

   Intermediate values blend between the original shape and the flattened result.

Lock
   Restricts transformations along selected axes.


Example
=======

.. list-table::

   * - .. figure:: /images/modeling_meshes_editing_mesh_to_circle_example1a.png

          Before

     - .. figure:: /images/modeling_meshes_editing_mesh_to_circle_example1b.png

          After
