Freestyle Chaining Iterators (freestyle.chainingiterators)
==========================================================

.. module:: freestyle.chainingiterators

This module contains chaining iterators used for the chaining
operation to construct long strokes by concatenating feature edges
according to selected chaining rules.  The module is also intended to
be a collection of examples for defining chaining iterators in Python.

.. class:: ChainPredicateIterator

   Class hierarchy: :class:`freestyle.types.Iterator` >
   :class:`freestyle.types.ViewEdgeIterator` >
   :class:`freestyle.types.ChainingIterator` >
   :class:`ChainPredicateIterator`
   
   A "generic" user-controlled ViewEdge iterator. This iterator is in
   particular built from a unary predicate and a binary predicate.
   First, the unary predicate is evaluated for all potential next
   ViewEdges in order to only keep the ones respecting a certain
   constraint. Then, the binary predicate is evaluated on the current
   ViewEdge together with each ViewEdge of the previous selection. The
   first ViewEdge respecting both the unary predicate and the binary
   predicate is kept as the next one. If none of the potential next
   ViewEdge respects these two predicates, None is returned.
   
   .. method:: __init__(*args)
   
      Accepted call signatures:
   
      - ``__init__(upred, bpred, restrict_to_selection=True, restrict_to_unvisited=True, begin=None, orientation=True)``
      - ``__init__(brother)``
   
      Builds a ChainPredicateIterator from a unary predicate, a binary
      predicate, a starting ViewEdge and its orientation or using the copy constructor.
   
      :param upred: The unary predicate that the next ViewEdge must satisfy.
      :type upred: :class:`freestyle.types.UnaryPredicate1D`
      :param bpred: The binary predicate that the next ViewEdge must
         satisfy together with the actual pointed ViewEdge.
      :type bpred: :class:`freestyle.types.BinaryPredicate1D`
      :param restrict_to_selection: Indicates whether to force the chaining
         to stay within the set of selected ViewEdges or not.
      :type restrict_to_selection: bool
      :param restrict_to_unvisited: Indicates whether a ViewEdge that has
         already been chained must be ignored ot not.
      :type restrict_to_unvisited: bool
      :param begin: The ViewEdge from where to start the iteration.
      :type begin: :class:`freestyle.types.ViewEdge` | None
      :param orientation: If true, we'll look for the next ViewEdge among
         the ViewEdges that surround the ending ViewVertex of begin. If
         false, we'll search over the ViewEdges surrounding the ending
         ViewVertex of begin.
      :type orientation: bool
      :param brother: A ChainPredicateIterator object.
      :type brother: :class:`ChainPredicateIterator`



.. class:: ChainSilhouetteIterator

   Class hierarchy: :class:`freestyle.types.Iterator` >
   :class:`freestyle.types.ViewEdgeIterator` >
   :class:`freestyle.types.ChainingIterator` >
   :class:`ChainSilhouetteIterator`
   
   A ViewEdge Iterator used to follow ViewEdges the most naturally. For
   example, it will follow visible ViewEdges of same nature. As soon, as
   the nature or the visibility changes, the iteration stops (by setting
   the pointed ViewEdge to 0). In the case of an iteration over a set of
   ViewEdge that are both Silhouette and Crease, there will be a
   precedence of the silhouette over the crease criterion.
   
   .. method:: __init__(*args)
   
      Accepted call signatures:
   
      - ``__init__(restrict_to_selection=True, begin=None, orientation=True)``
      - ``__init__(brother)``
   
      Builds a ChainSilhouetteIterator from the first ViewEdge used for
      iteration and its orientation or the copy constructor.
   
      :param restrict_to_selection: Indicates whether to force the chaining
         to stay within the set of selected ViewEdges or not.
      :type restrict_to_selection: bool
      :param begin: The ViewEdge from where to start the iteration.
      :type begin: :class:`freestyle.types.ViewEdge` | None
      :param orientation: If true, we'll look for the next ViewEdge among
         the ViewEdges that surround the ending ViewVertex of begin. If
         false, we'll search over the ViewEdges surrounding the ending
         ViewVertex of begin.
      :type orientation: bool
      :param brother: A ChainSilhouetteIterator object.
      :type brother: :class:`ChainSilhouetteIterator`



.. class:: pyChainSilhouetteIterator

   Natural chaining iterator that follows the edges of the same nature
   following the topology of objects, with decreasing priority for
   silhouettes, then borders, then suggestive contours, then all other edge
   types.  A ViewEdge is only chained once.

   .. method:: init()

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



