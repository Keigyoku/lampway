Freestyle Utilities (freestyle.utils)
=====================================

.. module:: freestyle.utils

This module contains helper functions used for Freestyle style module
writing.

.. toctree::
   :maxdepth: 1
   :caption: Submodules

   freestyle.utils.ContextFunctions.rst

.. function:: getCurrentScene()

   Returns the current scene.

   :return: The current scene.
   :rtype: :class:`bpy.types.Scene`


.. function:: integrate(func, it, it_end, integration_type)

   Returns a single value from a set of values evaluated at each 0D
   element of this 1D element.

   :param func: The UnaryFunction0D used to compute a value at each
      Interface0D.
   :type func: :class:`UnaryFunction0D`
   :param it: The Interface0DIterator used to iterate over the 0D
      elements of this 1D element. The integration will occur over
      the 0D elements starting from the one pointed by it.
   :type it: :class:`Interface0DIterator`
   :param it_end: The Interface0DIterator pointing the end of the 0D
      elements of the 1D element.
   :type it_end: :class:`Interface0DIterator`
   :param integration_type: The integration method used to compute a
      single value from a set of values.
   :type integration_type: :class:`IntegrationType`
   :return: The single value obtained for the 1D element. The return
      value type is float if func is of the :class:`UnaryFunction0DDouble`
      or :class:`UnaryFunction0DFloat` type, and int if func is of the
      :class:`UnaryFunction0DUnsigned` type.
   :rtype: int | float


.. function:: angle_x_normal(it: Interface0DIterator)

   unsigned angle between a Point's normal and the X axis, in radians
   
   :param it: An iterator over Interface0D objects.
   :type it: :class:`Interface0DIterator`
   :rtype: float

.. function:: bound(lower, x, higher)

   Returns x bounded by a maximum and minimum value. Equivalent to:
   return min(max(x, lower), higher)
   
   :param lower: Lower bound.
   :type lower: float
   :param x: Value to clamp.
   :type x: float
   :param higher: Upper bound.
   :type higher: float
   :rtype: float

.. function:: bounding_box(stroke)

   Returns the maximum and minimum coordinates (the bounding box) of the stroke's vertices
   
   :param stroke: A stroke.
   :type stroke: :class:`Stroke`
   :rtype: tuple[:class:`mathutils.Vector`, :class:`mathutils.Vector`]

.. function:: curvature_from_stroke_vertex(svert)

   The 3D curvature of an stroke vertex' underlying geometry
      The result is None or in the range [-inf, inf]
   
   :param svert: A stroke vertex.
   :type svert: :class:`StrokeVertex`
   :rtype: float | None

.. function:: find_matching_vertex(id, it)

   Finds the matching vertex, or returns None.
   
   :param id: The ID to match.
   :type id: :class:`Id`
   :param it: An iterator over candidate ViewEdges.
   :type it: :class:`AdjacencyIterator`
   :rtype: :class:`ViewEdge` | None

.. function:: get_chain_length(ve, orientation)

   Returns the 2d length of a given ViewEdge.
   
   :param ve: The ViewEdge whose chain length to compute.
   :type ve: :class:`ViewEdge`
   :param orientation: Direction in which to traverse the chain.
   :type orientation: bool
   :rtype: float

.. function:: get_object_name(stroke)

   Returns the name of the object that this stroke is drawn on.
   
   :param stroke: A stroke.
   :type stroke: :class:`Stroke`
   :rtype: str | None

.. function:: get_strokes()

   Get all strokes that are currently available

.. function:: get_test_stroke()

   Returns a static stroke object for testing 

.. function:: is_poly_clockwise(stroke)

   True if the stroke is orientated in a clockwise way, False otherwise
   
   :param stroke: A stroke whose orientation is tested.
   :type stroke: :class:`Stroke`
   :rtype: bool

.. function:: iter_distance_along_stroke(stroke)

   Yields the absolute distance along the stroke up to the current vertex.
   
   :param stroke: A stroke.
   :type stroke: :class:`Stroke`

.. function:: iter_distance_from_camera(stroke, range_min, range_max, normfac)

   Yields the distance to the camera relative to the maximum
   possible distance for every stroke vertex, constrained by
   given minimum and maximum values.
   
   :param stroke: A stroke.
   :type stroke: :class:`Stroke`
   :param range_min: Distances below this value are clamped to 0.
   :type range_min: float
   :param range_max: Distances above this value are clamped to 1.
   :type range_max: float
   :param normfac: Normalization factor applied to ``distance - range_min``.
   :type normfac: float

