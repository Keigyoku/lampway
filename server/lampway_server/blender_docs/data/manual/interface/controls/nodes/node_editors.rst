.. _bpy.types.SpaceNodeEditor:

************
Node Editors
************

Header
======

The *Header* contains various menus, buttons and options, partially based on the current node tree type.

.. figure:: /images/interface_controls_nodes_introduction_header.png

   Common node editor header options.

View
   This menu changes your view of the editor.
Select
   This menu allows you to select a node or groups of nodes.
Add
   This menu allows you to add nodes.
Node
   This menu allows you to do things with selected nodes.

.. _bpy.types.SpaceNodeEditor.pin:

:bl-icon:`pinned` Pinned
   When enabled, the editor always displays the currently selected node tree,
   regardless of changes in the active object or scene.
   This allows you to edit a material, texture, or compositor node tree independently
   of what is selected in the 3D Viewport or which scene is active.
   Useful when working across multiple objects or scenes but wanting to keep the editor
   focused on one specific node tree.
Parent Node Tree
   Leaves the current :doc:`node group </interface/controls/nodes/groups>` and returns to the parent node group/tree.
Snapping
   Change options for snapping node positions to achieve a cleaner node tree layout.
   See :doc:`/interface/controls/nodes/arranging`.


.. _bpy.types.SpaceNodeOverlay.show_overlays:

Overlays
========

Overlays are information that is displayed on top of the nodes and node trees.
There is a toggle to show or hide all overlays for the node editor next to the overlay popover.

.. _bpy.types.SpaceNodeOverlay.show_wire_color:

Wire Colors
   Color node links based on their connected sockets.

.. _bpy.types.SpaceNodeOverlay.show_reroute_auto_labels:

Reroute Auto Labels
   Label :doc:`Reroute Nodes </interface/controls/nodes/types/layout/reroute>`
   based on the label of connected reroute nodes.

.. _bpy.types.SpaceNodeOverlay.show_context_path:

Context Path
   Display breadcrumbs in the upper left corner indicating the hierarchy location
   of the node tree/group that's currently being displayed.

.. _bpy.types.SpaceNodeEditor.show_annotation:

Annotations
   Displays :doc:`Annotations </interface/annotate_tool>` in the preview region.

.. _bpy.types.SpaceNodeOverlay.show_previews:

Previews
   Display each node's :ref:`interface-nodes-parts-preview` if the node's preview is also toggled.

.. _bpy.types.SpaceNodeOverlay.show_timing:

Timings
   Display each node's last execution time.
   This option is only available for compositing and geometry nodes.

   In the context of geometry nodes, see :ref:`modeling-geometry_nodes-inspection-timings`.

.. _bpy.types.SpaceNodeOverlay.show_render_size:

Render Region
   Displays a border showing the final render region defined in the scene.
   Space outside the render region appear shaded for reference.

.. _bpy.types.SpaceNodeOverlay.passepartout_alpha:

Passepartout Alpha
   Controls the opacity of the shaded area outside the render region.
   Higher values darken the outside area more, making the render region stand out.


Toolbar
=======

The *Toolbar* contains a set of tools that can be used in the node editor.

:ref:`Select <tool-select-tweak>`
   Select or move nodes and links.

   :ref:`Select Box <tool-select-box>`
      Select nodes or links by dragging a box around them.

   :ref:`Select Circle <tool-select-circle>`
      Select nodes or links by clicking or dragging with a circular brush.

   :ref:`Select Lasso <tool-select-lasso>`
      Select nodes or links by drawing a free-form lasso.

:ref:`Annotate <tool-annotate-freehand>`
   Draw free-hand annotation.

   :ref:`Annotate Line <tool-annotate-line>`
      Draw straight line annotation.
   :ref:`Annotate Polygon <tool-annotate-polygon>`
      Draw a polygon annotation.
   :ref:`Annotate Eraser <tool-annotate-eraser>`
      Erase previous drawn annotations.

Link Cuts
   Delete connections between nodes by drawing a line across the links.
   See :ref:`bpy.ops.node.links_cut` for more information.

