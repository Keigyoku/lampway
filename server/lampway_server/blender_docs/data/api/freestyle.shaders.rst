Freestyle Shaders (freestyle.shaders)
=====================================

.. module:: freestyle.shaders

This module contains stroke shaders used for creation of stylized
strokes.  It is also intended to be a collection of examples for
shader definition in Python.

User-defined stroke shaders inherit the
:class:`freestyle.types.StrokeShader` class.

.. class:: BackboneStretcherShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`BackboneStretcherShader`
   
   [Geometry shader]
   
   .. method:: __init__(amount=2.0)
   
      Builds a BackboneStretcherShader object.
   
      :param amount: The stretching amount value.
      :type amount: float
   
   .. method:: shade(stroke)
   
      Stretches the stroke at its two extremities and following the
      respective directions: v(1)v(0) and v(n-1)v(n).
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: BezierCurveShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`BezierCurveShader`
   
   [Geometry shader]
   
   .. method:: __init__(error=4.0)
   
      Builds a BezierCurveShader object.
   
      :param error: The error we're allowing for the approximation. This
        error is the max distance allowed between the new curve and the
        original geometry.
      :type error: float
   
   .. method:: shade(stroke)
   
      Transforms the stroke backbone geometry so that it corresponds to a
      Bezier Curve approximation of the original backbone geometry.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: BlenderTextureShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`BlenderTextureShader`
   
   [Texture shader]
   
   .. method:: __init__(texture)
   
      Builds a BlenderTextureShader object.
   
      :param texture: A line style texture slot or a shader node tree to define a set of textures.
      :type texture: :class:`bpy.types.LineStyleTextureSlot` | :class:`bpy.types.ShaderNodeTree`
   
   .. method:: shade(stroke)
   
      Assigns a blender texture slot to the stroke  shading in order to
      simulate marks.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: CalligraphicShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`CalligraphicShader`
   
   [Thickness Shader]
   
   .. method:: __init__(thickness_min, thickness_max, orientation, clamp)
   
      Builds a CalligraphicShader object.
   
      :param thickness_min: The minimum thickness in the direction
         perpendicular to the main direction.
      :type thickness_min: float
      :param thickness_max: The maximum thickness in the main direction.
      :type thickness_max: float
      :param orientation: The 2D vector giving the main direction.
      :type orientation: :class:`mathutils.Vector`
      :param clamp: If true, the strokes are drawn in black when the stroke
         direction is between -90 and 90 degrees with respect to the main
         direction and drawn in white otherwise. If false, the strokes
         are always drawn in black.
      :type clamp: bool
   
   .. method:: shade(stroke)
   
      Assigns thicknesses to the stroke vertices so that the stroke looks
      like made with a calligraphic tool, i.e. the stroke will be the
      thickest in a main direction, and the thinnest in the direction
      perpendicular to this one, and an interpolation in between.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: ColorNoiseShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`ColorNoiseShader`
   
   [Color shader]
   
   .. method:: __init__(amplitude, period)
   
      Builds a ColorNoiseShader object.
   
      :param amplitude: The amplitude of the noise signal.
      :type amplitude: float
      :param period: The period of the noise signal.
      :type period: float
   
   .. method:: shade(stroke)
   
      Shader to add noise to the stroke colors.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: ConstantColorShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`ConstantColorShader`
   
   [Color shader]
   
   .. method:: __init__(red, green, blue, alpha=1.0)
   
      Builds a ConstantColorShader object.
   
      :param red: The red component.
      :type red: float
      :param green: The green component.
      :type green: float
      :param blue: The blue component.
      :type blue: float
      :param alpha: The alpha value.
      :type alpha: float
   
   .. method:: shade(stroke)
   
      Assigns a constant color to every vertex of the Stroke.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: ConstantThicknessShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`ConstantThicknessShader`
   
   [Thickness shader]
   
   .. method:: __init__(thickness)
   
      Builds a ConstantThicknessShader object.
   
      :param thickness: The thickness that must be assigned to the stroke.
      :type thickness: float
   
   .. method:: shade(stroke)
   
      Assigns an absolute constant thickness to every vertex of the Stroke.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: ConstrainedIncreasingThicknessShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`ConstrainedIncreasingThicknessShader`
   
   [Thickness shader]
   
   .. method:: __init__(thickness_min, thickness_max, ratio)
   
      Builds a ConstrainedIncreasingThicknessShader object.
   
      :param thickness_min: The minimum thickness.
      :type thickness_min: float
      :param thickness_max: The maximum thickness.
      :type thickness_max: float
      :param ratio: The thickness/length ratio that we don't want to exceed. 
      :type ratio: float
   
   .. method:: shade(stroke)
   
      Same as the :class:`IncreasingThicknessShader`, but here we allow
      the user to control the thickness/length ratio so that we don't get
      fat short lines.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: GuidingLinesShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`GuidingLinesShader`
   
   [Geometry shader]
   
   .. method:: __init__(offset)
   
      Builds a GuidingLinesShader object.
   
      :param offset: The line that replaces the stroke is initially in the
         middle of the initial stroke bounding box. offset is the value
         of the displacement which is applied to this line along its
         normal.
      :type offset: float
   
   .. method:: shade(stroke)
   
      Shader to modify the Stroke geometry so that it corresponds to its
      main direction line. This shader must be used together with the
      splitting operator using the curvature criterion. Indeed, the
      precision of the approximation will depend on the size of the
      stroke's pieces. The bigger the pieces are, the rougher the
      approximation is.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: IncreasingColorShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`IncreasingColorShader`
   
   [Color shader]
   
   .. method:: __init__(red_min, green_min, blue_min, alpha_min, red_max, green_max, blue_max, alpha_max)
   
      Builds an IncreasingColorShader object.
   
      :param red_min: The first color red component.
      :type red_min: float
      :param green_min: The first color green component.
      :type green_min: float
      :param blue_min: The first color blue component.
      :type blue_min: float
      :param alpha_min: The first color alpha value.
      :type alpha_min: float
      :param red_max: The second color red component.
      :type red_max: float
      :param green_max: The second color green component.
      :type green_max: float
      :param blue_max: The second color blue component.
      :type blue_max: float
      :param alpha_max: The second color alpha value.
      :type alpha_max: float
   
   .. method:: shade(stroke)
   
      Assigns a varying color to the stroke. The user specifies two
      colors A and B. The stroke color will change linearly from A to B
      between the first and the last vertex.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: IncreasingThicknessShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`IncreasingThicknessShader`
   
   [Thickness shader]
   
   .. method:: __init__(thickness_A, thickness_B)
   
      Builds an IncreasingThicknessShader object.
   
      :param thickness_A: The first thickness value.
      :type thickness_A: float
      :param thickness_B: The second thickness value.
      :type thickness_B: float
   
   .. method:: shade(stroke)
   
      Assigns thicknesses values such as the thickness increases from a
      thickness value A to a thickness value B between the first vertex
      to the midpoint vertex and then decreases from B to a A between
      this midpoint vertex and the last vertex. The thickness is
      linearly interpolated from A to B.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: PolygonalizationShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`PolygonalizationShader`
   
   [Geometry shader]
   
   .. method:: __init__(error)
   
      Builds a PolygonalizationShader object.
   
      :param error: The error we want our polygonal approximation to have
         with respect to the original geometry. The smaller, the closer
         the new stroke is to the original one. This error corresponds to
         the maximum distance between the new stroke and the old one.
      :type error: float
   
   .. method:: shade(stroke)
   
      Modifies the Stroke geometry so that it looks more "polygonal".
      The basic idea is to start from the minimal stroke approximation
      consisting in a line joining the first vertex to the last one and
      to subdivide using the original stroke vertices until a certain
      error is reached.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: RoundCapShader


   .. method:: round_cap_thickness(x)

      :param x: A value in [0, 1] along the cap (0 at base, 1 at tip).
      :type x: float
      :rtype: float

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: SamplingShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`SamplingShader`
   
   [Geometry shader]
   
   .. method:: __init__(sampling)
   
      Builds a SamplingShader object.
   
      :param sampling: The sampling to use for the stroke resampling.
      :type sampling: float
   
   .. method:: shade(stroke)
   
      Resamples the stroke.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: SmoothingShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`SmoothingShader`
   
   [Geometry shader]
   
   .. method:: __init__(num_iterations=100, factor_point=0.1, factor_curvature=0.0, factor_curvature_difference=0.2, aniso_point=0.0, aniso_normal=0.0, aniso_curvature=0.0, carricature_factor=1.0)
   
      Builds a SmoothingShader object.
   
      :param num_iterations: The number of iterations.
      :type num_iterations: int
      :param factor_point: 0.1
      :type factor_point: float
      :param factor_curvature: 0.0
      :type factor_curvature: float
      :param factor_curvature_difference: 0.2
      :type factor_curvature_difference: float
      :param aniso_point: 0.0
      :type aniso_point: float
      :param aniso_normal: 0.0
      :type aniso_normal: float
      :param aniso_curvature: 0.0
      :type aniso_curvature: float
      :param carricature_factor: 1.0
      :type carricature_factor: float
   
   .. method:: shade(stroke)
   
      Smooths the stroke by moving the vertices to make the stroke
      smoother. Uses curvature flow to converge towards a curve of
      constant curvature. The diffusion method we use is anisotropic to
      prevent the diffusion across corners.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: SpatialNoiseShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`SpatialNoiseShader`
   
   [Geometry shader]
   
   .. method:: __init__(amount, scale, num_octaves, smooth, pure_random)
   
      Builds a SpatialNoiseShader object.
   
      :param amount: The amplitude of the noise.
      :type amount: float
      :param scale: The noise frequency.
      :type scale: float
      :param num_octaves: The number of octaves
      :type num_octaves: int
      :param smooth: True if you want the noise to be smooth.
      :type smooth: bool
      :param pure_random: True if you don't want any coherence.
      :type pure_random: bool
   
   .. method:: shade(stroke)
   
      Spatial Noise stroke shader. Moves the vertices to make the stroke
      more noisy.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: SquareCapShader


   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: StrokeTextureStepShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`StrokeTextureStepShader`
   
   [Texture shader]
   
   .. method:: __init__(step)
   
      Builds a StrokeTextureStepShader object.
   
      :param step: The spacing along the stroke.
      :type step: float
   
   .. method:: shade(stroke)
   
      Assigns a spacing factor to the texture coordinates of the Stroke.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: ThicknessNoiseShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`ThicknessNoiseShader`
   
   [Thickness shader]
   
   .. method:: __init__(amplitude, period)
   
      Builds a ThicknessNoiseShader object.
   
      :param amplitude: The amplitude of the noise signal.
      :type amplitude: float
      :param period: The period of the noise signal.
      :type period: float
   
   .. method:: shade(stroke)
   
      Adds some noise to the stroke thickness.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: TipRemoverShader

   Class hierarchy: :class:`freestyle.types.StrokeShader` > :class:`TipRemoverShader`
   
   [Geometry shader]
   
   .. method:: __init__(tip_length)
   
      Builds a TipRemoverShader object.
   
      :param tip_length: The length of the piece of stroke we want to remove
         at each extremity.
      :type tip_length: float
   
   .. method:: shade(stroke)
   
      Removes the stroke's extremities.
   
      :param stroke: A Stroke object.
      :type stroke: :class:`freestyle.types.Stroke`



