.. _bpy.ops.armature.duplicate_rename:

********************
Duplicate and Rename
********************

.. reference::

   :Mode:      Edit Mode
   :Menu:      :menuselection:`Armature --> Duplicate and Rename`

Duplicates the selected bones and automatically renames the copies by replacing part of their names.

This operator behaves similarly to :ref:`bpy.ops.armature.duplicate_move`,
preserving parenting and connectivity relationships between duplicated bones where possible.

The duplicated bones become selected and can immediately be repositioned.

This is useful for creating mirrored rigs, duplicated bone chains, or alternative naming variants.


Options
=======

Flip Names
   Attempts to automatically flip directional suffixes in duplicated bone names.

   For example, names ending in ``.L`` may be renamed to ``.R``.

   This is useful for creating mirrored left/right bone chains.

Search
   Text to search for in the original bone names.

   Matching text is replaced in the duplicated bone names.

Replace
   Replacement text inserted in place of the search term.

   If left empty, the matching search term is removed from the duplicated bone names.
