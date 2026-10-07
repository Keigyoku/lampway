.. _bpy.types.RenderSettings.engine:

##################
  Render Engines
##################

Blender includes multiple render engines, each designed for different workflows
and levels of visual fidelity.

Choosing the appropriate engine depends on the project requirements,
such as realism, performance, and interactivity.


Overview
========

Blender provides the following render engines:

.. toctree::
   :maxdepth: 1
   :class: toc-list

   eevee/index.rst
   cycles/index.rst
   workbench/index.rst

Each engine uses a different rendering approach and is optimized for specific tasks.

More renderers from third-party developers are available as
:doc:`add-ons </editors/preferences/extensions>`.
Each renderer has its own render settings to control render quality and performance.


Choosing a Render Engine
========================

The active render engine can be selected in the :ref:`Render Properties <bpy.types.RenderSettings.engine>`.

Consider the following when choosing an engine:

- **Realism vs Performance**:
  Cycles provides physically accurate rendering, while Eevee prioritizes real-time performance.

- **Viewport Interactivity**:
  Eevee and Workbench are faster for interactive workflows.

- **Final Output vs Preview**:
  Cycles is typically used for final renders, while Eevee or Workbench may be used during setup.


Engine Comparison
=================

.. list-table::
   :header-rows: 1

   * - Engine
     - Type
     - Strengths
     - Typical Use Cases

   * - Eevee
     - Real-time rasterization
     - Fast, interactive, supports many modern effects
     - Animation, previews, stylized rendering, real-time workflows

   * - Cycles
     - Path tracing
     - Physically accurate lighting, realistic materials and shadows
     - Final renders, photorealism, VFX

   * - Workbench
     - Basic rasterization
     - Very fast, simple shading options
     - Modeling, layout, technical previews


Switching Engines
=================

Switching render engines may change available settings, materials,
and rendering behavior.

- Some features are engine-specific.
- Materials may appear differently between engines.
- Certain nodes or effects may only be supported in specific engines.

It is recommended to choose a render engine early in production
to avoid workflow inconsistencies.
