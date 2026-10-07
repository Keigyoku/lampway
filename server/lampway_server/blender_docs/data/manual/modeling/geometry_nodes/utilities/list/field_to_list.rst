.. index:: Geometry Nodes; Field to List
.. _bpy.types.GeometryNodeFieldToList:

******************
Field to List Node
******************

.. figure:: /images/node-types_GeometryNodeFieldToList.webp
   :align: center
   :alt: Field to List node.

The *Field to List* node evaluates one or more fields and converts their values into lists.

Each field is evaluated for every element in the current context, and the
resulting values are collected into a list. This is useful when working with
nodes that operate on lists rather than fields.


Inputs
======

Field Inputs
   One or more field inputs to evaluate.
   Additional fields can be added in the node properties.


Properties
==========

Items
-----

A list of all input fields to be evaluated.

Each item definition creates a corresponding list output.

Socket Type
   The data type of the field to evaluate and the generated list values.


Outputs
=======

Each field defined in the node properties creates a corresponding list output.

The output list contains the evaluated value of the field for every element in
the current context.
