Region(bpy_struct)
==================

.. currentmodule:: bpy.types

base class --- :class:`bpy_struct`


.. class:: Region(bpy_struct)

   Region in a subdivided screen area

   .. attribute:: active_panel_category

      The current active panel category, may be Null if the region does not support this feature (NOTE: these categories are generated at runtime, so list may be empty at initialization, before any drawing took place) (default ``'UNSUPPORTED'``)

      :type: Literal[:ref:`rna_enum_region_panel_category_items`]

   .. data:: alignment

      Alignment of the region within the area (default ``'NONE'``, readonly)

      - ``NONE``
        None -- Don't use any fixed alignment, fill available space.
      - ``TOP``
        Top.
      - ``BOTTOM``
        Bottom.
      - ``LEFT``
        Left.
      - ``RIGHT``
        Right.
      - ``HORIZONTAL_SPLIT``
        Horizontal Split.
      - ``VERTICAL_SPLIT``
        Vertical Split.
      - ``FLOAT``
        Float -- Region floats on screen, does not use any fixed alignment.
      - ``QUAD_SPLIT``
        Quad Split -- Region is split horizontally and vertically.

      :type: Literal['NONE', 'TOP', 'BOTTOM', 'LEFT', 'RIGHT', 'HORIZONTAL_SPLIT', 'VERTICAL_SPLIT', 'FLOAT', 'QUAD_SPLIT']

   .. data:: data

      Region specific data (the type depends on the region type) (readonly)

      :type: :class:`AnyType` | None

   .. data:: height

      Region height (in [0, 32767], default 0, readonly)

      :type: int

   .. data:: type

      Type of this region (default ``'WINDOW'``, readonly)

      :type: Literal[:ref:`rna_enum_region_type_items`]

   .. data:: view2d

      2D view of the region (readonly, never None)

      :type: :class:`View2D`

   .. data:: width

      Region width (in [0, 32767], default 0, readonly)

      :type: int

   .. data:: x

      The window relative vertical location of the region (in [-inf, inf], default 0, readonly)

      :type: int

   .. data:: y

      The window relative horizontal location of the region (in [-inf, inf], default 0, readonly)

      :type: int

   .. method:: tag_redraw()

      tag_redraw


   .. method:: tag_refresh_ui()

      tag_refresh_ui


   .. method:: mixar_draw_glass(bounds, *, radius=12.0, alpha=1.0)

      Draw the agent task cards' glass material during a POST_PIXEL draw callback

      :param bounds: Bounds, Region pixels: xmin, ymin, xmax, ymax (array of 4 items, in [-inf, inf])
      :type bounds: Sequence[int]
      :param radius: Radius, Corner radius in pixels (in [0, 10000], optional)
      :type radius: float
      :param alpha: Opacity, Fade the complete material (in [0, 1], optional)
      :type alpha: float

   .. method:: mixar_agent_panel_bounds()

      Read the native agent stack's notification anchor

      :return: Bounds, Viewport pixels: left, bottom, right, stack top, chrome ceiling (array of 5 items, in [-inf, inf])
      :rtype: :class:`bpy_prop_array`\ [int]

   .. method:: mixar_draw_card_close(bounds, *, alpha=1.0, hovered=False)

      Draw the shared task and notification close control

      :param bounds: Bounds, Region pixels: xmin, ymin, exclusive xmax, exclusive ymax (array of 4 items, in [-inf, inf])
      :type bounds: Sequence[int]
      :param alpha: Opacity, Fade the entire control (in [0, 1], optional)
      :type alpha: float
      :param hovered: Hovered, Draw the shared rounded hover wash (optional)
      :type hovered: bool

   .. classmethod:: bl_rna_get_subclass(id, default=None, /)
   
      :param id: The RNA type identifier.
      :type id: str
      :param default: The value to return when not found.
      :type default: :class:`bpy.types.Struct` | None
      :return: The RNA type or default when not found.
      :rtype: :class:`bpy.types.Struct`


   .. classmethod:: bl_rna_get_subclass_py(id, default=None, /)
   
      :param id: The RNA type identifier.
      :type id: str
      :param default: The value to return when not found.
      :type default: type | None
      :return: The class or default when not found.
      :rtype: type


Inherited Properties
--------------------

.. hlist::
   :columns: 2

   - :class:`bpy_struct.id_data`

Inherited Functions
-------------------

.. hlist::
   :columns: 2

   - :class:`bpy_struct.as_pointer`
   - :class:`bpy_struct.driver_add`
   - :class:`bpy_struct.driver_remove`
   - :class:`bpy_struct.get`
   - :class:`bpy_struct.id_properties_clear`
   - :class:`bpy_struct.id_properties_ensure`
   - :class:`bpy_struct.id_properties_ui`
   - :class:`bpy_struct.is_property_hidden`
   - :class:`bpy_struct.is_property_overridable_library`
   - :class:`bpy_struct.is_property_readonly`
   - :class:`bpy_struct.is_property_set`
   - :class:`bpy_struct.items`
   - :class:`bpy_struct.keyframe_delete`
   - :class:`bpy_struct.keyframe_insert`
   - :class:`bpy_struct.keys`
   - :class:`bpy_struct.path_from_id`
   - :class:`bpy_struct.path_from_module`
   - :class:`bpy_struct.path_resolve`
   - :class:`bpy_struct.pop`
   - :class:`bpy_struct.property_overridable_library_set`
   - :class:`bpy_struct.property_unset`
   - :class:`bpy_struct.rna_ancestors`
   - :class:`bpy_struct.type_recast`
   - :class:`bpy_struct.values`

References
----------

.. hlist::
   :columns: 2

   - :class:`Area.regions`
   - :class:`Context.region`
   - :class:`Context.region_popup`

