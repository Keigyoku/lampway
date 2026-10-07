
********************************
Selecting Grease Pencil Elements
********************************

.. _bpy.ops.grease_pencil.set_selection_mode:
.. _bpy.types.ToolSettings.gpencil_selectmode_edit:

Select Mode
===========

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`3D Viewport Header --> Select Mode`
   :Shortcut:  :kbd:`1`, :kbd:`2`, :kbd:`3`

.. figure:: /images/grease-pencil_selecting_mode-buttons.png
   :align: right

   Edit Mode selection buttons.

In Edit Mode there are three different selection modes.
You can enter the different modes by selecting one of the three buttons in the header.

:Points: To select individual points.
:Strokes: To select an entire stroke.
:Segments: To select all points that are between other strokes.

.. figure:: /images/grease-pencil_selecting_example.png

   Points, stroke and in between stroke selection sample.


.. _bpy.ops.grease_pencil.select_all:

Select All/None/Invert
======================

All these options have the same meaning and behavior as in
:doc:`Object Mode </scene_layout/object/selecting>`.


.. _bpy.ops.grease_pencil.select_random:

Select Random
=============

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Select --> Select Random`

Randomly selects unselected points or strokes.

Ratio
   The likelihood of an unselected elements being selected.
   Note that, this is not the percentage amount of elements that will be selected.
Random Seed
   :term:`Seed` used by the pseudo-random number generator.
Action
   Selection or deselection of elements.


.. _bpy.ops.grease_pencil.select_alternate:

Select Alternated
=================

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Select --> Select Alternated`

Selects alternate points in the selected strokes.


.. _bpy.ops.grease_pencil.select_more:
.. _bpy.ops.grease_pencil.select_less:

Select More/Less
================

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Select --> More/Less`
   :Shortcut:  :kbd:`Ctrl-NumpadPlus`, :kbd:`Ctrl-NumpadMinus`

The purpose of these operators is to reduce or enlarge the current selection within a stroke
(i.e. they will never "go outside" of a stroke or "jump" to another stroke in the same object).

More
   For each selected point, select *all* its linked points (i.e. one or two...).
Less
   For each selected point, if *all* points linked to this point are selected, keep this one selected.
   Otherwise, deselect it.

.. hint::

   When *all* points of a stroke are selected, nothing will happen
   (as for *Less*, all linked points are always selected, and of course, *More* cannot add any).
   Conversely, the same goes when no points are selected.


.. _bpy.ops.grease_pencil.select_by_stroke_type:

By Stroke Type
==============

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Select --> By Stroke Type`

Selects curves based on whether they are strokes or fills.

Type
   :Stroke: Select all stroke curves (outlines).
   :Fill: Select all fill curves (enclosed filled shapes).

Deselect
   If enabled, matching curves are deselected instead of selected.


.. _bpy.ops.grease_pencil.select_similar:

Select Similar
==============

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Select --> Select Similar`
   :Shortcut:  :kbd:`Shift-G`

Select all strokes with similar characteristics.

Mode
   The characteristics to compare.

   :Layer: Selects all the points/strokes with a similar layer index.
   :Material: Selects all the points/strokes with a similar material index.
   :Vertex Color: Selects all the points/strokes with a similar vertex color.
   :Radius: Selects all the points/strokes with a similar stroke radius.
   :Opacity: Selects all the points/strokes with a similar layer opacity

Threshold
   How similar the selection must be.


.. _bpy.ops.grease_pencil.select_fill:

Select Fill
===========

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Select --> Select Fill`
   :Shortcut:  :kbd:`Ctrl-L`

Selects all curves that belong to the same fill region as the active curve.

Grease Pencil fills can be composed of multiple boundary curves.
This operator expands the current selection to include all curves
that define the same enclosed fill area.

This is useful when editing or transforming an entire filled shape,
ensuring that all boundary strokes are selected together.


.. _bpy.ops.grease_pencil.select_linked:

Select Linked
=============

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Select --> Select Linked`
   :Shortcut:  :kbd:`L`

Selects the stroke under the cursor along with all connected points belonging to the same stroke.

This is useful for quickly selecting an entire stroke for editing, transforming,
moving between layers, or applying material changes.

Deselect Linked
   Removes the linked stroke under the cursor from the selection.

   Shortcut: :kbd:`Shift-L`


.. _bpy.ops.grease_pencil.select_ends:

Select First/Last
=================

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Select --> First/Last`

These operators will toggle the selection of the first or last point(s) of the stroke(s) in the object.
This is useful to quickly find the start of a stroke.
