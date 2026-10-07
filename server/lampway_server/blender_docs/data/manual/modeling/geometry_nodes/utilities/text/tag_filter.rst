.. index:: Geometry Nodes; Tag Filter
.. _bpy.types.GeometryNodeTagFilter:
.. --- copy below this line ---

***************
Tag Filter Node
***************

.. figure:: /images/node-types_GeometryNodeTagFilter.webp
   :align: center
   :alt: Tag Filter node.

The *Tag Filter* node checks whether a list of tags matches a tag filter.

A tag filter consists of one or more tag names separated by commas. The node
returns true when any tag in the filter exists in the input tag list.


Inputs
======

Tag Filter
   Comma-separated list of tag names to match.

   Whitespace around tag names is ignored. An empty filter matches all tag lists.

Tags
   List of tags to evaluate.


Outputs
=======

Match
   True when any tag in the *Tag Filter* exists in the input *Tags* list, otherwise false.


Examples
========

- ``"metal"`` matches tag lists containing ``metal``.
- ``"metal, painted"`` matches tag lists containing either ``metal`` or ``painted``.
- ``""`` (an empty filter) always matches.
