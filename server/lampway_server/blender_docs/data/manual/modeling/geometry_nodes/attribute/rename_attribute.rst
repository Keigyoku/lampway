.. index:: Geometry Nodes; Rename Attribute
.. _bpy.types.GeometryNodeRenameAttribute:

*********************
Rename Attribute Node
*********************

.. figure:: /images/node-types_GeometryNodeRenameAttribute.webp
   :align: right
   :alt: Rename Attribute node.

The *Rename Attribute* node renames an existing attribute or modifies the prefix
of multiple attributes on a geometry.

This is useful for reorganizing attribute names, resolving conflicts, or preparing
attributes for use in other nodes that expect specific naming conventions.


Inputs
======

Geometry
   Standard geometry input.

Mode
   Determines how attributes are renamed.

   :Single: Renames a single attribute using the provided names.
   :Prefix: Renames multiple attributes by replacing or adding a prefix.

Old
   The name or prefix of the attribute(s) to be renamed.

   - In *Single* mode, this is the exact attribute name.
   - In *Prefix* mode, this is the prefix to search for.

New
   The new name or prefix for the attribute(s).

   - In *Single* mode, this is the new attribute name.
   - In *Prefix* mode, this replaces the matched prefix.

Overwrite
   Allows renaming even if the destination name already exists.

   - When disabled, the operation will skip attributes that would conflict with existing names.
   - When enabled, existing attributes with the target name are overwritten.


Outputs
=======

Geometry
   Standard geometry output with renamed attributes applied.