.. class:: pyChainSilhouetteGenericIterator

   Natural chaining iterator that follows the edges of the same nature
   following the topology of objects, with decreasing priority for
   silhouettes, then borders, then suggestive contours, then all other
   edge types.
   
   .. method:: __init__(stayInSelection=True, stayInUnvisited=True)
   
      Builds a pyChainSilhouetteGenericIterator object.
   
      :param stayInSelection: True if it is allowed to go out of the selection
      :type stayInSelection: bool
      :param stayInUnvisited: May the same ViewEdge be chained twice
      :type stayInUnvisited: bool

   .. method:: init()

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



.. class:: pyExternalContourChainingIterator

   Chains by external contour

   .. method:: checkViewEdge(ve, orientation)

      Tests whether a ViewEdge belongs to the external contour.
      
      :param ve: The ViewEdge to test.
      :type ve: :class:`ViewEdge`
      :param orientation: Iteration orientation.
      :type orientation: bool
      :rtype: bool

   .. method:: init()

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



.. class:: pySketchyChainSilhouetteIterator

   Natural chaining iterator with a sketchy multiple touch.  It chains the
   same ViewEdge multiple times to achieve a sketchy effect.
   
   .. method:: __init__(nRounds=3,stayInSelection=True)
   
      Builds a pySketchyChainSilhouetteIterator object.
   
      :param nRounds: Number of times every Viewedge is chained.
      :type nRounds: int
      :param stayInSelection: if False, edges outside of the selection can be chained.
      :type stayInSelection: bool

   .. method:: init()

   .. method:: make_sketchy(ve)

      Creates the sketchy effect by causing the chain to run from
      the start again. (loop over itself again)
      
      :param ve: The candidate ViewEdge, or None to fall back to the current edge.
      :type ve: :class:`ViewEdge` | None
      :rtype: :class:`ViewEdge` | None

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



.. class:: pySketchyChainingIterator

   Chaining iterator designed for sketchy style. It chains the same
   ViewEdge several times in order to produce multiple strokes per
   ViewEdge.

   .. method:: init()

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



.. class:: pyFillOcclusionsRelativeChainingIterator

   Chaining iterator that fills small occlusions
   
   .. method:: __init__(percent)
   
      Builds a pyFillOcclusionsRelativeChainingIterator object.
   
      :param percent: The maximal length of the occluded part, expressed
          in a percentage of the total chain length.
      :type percent: float

   .. method:: init()

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



.. class:: pyFillOcclusionsAbsoluteChainingIterator

   Chaining iterator that fills small occlusions
   
   .. method:: __init__(length)
   
      Builds a pyFillOcclusionsAbsoluteChainingIterator object.
   
      :param length: The maximum length of the occluded part in pixels.
      :type length: int

   .. method:: init()

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



.. class:: pyFillOcclusionsAbsoluteAndRelativeChainingIterator

   Chaining iterator that fills small occlusions regardless of the
   selection.
   
   .. method:: __init__(percent, l)
   
      Builds a pyFillOcclusionsAbsoluteAndRelativeChainingIterator object.
   
      :param percent: The maximal length of the occluded part as a
          percentage of the total chain length.
      :type percent: float
      :param l: Absolute length.
      :type l: float

   .. method:: init()

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



.. class:: pyFillQi0AbsoluteAndRelativeChainingIterator

   Chaining iterator that fills small occlusions regardless of the
   selection.
   
   .. method:: __init__(percent, l)
   
      Builds a pyFillQi0AbsoluteAndRelativeChainingIterator object.
   
      :param percent: The maximal length of the occluded part as a
          percentage of the total chain length.
      :type percent: float
      :param l: Absolute length.
      :type l: float

   .. method:: init()

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



.. class:: pyNoIdChainSilhouetteIterator

   Natural chaining iterator that follows the edges of the same nature
   following the topology of objects, with decreasing priority for
   silhouettes, then borders, then suggestive contours, then all other edge
   types.  It won't chain the same ViewEdge twice.
   
   .. method:: __init__(stayInSelection=True)
   
      Builds a pyNoIdChainSilhouetteIterator object.
   
      :param stayInSelection: True if it is allowed to go out of the selection
      :type stayInSelection: bool

   .. method:: init()

   .. method:: traverse(iter)

      Returns the next ViewEdge to chain.
      
      :param iter: An adjacency iterator over the candidate ViewEdges.
      :type iter: :class:`AdjacencyIterator`
      :return: The next ViewEdge, or None to stop chaining.
      :rtype: :class:`ViewEdge` | None



