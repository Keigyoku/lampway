.. index:: Nodes; Get Nested Bundle Paths Node
.. _bpy.types.NodeGetNestedBundlePaths:
.. --- copy below this line ---

****************************
Get Nested Bundle Paths Node
****************************

.. figure:: /images/node-types_NodeGetNestedBundlePaths.webp
   :align: right
   :alt: Get Nested Bundle Paths node.

The *Get Nested Bundle Paths* node searches a bundle and any nested bundles,
returning the paths to items that match the specified filter.

This is useful for locating typed bundles or values without requiring them
to exist at a fixed location within the bundle hierarchy.

.. tip::

   This node searches recursively through nested bundles, making it useful
   for locating typed bundles regardless of where they are stored in the
   bundle hierarchy.


Inputs
======

Bundle
   Bundle to search.

Mode
   Determines which bundle items are matched.

   :All: Return the paths to all items.
   :Bundle Type: Return the paths to typed bundles matching the specified type.
   :Data Type: Return the paths to values with the specified data type.

Pattern Mode :guilabel:`Bundle Type`
   How bundle types are matched.

   :Exact:
      Match bundles whose type exactly matches the specified type.
   :Wildcard:
      Match bundles whose type matches the specified pattern.

      The pattern may contain a single wildcard character (``*``).

Bundle Type :guilabel:`Bundle Type`
   Bundle type or pattern to search for.

Data Type :guilabel:`Data Type`
   Data type of bundle values to search for.


Outputs
=======

Paths
   List of paths to the matching bundle items.