.. function:: iter_distance_from_object(stroke, location, range_min, range_max, normfac)

   yields the distance to the given object relative to the maximum
   possible distance for every stroke vertex, constrained by
   given minimum and maximum values.
   
   :param stroke: A stroke.
   :type stroke: :class:`Stroke`
   :param location: Reference location in 3D space.
   :type location: :class:`mathutils.Vector`
   :param range_min: Distances below this value are clamped to 0.
   :type range_min: float
   :param range_max: Distances above this value are clamped to 1.
   :type range_max: float
   :param normfac: Normalization factor applied to ``distance - range_min``.
   :type normfac: float

.. function:: iter_material_value(stroke, func, attribute)

   Yields a specific material attribute from the vertex' underlying material.
   
   :param stroke: A stroke.
   :type stroke: :class:`Stroke`
   :param func: A function returning a material for the iterator's current vertex.
   :type func: Callable[[:class:`Interface0DIterator`], :class:`Material`]
   :param attribute: The material attribute name (e.g. ``LINE``, ``DIFF``, ``ALPHA``).
   :type attribute: str

.. function:: iter_t2d_along_stroke(stroke)

   Yields the progress along the stroke.
   
   :param stroke: A stroke.
   :type stroke: :class:`Stroke`

.. function:: material_from_fedge(fe)

   Get the diffuse RGBA color from an FEdge.
   
   :param fe: An FEdge.
   :type fe: :class:`FEdge`
   :rtype: :class:`Material` | None

.. function:: normal_at_I0D(it: Interface0DIterator) -> Vector

   Normal at an Interface0D object. In contrast to Normal2DF0D this
      function uses the actual data instead of underlying Fedge objects.
   
   :param it: An iterator over Interface0D objects.
   :type it: :class:`Interface0DIterator`
   :rtype: :class:`mathutils.Vector`

.. function:: pairwise(iterable, types=None)

   Yields a tuple containing the previous and current object.
   
   :param iterable: An iterable of items.
   :type iterable: Iterable[Any]
   :param types: Container types for which the iterator's ``incremented()``
       method is used instead of standard tee-based pairing. When ``None``
       defaults to ``(Stroke, StrokeVertexIterator)``.
   :type types: tuple[type, ...] | None

.. function:: rgb_to_bw(r, g, b)

   Method to convert rgb to a bw intensity value.
   
   :param r: Red channel (0..1).
   :type r: float
   :param g: Green channel (0..1).
   :type g: float
   :param b: Blue channel (0..1).
   :type b: float
   :rtype: float

.. function:: simplify(points, tolerance)

   Simplifies a set of points.
   
   :param points: Points to simplify.
   :type points: Sequence[:class:`mathutils.Vector`]
   :param tolerance: Maximum allowed deviation from the original curve.
   :type tolerance: float
   :rtype: tuple

.. function:: stroke_curvature(it)

   Compute the 2D curvature at the stroke vertex pointed by the iterator 'it'.
   K = 1 / R
   where R is the radius of the circle going through the current vertex and its neighbors
   
   :param it: An iterator over a stroke's vertices.
   :type it: :class:`StrokeVertexIterator`

.. function:: stroke_normal(stroke)

   Compute the 2D normal at the stroke vertex pointed by the iterator
   'it'.  It is noted that Normal2DF0D computes normals based on
   underlying FEdges instead, which is inappropriate for strokes when
   they have already been modified by stroke geometry modifiers.
   
   The returned normals are dynamic: they update when the
   vertex position (and therefore the vertex normal) changes.
   for use in geometry modifiers it is advised to
   cast this generator function to a tuple or list
   
   :param stroke: A stroke.
   :type stroke: :class:`Stroke`

.. function:: tripplewise(iterable)

   Yields a tuple containing the current object and its immediate neighbors.
   
   :param iterable: An iterable of items.
   :type iterable: Iterable[Any]

.. class:: BoundingBox

   Object representing a bounding box consisting out of 2 2D vectors

   .. method:: inside(other)

      True if self inside other, False otherwise.
      
      :param other: Another bounding box to test containment against.
      :type other: :class:`BoundingBox`
      :rtype: bool

   .. classmethod:: from_sequence(sequence)

      BoundingBox from sequence of 2D or 3D Vector objects.
      
      :param sequence: An iterable of vectors to compute the box from.
      :type sequence: Iterable[:class:`mathutils.Vector`]
      :rtype: :class:`BoundingBox`

   .. details:: Special Methods

      .. method:: __repr__()

         :rtype: str



.. class:: StrokeCollector

   Collects and Stores stroke objects

   .. method:: shade(stroke)

      :param stroke: The stroke to collect.
      :type stroke: :class:`Stroke`



