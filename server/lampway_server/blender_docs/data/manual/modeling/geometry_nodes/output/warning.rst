.. index:: Geometry Nodes; Warning
.. _bpy.types.GeometryNodeWarning:
.. --- copy below this line ---

************
Warning Node
************

.. figure:: /images/node-types_GeometryNodeWarning.webp
   :align: right
   :alt: Warning Node.

The *Warning* node outputs a custom message that is displayed when the node tree
is evaluated.

This allows node groups to communicate expectations, assumptions, or error
conditions, such as required input ranges, missing data, or unsupported
configurations.

By default, warnings are propagated through parent node groups.
This behavior can be controlled with the
:ref:`bpy.types.Node.warning_propagation` setting on each node.


Inputs
======

Show
   Controls whether the warning is displayed.

   When disabled, the warning is suppressed.

Message
   Text of the warning message.

   This can be used to describe invalid inputs, required conditions,
   or other information relevant to users of the node group.


Properties
==========

Warning Type
   Severity of the warning.

   The warning type also determines the icon used when the message is displayed.

   :Info:
      Informational message that does not indicate a problem.
   :Warning:
      Indicates a potential issue that may produce unexpected results.
   :Error:
      Indicates an invalid configuration that is likely to produce incorrect results.


Outputs
=======

Show
   Passes through the *Show* input.

   This can be used to combine or forward warning conditions to other nodes.


.. --- geometry nodes specific ---

Usage
=====

When used inside a Geometry Nodes tree, warnings are displayed in the
:ref:`modifiers-geometry-nodes-warnings` panel of the Geometry Nodes modifier.
