.. _bpy.types.Cycles:
.. _bpy.ops.cycles:

##########
  Cycles
##########

Cycles is Blender's physically-based path tracer for production rendering.
It is designed to provide physically based results out-of-the-box,
with artistic control and flexible shading nodes for production needs.

.. figure:: /images/render_cycles_introduction_overview.jpg

To use Cycles, select it as the *Render Engine* in the Render properties.
For :doc:`GPU accelerated rendering </render/cycles/gpu_rendering>`,
enable compatible devices in :menuselection:`Preferences --> System --> Cycles Render Devices`.

.. seealso::

   The `Cycles website <https://www.cycles-renderer.org/>`__ with more information and a gallery.

.. toctree::
   :titlesonly:
   :maxdepth: 2

   render_settings/index.rst
   world_settings.rst
   object_settings/index.rst
   material_settings.rst
   Light Settings <light_settings.rst>
   gpu_rendering.rst
   baking.rst
   optimizations/index.rst
   osl/index.rst
   osl/camera.rst
