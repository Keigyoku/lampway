.. _bpy.ops.import_curve.svg:

***************************
Import SVG as Curves (.svg)
***************************

.. reference::

   :Category:  Import-Export
   :Menu:      :menuselection:`File --> Import --> SVG as Curves (.svg)`

Imports a :abbr:`SVG (Scalable Vector Graphics)` file as one or more curve objects.

SVG files contain vector-based shapes commonly created in illustration programs
such as Inkscape or Adobe Illustrator. When imported into Blender, the paths in
the SVG file are converted into :doc:`curve objects </modeling/curves/introduction>`.
Each SVG path typically becomes a separate spline within the resulting curve object.

This allows vector artwork to be used for modeling, extrusion, or motion graphics
workflows. For example, imported curves can be extruded to create 3D text or
logos, used as paths for animation, or converted to meshes.

.. note::

   Currently the importer only supports SVG path geometry. Other SVG features such as
   gradients, fills, strokes, text objects, images, and filters are ignored during import.

.. note::

   Imported curves are created in the XY plane and scaled according to the SVG document
   units. Additional scaling or orientation adjustments may be required depending on
   the source file.