Mute Links
   Mute connections between nodes by drawing a line across the links.
   Muted links are kept in place but ignored in evaluation.
   See :ref:`bpy.ops.node.links_mute` for more information.

Add Reroute
   Insert a :doc:`/interface/controls/nodes/types/layout/reroute`
   point on links by drawing a line across them.
   Reroute nodes help organize complex node trees by redirecting connections.


Sidebar
=======

The Sidebar region contains properties for
the currently selected node as well as node editor-specific settings.


Node
----

.. reference::

   :Panel:     :menuselection:`Sidebar --> Node`

The *Node* tab in the Sidebar contains properties that control the behavior
and appearance of the active node. Available options depend on the node
type and the editor.

.. figure:: /images/interface_controls_nodes_sidebar_item.png
   :align: center

   Node tab with a compositing Render Layers node selected.


Node
^^^^

.. _bpy.types.Node.name:

Name
   A unique identifier for the node within its node tree.
   This name must be unique and is used internally for references.

.. _bpy.types.Node.label:

Label
   A custom title displayed at the top of the node.
   Unlike the Name, this does not need to be unique and is useful
   for organizing complex node trees.

.. _bpy.types.Node.use_custom_color:
.. _bpy.types.Node.color:

Color
   By default, the node background color is defined by the current theme.
   Enable this option to override it with a custom color.

   Custom colors can provide visual cues to distinguish related nodes
   or highlight important parts of a node tree.

   The preset button next to the color field allows saving and reusing
   custom colors.

   Node Color Specials
      Contains :doc:`/interface/operators` related to custom node colors.

      .. _bpy.ops.node.node_copy_color:

      Copy to Selected
         Copies the color of the :term:`Active` node to all selected nodes.

.. _bpy.types.Node.show_options:

Show Options
   Shows or hides additional node-specific options in the node header,
   when available for that node type.

.. _bpy.types.Node.mute:

Mute
   Temporarily disables the node without removing it.
   When possible, the node is bypassed and its inputs are passed directly to its outputs.

.. _bpy.types.Node.warning_propagation:

Propagation :guilabel:`Geometry Nodes`
   Controls which messages from this node are propagated to the parent
   node group or modifier.

   :All Messages: Propagate informational messages, warnings, and errors.
   :Errors and Warnings: Propagate only warnings and errors.
   :Errors: Propagate only error messages.
   :None: Do not propagate any messages.


Properties
^^^^^^^^^^

The properties that are shown depend on the type of node selected,
e.g. a Mix node has different properties than a Mask node.


Custom Properties
^^^^^^^^^^^^^^^^^

Create and manage your own properties to store data in the active node.
See the :ref:`Custom Properties <files-data_blocks-custom-properties>` page for more information.


Tool
----

.. reference::

   :Panel:     :menuselection:`Sidebar region --> Tool`


Active Tool
^^^^^^^^^^^

The info in this panel changes with the selected tool.


View
----

.. reference::

   :Panel:     :menuselection:`Sidebar region --> View`


Annotations
^^^^^^^^^^^

You can select the Annotate tool in the Toolbar to make annotations in the node editor.
See :doc:`Annotate Tool </interface/annotate_tool>` for more info.


Navigating
==========

Navigating the node editors is done with the use of both mouse movement and keyboard shortcuts.

Pan :kbd:`MMB`
   Move the view up, down, left and right.
Zoom :kbd:`Ctrl-MMB`, :kbd:`Wheel`
   Move the camera forwards and backwards.
Frame Selected :kbd:`NumpadPeriod`
   Adjusts the zooms to fit only the selected nodes in the view.
Frame All :kbd:`Home`
   Adjusts the zoom to fit all nodes in the view.


Adding Nodes
============

.. reference::

   :Menu:      :menuselection:`Add`
   :Shortcut:  :kbd:`Shift-A`

Nodes are added via the *Add* menu in the editor's header or using a keyboard shortcut.

Nodes can also be added by dragging a connection from an existing node's input or output socket
and dropping the connection above an empty space instead of connecting to another socket.
This action will open a search menu with a list of compatible nodes
and their sockets that can be added and connected to the existing node.
Confirming the menu selection will add the node which can then be moved and placed.
