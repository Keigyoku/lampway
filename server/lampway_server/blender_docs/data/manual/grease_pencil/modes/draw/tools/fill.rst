.. _tool-grease-pencil-draw-fill:

*********
Fill Tool
*********

.. reference::

   :Mode:      Draw Mode
   :Tool:      :menuselection:`Toolbar --> Fill`

The Fill tool creates filled Grease Pencil strokes by detecting enclosed
regions formed by existing strokes.

Depending on the selected *Fill Solver*, the boundary can be computed from
the stroke geometry or from a pixel-based representation, allowing fills to
work with both clean line art and more complex drawings.

The Fill tool uses any of the Grease Pencil *Fill* draw mode brushes.
Activating a brush from an asset shelf or brush selector also activates this
tool for convenience.


Tool Settings
=============

Brush Asset
-----------

The asset selector can be used to open a pop-up asset browser to select the active brush asset for the tool.

See :ref:`brush-management-utility-operators` for more information.


Brush Settings
--------------

You can also configure the brush's main settings exposed in the Tool Settings for convenience.

.. _bpy.types.BrushGpencilSettings.fill_direction:

Direction :kbd:`Ctrl`
   Determines which side of the detected boundary is filled.

   :Normal:
      Fill the enclosed region under the cursor.
   :Inverted:
      Fill the region outside the detected boundary. This is useful for
      filling the background around a drawing.

Size :guilabel:`Delaunay`
   Maximum distance used to search for an enclosed region around the cursor.

.. _bpy.types.BrushGpencilSettings.fill_factor:

Precision :guilabel:`Pixel`
   Controls the accuracy of the pixel-based boundary detection.

   Higher values produce more accurate fills at the cost of increase computation time.

.. _bpy.types.BrushGpencilSettings.dilate:

Dilate/Contract :guilabel:`Pixel`
   Expand or shrink the detected fill region relative to the boundary strokes.

Thickness :guilabel:`Pixel`
   Thickness of the boundary strokes used by the *Pixel* fill solver.


Advanced
^^^^^^^^

.. _bpy.types.BrushGpencilSettings.fill_solver:

Fill Solver
   Method used to detect the fill region.

   :Delaunay:
      Uses the stroke geometry directly to compute enclosed regions.
      Produces accurate fills that are independent of viewport resolution.
   :Pixel:
      Rasterizes the strokes and performs a flood fill.
      Useful for sketches or drawings where geometric boundaries are less reliable.

Size Unit :guilabel:`Delaunay`
   Controls how the brush *Size* is measured.

   :View:
      Measure the brush *Size* in screen space.
   :Scene:
      Measure the brush *Size* in scene units.

      The brush size remains constant regardless of the viewport zoom level.
      The unit system is configured in the :ref:`Scene Units <bpy.types.UnitSettings>`.

.. _bpy.types.BrushGpencilSettings.fill_draw_mode:

Boundary
   Determines which strokes are considered when detecting fill boundaries.

   :All: Use both strokes and fill guide strokes.
   :Strokes: Use only strokes.
   :Edit Lines: Use only fill guide strokes.

   .. _bpy.types.BrushGpencilSettings.show_fill_boundary:

   :bl-icon:`hide_on` / :bl-icon:`hide_off` Show Lines
      Display the auxiliary lines used to compute the fill boundary.

.. _bpy.types.BrushGpencilSettings.fill_layer_mode:

Layers
   Determines which :doc:`Layers </grease_pencil/properties/layers>`
   contribute to the fill boundary.

   :Visible: Calculate boundaries using all visible layers.
   :Active: Calculate boundaries using only the active layer.
   :Layer Above: Calculate boundaries using the layer above the active layer.
   :Layer Below: Calculate boundaries using the layer below the active layer.
   :All Above: Calculate boundaries using all layers above the active layer.
   :All Below: Calculate boundaries using all layers below the active layer.

.. _bpy.types.BrushGpencilSettings.fill_simplify_level:

Simplify :guilabel:`Pixel`
   Reduce the complexity of the detected boundary before filling.

   Higher values improve performance but may reduce the accuracy of the filled region.

.. _bpy.types.BrushGpencilSettings.show_fill:
.. _bpy.types.BrushGpencilSettings.fill_threshold:

Ignore Transparent
   Ignore strokes whose material opacity falls below the specified threshold
   when calculating fill boundaries.

   The slider controls the opacity threshold used to consider a material transparent.

.. _bpy.types.BrushGpencilSettings.use_fill_limit:

Limit to Viewport :guilabel:`Pixel`
   Fill only regions visible in the viewport.

.. _bpy.types.BrushGpencilSettings.use_auto_remove_fill_guides:

Auto-Remove Fill Guides
   Automatically remove manually created fill guide strokes after creating a fill.


