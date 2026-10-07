BlendDataPathMeta
=================

.. currentmodule:: bpy.types

.. class:: BlendDataPathMeta

   Metadata about a file path visited by :class:`bpy.types.BlendData.file_path_foreach`.

   .. attribute:: is_cache

      True when the path is a cache file, like the image texture cache. These paths can not be edited.
      
      :type: bool


   .. attribute:: is_expanded

      True when the path was expanded from a UDIM tile or sequence frame. These paths can not be edited.
      
      :type: bool


   .. attribute:: is_readonly

      True when the path is read-only and can not be edited.
      
      :type: bool




