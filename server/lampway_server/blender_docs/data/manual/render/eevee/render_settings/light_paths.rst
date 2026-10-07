***********
Light Paths
***********


Clamping
========

.. reference::

   :Panel:     :menuselection:`Render --> Light Paths --> Clamping`


Surface
-------

.. _bpy.types.SceneEEVEE.clamp_surface_direct:

Direct Light
   This option limits the maximum light intensity a surface can reflect.
   It reduces :term:`Aliasing` noise and :term:`Fireflies` at the cost of accuracy.
   Setting this option to 0.0 disables clamping altogether.
   Lower values have a greater effect on the resulting image than higher values.

.. _bpy.types.SceneEEVEE.clamp_surface_indirect:

Indirect Light
   Similar to **Direct Light** but limits the maximum light intensity reflected using
   ray-tracing and light-probes.
   This also limits the intensity of the world lighting since it is considered indirect light.

.. note::

   These options provide a way to limit :term:`Fireflies` and :term:`Aliasing`
   of highly reflective surfaces and dense volumes.
   However, as values are clamped, intentionally bright highlights may also be reduced.

   Care must be taken to balance firefly reduction against loss of desired brightness.


Volume
------

.. _bpy.types.SceneEEVEE.clamp_volume_direct:

Direct Light
   The same as *Surface Direct Light* but applied to volume direct lighting.

.. _bpy.types.SceneEEVEE.clamp_volume_indirect:

Indirect Light
   The same as *Surface Indirect Light* but applied to volume indirect lighting.


Intensity
=========

.. reference::

   :Panel:     :menuselection:`Render --> Light Paths --> Intensity`

The intensity controls scale the evaluated lighting contribution in EEVEE.
They do not modify ray depth, sampling, accumulation, or performance characteristics.

.. _bpy.types.SceneEEVEE.direct_light_intensity:

Direct Light
   Scales the contribution of direct lighting, including light sources that directly
   illuminate surfaces and volumes.

   Increasing this value strengthens highlights and direct illumination.
   Lowering it reduces the apparent strength of light sources without modifying
   their energy settings.

.. _bpy.types.SceneEEVEE.indirect_light_intensity:

Indirect Light
   Scales the contribution of indirect lighting, including bounced light from
   ray tracing and light probes.

   This affects global illumination and world lighting.
   It can be used to strengthen or weaken the perceived bounce light in a scene.

   The scaling is applied after clamping, preserving firefly suppression behavior.
   This makes the result behave similarly to a post-lighting compositing adjustment,
   while remaining consistent across dithered and blended materials.

   These controls are useful for adjusting lighting balance in large environments,
   fine-tuning indirect illumination, and balancing direct versus indirect contribution
   without modifying individual light settings