Gap Closure
"""""""""""

Gap closure generates temporary helper lines to automatically close small
gaps between strokes, allowing open regions to be filled.

.. _bpy.types.BrushGpencilSettings.fill_internal_gaps:

Internal Gaps
   Stop helper lines at internal gaps.

.. _bpy.types.BrushGpencilSettings.fill_gap_factor:

Detection Factor
   Controls the sensitivity of gap detection.

   Higher values detect more gaps, which can result in smaller fill regions.

.. _bpy.types.BrushGpencilSettings.extend_stroke_factor:

Size :guilabel:`Pixel`
   Maximum distance used by the selected gap closure method when creating
   temporary helper lines.

.. _bpy.types.BrushGpencilSettings.fill_extend_mode:

Mode :kbd:`S` :guilabel:`Pixel`
   Method used to generate temporary helper lines.

   :Radius:
      Connect nearby open stroke endpoints that fall within the specified radius.
   :Extend:
      Extend open stroke ends until they intersect another stroke or reach
      the specified distance.

.. _bpy.types.BrushGpencilSettings.show_fill_extend:

Visual Aids :guilabel:`Pixel`
   Display the temporary helper lines used for gap closure.

.. _bpy.types.BrushGpencilSettings.use_collide_strokes:

Strokes Collision :kbd:`D` :guilabel:`Pixel`
   Stop extending helper lines when they intersect an existing stroke.


Usage
=====

Selecting a Brush and Material
------------------------------

In the Tool Settings select the brush, material and color type to use with the tool.
The Fill tool uses *Fill Brush* types.
See :ref:`grease-pencil-draw-common-options` for more information.


Filling Areas
-------------

Click :kbd:`LMB` in a closed stroke area. The tool will automatically calculate
the boundary and create a new closed stroke filled with the material selected.

.. list-table::

   * - .. figure:: /images/grease-pencil_modes_draw_tools_fill_example-01.png
          :width: 200px

          Original Drawing.

     - .. figure:: /images/grease-pencil_modes_draw_tools_fill_example-02.png
          :width: 200px

          Use the fill tool to leak materials on closed areas.

     - .. figure:: /images/grease-pencil_modes_draw_tools_fill_example-03.png
          :width: 200px

          Final filled drawing.


Fill Guides
-----------

If you have a large gap in an area that you want fill,
you can add fill guides manually, a temporary auxiliary lines for closing open shapes.
To create a fill guide stroke use :kbd:`Alt-LMB` and draw a line to close the desired area.

.. list-table::

   * - .. figure:: /images/grease-pencil_modes_draw_tools_fill_boundary-strokes-01.png
          :width: 200px

          Original drawing.

     - .. figure:: /images/grease-pencil_modes_draw_tools_fill_boundary-strokes-02.png
          :width: 200px

          Add fill guide to close open areas (red lines).

     - .. figure:: /images/grease-pencil_modes_draw_tools_fill_boundary-strokes-03.png
          :width: 200px

          Use the Fill tool to leak material on the new closed area.

When you are satisfied with the fill result you can delete the fill guide using
the *Clean Up* tool in the :doc:`Grease Pencil Menu </grease_pencil/modes/edit/grease_pencil_menu>` in Edit Mode.


Automatic Gap Closure
---------------------

A more automatic way to close gaps in an area that you want fill is using temporarily helper lines.
There are two method to use "Radius" or "Extend"

*Radius* use temporary auxiliary lines calculated from the radius of nearby open points to close open shapes.
Set the size more than zero to control the circle size over opened points
(the circle will disappear when the line close the gap).
Click over the area you want to be filled and change the length of the strokes using
:kbd:`PageUp` :kbd:`PageDown` or :kbd:`Wheel`.
When you are satisfied with the length and you are sure the temporarily strokes cross each other,
click again to fill the area.

.. list-table::

   * - .. figure:: /images/grease-pencil_modes_draw_tools_fill_extended-strokes-01.png
          :width: 200px

          Original Drawing.

     - .. figure:: /images/grease-pencil_modes_draw_tools_fill_radius-02.png
          :width: 200px

          Use Radius mode to close open areas (Red circles and cyan lines).

     - .. figure:: /images/grease-pencil_modes_draw_tools_fill_radius-03.png
          :width: 200px

          Use Fill Tool to leak material on the new closed area.

*Extend* use temporary auxiliary lines extending the actual strokes ends for closing open shapes.
Set the size more than zero to use the extended lines, click over the area you want to be filled
and change the length of the strokes using :kbd:`PageUp`/:kbd:`PageDown`, :kbd:`Wheel` or a pen's :kbd:`MMB`.
When you are satisfied with the length and you are sure the temporarily strokes cross each other,
click again to fill the area.

.. list-table::

   * - .. figure:: /images/grease-pencil_modes_draw_tools_fill_extended-strokes-01.png
          :width: 200px

          Original Drawing.

     - .. figure:: /images/grease-pencil_modes_draw_tools_fill_extended-strokes-02.png
          :width: 200px

          Use Extend mode to close open areas (cyan lines).

     - .. figure:: /images/grease-pencil_modes_draw_tools_fill_extended-strokes-03.png
          :width: 200px

          Use Fill Tool to leak material on the new closed area.


.. Switch to Draw Tool
.. -------------------

.. Use :kbd:`Ctrl-LMB` to change temporary to the active draw tool.
.. For example to manually cover small areas difficult to reach for the Fill tool.
.. See :doc:`Draw Tool </grease_pencil/modes/draw/tools/draw>` for more information.
