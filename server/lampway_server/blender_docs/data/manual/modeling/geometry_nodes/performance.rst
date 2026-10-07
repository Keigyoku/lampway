.. _geometry-nodes-performance:

**************************
Geometry Nodes Performance
**************************

Geometry Nodes can process large amounts of data efficiently, but performance depends heavily
on how node trees are structured and how much geometry is evaluated.

This page outlines common considerations and techniques for improving performance.


General Principles
==================

- Minimize the amount of geometry processed.
- Avoid unnecessary evaluations or repeated calculations.
- Prefer simple operations over complex ones when possible.
- Use fields efficiently to delay computation until needed.


Reduce Geometry Complexity
==========================

High geometry counts are one of the most common causes of slow performance.

- Use lower-resolution meshes where possible.
- Reduce subdivision levels.
- Limit the number of instances or points generated.
- Use :ref:`bpy.types.GeometryNodeRealizeInstances` only when necessary.

Keeping geometry lightweight ensures faster evaluation across the node tree.


Use Instances Instead of Real Geometry
======================================

Instancing is significantly more efficient than duplicating geometry.

- Use :ref:`bpy.types.GeometryNodeInstanceOnPoints` to place repeated geometry.
- Avoid converting instances to real geometry unless required.
- Perform operations on instances before realizing them.

Instances reduce memory usage and improve evaluation speed.


Limit Expensive Operations
==========================

Some nodes are more computationally expensive than others.

- Boolean operations can be slow on dense meshes.
- Proximity and raycast nodes may be costly depending on input size.
- Simulation zones evaluate every frame and can add overhead.

Use these nodes carefully and limit their input size where possible.


Control Field Evaluation
========================

Fields are evaluated lazily, but inefficient usage can still impact performance.

- Avoid recalculating the same field multiple times.
- Store intermediate results when reused.
- Use *Capture Attribute* to cache values.

Efficient field usage reduces redundant computation.


Use Selection to Limit Work
===========================

Restrict operations to only the necessary elements.

- Use the *Selection* input on nodes whenever possible.
- Avoid applying operations to entire geometry if only part needs modification.

This reduces the number of elements processed.


Optimize Node Tree Structure
============================

Well-structured node trees are easier to evaluate efficiently.

- Group related operations into node groups.
- Avoid unnecessary node chains.
- Remove unused nodes and connections.
- Keep data flow simple and direct.

Simpler graphs generally perform better.


Baking
======

:doc:`/modeling/geometry_nodes/baking` can significantly improve performance
by storing the result of expensive computations.

- Use simulation baking to cache results over time.
- Bake geometry that does not need to update every frame.
- Avoid recalculating complex node trees when results can be reused.

Baking trades flexibility for performance, so it is most useful once a setup is finalized.


Geometry Nodes Stack Limit
==========================

Geometry Nodes evaluation is subject to a stack limit.
This stack limit can be adjusted in the User Preferences if more resources are available.

- Deep or highly nested node trees may hit this limit.
- Recursive-like setups or excessive node group nesting can increase stack usage.

If the stack limit is reached, evaluation may fail or produce incomplete results.

To avoid this:

- Reduce node group nesting depth.
- Simplify overly complex node chains.
- Break large setups into smaller, separate systems when possible.


Viewport and Evaluation Settings
================================

Performance can also be affected by viewport settings.

- Lower viewport subdivision levels.
- Use simpler shading modes while working.
- Disable unnecessary modifiers during editing.

Reducing viewport load improves interactivity.


Profiling and Debugging
=======================

To identify bottlenecks:

- Use :ref:`bpy.types.SpaceNodeOverlay.show_timing` overlay to find slow nodes.
- Temporarily mute nodes to isolate slow operations.
- Reduce input sizes to test performance impact.
- Use simpler geometry to compare results.

Iterative testing helps pinpoint performance issues.


Notes
=====

- Performance depends on hardware, especially CPU and memory bandwidth.
- Complex procedural setups may require trade-offs between quality and speed.
- Optimizing early can help avoid costly redesigns later.
