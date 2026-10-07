.. _bpy.types.UserAssetLibrary:

***************
Asset Libraries
***************

Asset Libraries define locations where Blender searches for assets.

Asset libraries can point to directories on the local file system or to
online asset repositories. Once added, assets contained in those libraries
are available in the :doc:`/editors/asset_browser` and other asset selectors.

.. figure:: /images/asset_browser-asset_library_preferences.png

   Name and location of asset libraries in the Preferences.

To create a local asset library, create an empty directory and add it to the
:ref:`ui-list-view`. Any asset contained in blend-files within that directory
or its subdirectories will automatically become available in the Asset Browser.

The library name is only used within Blender to identify the asset library
and can be changed at any time.


Options
=======

.. _bpy.types.UserAssetLibrary.path:

Path
   Directory containing the asset library.

   Only available for local asset libraries.

.. _bpy.types.UserAssetLibrary.remote_url:

URL
   URL of the online asset library.

   Only available for online asset libraries.

.. _bpy.types.UserAssetLibrary.import_method:

Import Method
   Default method used when importing assets from this library.

   This setting is used unless overridden by the
   :ref:`Asset Browser <bpy.types.FileAssetSelectParams.import_method>`.

   This option is not available for built-in asset libraries.

   :ref:`Link <bpy.ops.wm.link>`
      Links the asset into the current blend-file.

      Linked assets remain read-only and continue to reference the original
      asset library. Changes made to the source asset are reflected in all
      files that link it.

      .. note::

         Linking is not supported for online asset libraries.

   :ref:`Append <bpy.ops.wm.append>`
      Creates an independent copy of the asset and all of its dependencies.

      Every imported asset is appended as new data, even if the same asset
      has already been imported previously.

      Dependencies include any data referenced by the asset, such as meshes,
      materials, node groups, objects, constraints, or drivers.

      Later changes made to the original asset library are not reflected in
      the appended copy.

   Pack
      Imports the asset as linked data and immediately packs it into the
      current blend-file.

      This creates a self-contained blend-file while preserving the behavior
      of linked assets during import.

      Useful when sharing files or archiving projects that should not depend
      on the original asset library.

.. _bpy.types.UserAssetLibrary.use_relative_path:

Relative Path
   Stores the library location as a relative path whenever possible.

   This is useful when the asset library resides alongside a project and may
   be moved together with it.


.. _essentials-library:

Essentials Library
==================

The built-in *Essentials* asset library provides assets that are included
with Blender.

.. _bpy.types.PreferencesAssetLibraries.use_online_essentials:

Include Online Essentials
   Includes additional assets hosted online in the *Essentials* library.

   Downloading these assets requires
   :ref:`Online Access <bpy.types.PreferencesSystem.use_online_access>`
   to be enabled in the Preferences.