.. class:: py2DCurvatureColorShader

   Assigns a color (grayscale) to the stroke based on the curvature.
   A higher curvature will yield a brighter color.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyBackboneStretcherNoCuspShader

   Stretches the stroke's backbone, excluding cusp vertices (end junctions).

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyBackboneStretcherShader

   Stretches the stroke's backbone by a given length (in pixels).

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyBluePrintCirclesShader

   Draws the silhouette of the object as a circle.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyBluePrintDirectedSquaresShader

   Replaces the stroke with a directed square.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyBluePrintEllipsesShader


   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyBluePrintSquaresShader


   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyConstantColorShader

   Assigns a constant color to the stroke.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyConstantThicknessShader

   Assigns a constant thickness along the stroke.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyConstrainedIncreasingThicknessShader

   Increasingly thickens the stroke, constrained by a ratio of the
   stroke's length.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyDecreasingThicknessShader

   Inverse of pyIncreasingThicknessShader, decreasingly thickens the stroke.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyDepthDiscontinuityThicknessShader

   Assigns a thickness to the stroke based on the stroke's distance
   to the camera (Z-value).

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyDiffusion2Shader

   Iteratively adds an offset to the position of each stroke vertex
   in the direction perpendicular to the stroke direction at the
   point. The offset is scaled by the 2D curvature (i.e. how quickly
   the stroke curve is) at the point.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyFXSVaryingThicknessWithDensityShader

   Assigns thickness to a stroke based on the density of the diffuse map.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyGuidingLineShader


   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyHLRShader

   Controls visibility based upon the quantitative invisibility (QI)
   based on hidden line removal (HLR).

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyImportance2DThicknessShader

   Assigns thickness based on distance to a given point in 2D space.
   the thickness is inverted, so the vertices closest to the
   specified point have the lowest thickness.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyImportance3DThicknessShader

   Assigns thickness based on distance to a given point in 3D space.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyIncreasingColorShader

   Fades from one color to another along the stroke.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyIncreasingThicknessShader

   Increasingly thickens the stroke.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyInterpolateColorShader

   Fades from one color to another and back.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyLengthDependingBackboneStretcherShader

   Stretches the stroke's backbone proportional to the stroke's length
   NOTE: you'll probably want an l somewhere between (0.5 - 0). A value that
   is too high may yield unexpected results.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyMaterialColorShader

   Assigns the color of the underlying material to the stroke.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyModulateAlphaShader

   Limits the stroke's alpha between a min and max value.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyNonLinearVaryingThicknessShader

   Assigns thickness to a stroke based on an exponential function.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyPerlinNoise1DShader

   Displaces the stroke using the curvilinear abscissa.  This means
   that lines with the same length and sampling interval will be
   identically distorted.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyPerlinNoise2DShader

   Displaces the stroke using the strokes coordinates.  This means
   that in a scene no strokes will be distorted identically.
   
   More information on the noise shaders can be found at:
   https://freestyleintegration.wordpress.com/2011/09/25/development-updates-on-september-25/

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyRandomColorShader

   Assigns a color to the stroke based on given seed.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pySLERPThicknessShader

   Assigns thickness to a stroke based on spherical linear interpolation.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pySamplingShader

   Resamples the stroke, which gives the stroke the amount of
   vertices specified.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pySinusDisplacementShader

   Displaces the stroke in the shape of a sine wave.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyTVertexRemoverShader

   Removes t-vertices from the stroke.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyTVertexThickenerShader

   Thickens TVertices (visual intersections between two edges).

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyTimeColorShader

   Assigns a grayscale value that increases for every vertex.
   The brightness will increase along the stroke.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



.. class:: pyTipRemoverShader

   Removes the tips of the stroke.

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`

   .. staticmethod:: check_vertex(v, length)

      :param v: A stroke vertex to test.
      :type v: :class:`StrokeVertex`
      :param length: Distance threshold from the stroke ends.
      :type length: float
      :rtype: bool



.. class:: pyZDependingThicknessShader

   Assigns thickness based on an object's local Z depth (point
   closest to camera is 1, point furthest from camera is zero).

   .. method:: shade(stroke)

      :param stroke: The stroke to shade.
      :type stroke: :class:`Stroke`



