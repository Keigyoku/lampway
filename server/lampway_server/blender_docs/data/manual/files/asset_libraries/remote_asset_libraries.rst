**********************
Remote Asset Libraries
**********************

A *Remote Asset Library* is an :ref:`Asset Library <what-is-asset-library>` with a few extra files, stored on a server so that it can be accessed remotely.

In this case, "Remote" means "reached through a network connection". It can be served from your own computer, it doesn't have to be far away.

A few examples:

- The online part of Blender's :ref:`Essentials <essentials-library>` asset library.
- A set of Geometry Nodes assets published by an independent creator for their supporters.
- The inventory of a furniture store, for kit-bashing or trying out in a 3D scan of your living room.


Downloading Assets
==================

Assets can be downloaded from wherever they are shown, for example:

- Asset Browser: right-click and choose "Download Asset".
- Asset Shelf: click the download button shown when you hover the mouse over the asset.
- 'Add' menu for Compositor Nodes: right-click the menu item for the asset, and choose 'Download Asset'.

Assets are downloaded to the :ref:`local cache directory <local-cache-dir>`. They are typically not meant for editing, as they are typically stripped down of all niceties to make the download as small as possible. To browse the asset cache, for example to remove asset files you once downloaded but no longer want, right-click on an asset in the Asset Browser and choose 'Open File Location'.


Limitations
===========

The following limitations apply to remote asset libraries:

- Each ``.blend`` file should be **independent**. Any external dependency, such as ``.png`` files for textures, must be :ref:`packed <pack-unpack-data>` into the blend file. It is fine if the ``.blend`` file contains multiple assets. The important thing is that *when the* ``.blend`` *file is downloaded, the assets in it should be usable without needing to download any other file*.
- Blender does not have the concept of **asset versions**. This means that after downloading an asset, Blender can only detect whether the remote library has the same or a different file. It could be an updated version, or they may have rolled back to an older version. It's also possible that the ``.blend`` file was somehow modified after downloading it. The only thing Blender knows is whether they are the same or not.


Ingredients of a Remote Asset Library
=====================================

A Remote Asset Library consists of the following ingredients:

1. **The assets.** These are ``.blend`` files with one or more :ref:`assets <what-is-asset>` in each file. Each ``.blend`` file needs to be independent of any other file, so no linking between files, and pack textures and other external files. Basically: to get an asset, it should be enough to only download the ``.blend`` file.
2. **The Listing.** These are ``.json`` files that Blender can create, describing which assets are available in the library. This listing also contains the catalogs.
3. **Preview Images.** These are the optional preview images shown to users in the asset browser and asset shelves. Should be at least 256x256 pixels and must use a WebP (preferred) or PNG format. While generating the listing, Blender will export the preview images to WebP files.


Creating a Remote Asset Library
===============================

A *remote* library can be any directory containing ``.blend`` files with assets, like a regular :ref:`asset library <what-is-asset-library>`.
It just needs a set of files called the **asset listing**, which Blender can generate.

From the asset library directory, run this command in a :ref:`terminal <command_line-launch-index>`:

.. code-block:: bash

  $ cd /path/to/asset-library
  $ blender -b -c asset_listing generate .

These can also be combined into one command:

.. code-block:: bash

  $ blender -b -c asset_listing generate /path/to/asset-library

This command should be run any time an asset or asset catalog changes. This includes edits (even re-saving the file), removing assets, or creating new assets.

After the listing generator has run, edit the ``_asset-library-meta.json`` file (any plain text editor will do), to update the asset library's name & contact information:

.. code-block:: json

   {
      "api_versions": {
         "v1": {
            "url": "_v1/asset-index.json",
            "hash": "SHA256:5ba68debdc34ece8ddb1ca6ea4c7acf3287b657c72da47277e09bd30e2c7d02e"
         }
      },
      "name": "My amazing Assets",       // <-- Edit this
      "contact": {
         "name": "Your Name",            // <-- Edit this
         "url": "https://example.org/",  // <-- Edit this
         "email": "example@example.org"  // <-- Edit this
      }
   }


Re-running the listing generator will retain this information, so you should only need to edit this once.


Serving a Remote Asset Library
==============================

For testing, run any of these commands from the asset library directory:

- **Blender:** ``blender -q -b --python-expr "import runpy, sys; sys.argv=[sys.argv[0], '-b', '127.0.0.1']; runpy.run_module('http.server', run_name='__main__')"``
- **Python:** ``python3 -m http.server``
- **PicoHTTP:** Download `picohttp`_ and run ``picohttp``.

For actually serving the files, any static web server (`nginx`_, `Apache`_) will do.

.. _picohttp: https://gitlab.com/dr.sybren/picohttp/-/releases
.. _nginx: https://nginx.org/
.. _Apache: https://httpd.apache.org/

Requirements to the Web Server
==============================

Whatever web server is used, it MUST provide the following:

- Indicate the size of each file in the ``Content-Length`` response header.
- Ignore query string parameters when serving static files. So ``some_file.blend?hash=abcdef`` should just serve the file ``some_file.blend`` (without ``?hash=abcdef`` in the filename).

It is highly recommended, but not required, to support `conditional requests`_ via either the ``Last-Modified`` / ``If-Modified-Since`` headers, and/or the ``ETag``/``If-None-Match`` headers.

This will greatly reduce the bandwidth used by Blender's periodic syncing of the asset listing. When that listing did not change, the server will just return ``304 Not Modified`` instead of re-transferring the files.

.. _conditional requests: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests
