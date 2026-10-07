NodeTreeInterfaceSocket(NodeTreeInterfaceItem)
==============================================

.. currentmodule:: bpy.types

base classes --- :class:`bpy_struct`, :class:`NodeTreeInterfaceItem`

.. toctree::
   :caption: Subclasses
   :maxdepth: 1

   bpy.types.NodeTreeInterfaceSocketBool.rst
   bpy.types.NodeTreeInterfaceSocketBundle.rst
   bpy.types.NodeTreeInterfaceSocketClosure.rst
   bpy.types.NodeTreeInterfaceSocketCollection.rst
   bpy.types.NodeTreeInterfaceSocketColor.rst
   bpy.types.NodeTreeInterfaceSocketFloat.rst
   bpy.types.NodeTreeInterfaceSocketFloatAngle.rst
   bpy.types.NodeTreeInterfaceSocketFloatColorTemperature.rst
   bpy.types.NodeTreeInterfaceSocketFloatDistance.rst
   bpy.types.NodeTreeInterfaceSocketFloatFactor.rst
   bpy.types.NodeTreeInterfaceSocketFloatFrequency.rst
   bpy.types.NodeTreeInterfaceSocketFloatMass.rst
   bpy.types.NodeTreeInterfaceSocketFloatPercentage.rst
   bpy.types.NodeTreeInterfaceSocketFloatPixel.rst
   bpy.types.NodeTreeInterfaceSocketFloatTime.rst
   bpy.types.NodeTreeInterfaceSocketFloatTimeAbsolute.rst
   bpy.types.NodeTreeInterfaceSocketFloatUnsigned.rst
   bpy.types.NodeTreeInterfaceSocketFloatWavelength.rst
   bpy.types.NodeTreeInterfaceSocketFont.rst
   bpy.types.NodeTreeInterfaceSocketGeometry.rst
   bpy.types.NodeTreeInterfaceSocketImage.rst
   bpy.types.NodeTreeInterfaceSocketInt.rst
   bpy.types.NodeTreeInterfaceSocketIntFactor.rst
   bpy.types.NodeTreeInterfaceSocketIntPercentage.rst
   bpy.types.NodeTreeInterfaceSocketIntPixel.rst
   bpy.types.NodeTreeInterfaceSocketIntUnsigned.rst
   bpy.types.NodeTreeInterfaceSocketIntVector2D.rst
   bpy.types.NodeTreeInterfaceSocketIntVector3D.rst
   bpy.types.NodeTreeInterfaceSocketIntVectorFactor2D.rst
   bpy.types.NodeTreeInterfaceSocketIntVectorFactor3D.rst
   bpy.types.NodeTreeInterfaceSocketIntVectorPercentage2D.rst
   bpy.types.NodeTreeInterfaceSocketIntVectorPercentage3D.rst
   bpy.types.NodeTreeInterfaceSocketIntVectorPixel2D.rst
   bpy.types.NodeTreeInterfaceSocketIntVectorPixel3D.rst
   bpy.types.NodeTreeInterfaceSocketIntVectorUnsigned2D.rst
   bpy.types.NodeTreeInterfaceSocketIntVectorUnsigned3D.rst
   bpy.types.NodeTreeInterfaceSocketMask.rst
   bpy.types.NodeTreeInterfaceSocketMaterial.rst
   bpy.types.NodeTreeInterfaceSocketMatrix.rst
   bpy.types.NodeTreeInterfaceSocketMenu.rst
   bpy.types.NodeTreeInterfaceSocketObject.rst
   bpy.types.NodeTreeInterfaceSocketRotation.rst
   bpy.types.NodeTreeInterfaceSocketScene.rst
   bpy.types.NodeTreeInterfaceSocketShader.rst
   bpy.types.NodeTreeInterfaceSocketSound.rst
   bpy.types.NodeTreeInterfaceSocketString.rst
   bpy.types.NodeTreeInterfaceSocketStringFilePath.rst
   bpy.types.NodeTreeInterfaceSocketText.rst
   bpy.types.NodeTreeInterfaceSocketTexture.rst
   bpy.types.NodeTreeInterfaceSocketVector.rst
   bpy.types.NodeTreeInterfaceSocketVector2D.rst
   bpy.types.NodeTreeInterfaceSocketVector4D.rst
   bpy.types.NodeTreeInterfaceSocketVectorAcceleration.rst
   bpy.types.NodeTreeInterfaceSocketVectorAcceleration2D.rst
   bpy.types.NodeTreeInterfaceSocketVectorAcceleration4D.rst
   bpy.types.NodeTreeInterfaceSocketVectorDirection.rst
   bpy.types.NodeTreeInterfaceSocketVectorDirection2D.rst
   bpy.types.NodeTreeInterfaceSocketVectorDirection4D.rst
   bpy.types.NodeTreeInterfaceSocketVectorEuler.rst
   bpy.types.NodeTreeInterfaceSocketVectorEuler2D.rst
   bpy.types.NodeTreeInterfaceSocketVectorEuler4D.rst
   bpy.types.NodeTreeInterfaceSocketVectorFactor.rst
   bpy.types.NodeTreeInterfaceSocketVectorFactor2D.rst
   bpy.types.NodeTreeInterfaceSocketVectorFactor4D.rst
   bpy.types.NodeTreeInterfaceSocketVectorPercentage.rst
   bpy.types.NodeTreeInterfaceSocketVectorPercentage2D.rst
   bpy.types.NodeTreeInterfaceSocketVectorPercentage4D.rst
   bpy.types.NodeTreeInterfaceSocketVectorPixel.rst
   bpy.types.NodeTreeInterfaceSocketVectorPixel2D.rst
   bpy.types.NodeTreeInterfaceSocketVectorPixel4D.rst
   bpy.types.NodeTreeInterfaceSocketVectorTranslation.rst
   bpy.types.NodeTreeInterfaceSocketVectorTranslation2D.rst
   bpy.types.NodeTreeInterfaceSocketVectorTranslation4D.rst
   bpy.types.NodeTreeInterfaceSocketVectorVelocity.rst
   bpy.types.NodeTreeInterfaceSocketVectorVelocity2D.rst
   bpy.types.NodeTreeInterfaceSocketVectorVelocity4D.rst
   bpy.types.NodeTreeInterfaceSocketVectorXYZ.rst
   bpy.types.NodeTreeInterfaceSocketVectorXYZ2D.rst
   bpy.types.NodeTreeInterfaceSocketVectorXYZ4D.rst

.. class:: NodeTreeInterfaceSocket(NodeTreeInterfaceItem)

   Declaration of a node socket

   .. attribute:: attribute_domain

      Attribute domain used by the geometry nodes modifier to create an attribute output (default ``'POINT'``)

      :type: Literal[:ref:`rna_enum_attribute_domain_items`]

   .. attribute:: bl_socket_idname

      Name of the socket type (default "", never None)

      :type: str

   .. attribute:: default_attribute_name

      The attribute name used by default when the node group is used by a geometry nodes modifier (default "", never None)

      :type: str

   .. attribute:: default_input

      Input to use when the socket is unconnected. Requires "Hide Value". (default ``'VALUE'``)

      - ``VALUE``
        Default Value -- The node socket's default value.
      - ``INDEX``
        Index -- The index from the context.
      - ``ID_OR_INDEX``
        ID or Index -- The "id" attribute if available, otherwise the index.
      - ``NORMAL``
        Normal -- The geometry's normal direction.
      - ``POSITION``
        Position -- The position from the context.
      - ``INSTANCE_TRANSFORM``
        Instance Transform -- Transformation of each instance from the geometry context.
      - ``HANDLE_LEFT``
        Left Handle -- The left Bézier control point handle from the context.
      - ``HANDLE_RIGHT``
        Right Handle -- The right Bézier control point handle from the context.
      - ``SCENE_FRAME``
        Scene Frame -- The current frame in the scene.
      - ``UNIFORM_IMAGE_COORDINATES``
        Uniform Image Coordinates -- The uniform image coordinates of the compositing space.
      - ``SELF_OBJECT``
        Self Object -- The object that contains the geometry nodes modifier currently being executed.

      :type: Literal['VALUE', 'INDEX', 'ID_OR_INDEX', 'NORMAL', 'POSITION', 'INSTANCE_TRANSFORM', 'HANDLE_LEFT', 'HANDLE_RIGHT', 'SCENE_FRAME', 'UNIFORM_IMAGE_COORDINATES', 'SELF_OBJECT']

   .. attribute:: description

      Socket description (default "", never None)

      :type: str

   .. attribute:: force_non_field

      Only allow single value inputs rather than field.
      Deprecated. Will be remove in 5.0.
      
      (default False)

      :type: bool

   .. attribute:: hide_in_modifier

      Don't show the input value in the geometry nodes modifier interface (default False)

      :type: bool

   .. attribute:: hide_value

      Hide the socket input value even when the socket is not connected (default False)

      :type: bool

   .. data:: identifier

      Unique identifier for mapping sockets (default "", readonly, never None)

      :type: str

   .. data:: in_out

      Input or output socket type (default ``'INPUT'``, readonly)

      - ``INPUT``
        Input -- Generate a input node socket.
      - ``OUTPUT``
        Output -- Generate a output node socket.

      :type: Literal['INPUT', 'OUTPUT']

   .. attribute:: is_inspect_output

      Take link out of node group to connect to root tree output node (default False)

      :type: bool

   .. attribute:: is_panel_toggle

      This socket is meant to be used as the toggle in its panel header (default False)

      :type: bool

   .. attribute:: layer_selection_field

      Take Grease Pencil Layer or Layer Group as selection field (default False)

      :type: bool

   .. attribute:: menu_expanded

      Draw the menu socket as an expanded drop-down menu (default False)

      :type: bool

   .. attribute:: name

      Socket name (default "", never None)

      :type: str

   .. attribute:: optional_label

      Indicate that the label of this socket is not necessary to understand its meaning. This may result in the label being skipped in some cases (default False)

      :type: bool

   .. attribute:: select

      Socket is selected in the interface (default False)

      :type: bool

   .. attribute:: socket_type

      Type of the socket generated by this interface item (default ``'DEFAULT'``)

      :type: Literal['DEFAULT']

   .. attribute:: structure_type

      What kind of higher order types are expected to flow through this socket (default ``'AUTO'``)

      :type: Literal[:ref:`rna_enum_node_socket_structure_type_items`]

   .. method:: bl_system_properties_get(*, do_create=False)

      DEBUG ONLY. Internal access to runtime-defined RNA data storage, intended solely for testing and debugging purposes. Do not access it in regular scripting work, and in particular, do not assume that it contains writable data

      :param do_create: Ensure that system properties are created if they do not exist yet (optional)
      :type do_create: bool
      :return: The system properties root container, or None if there are no system properties stored in this data yet, and its creation was not requested
      :rtype: :class:`PropertyGroup`

   .. method:: draw(context, layout)

      Draw properties of the socket interface

      :param context: (never None)
      :type context: :class:`Context` | None
      :param layout: Layout, Layout in the UI (never None)
      :type layout: :class:`UILayout` | None

   .. method:: init_socket(node, socket, data_path)

      Initialize a node socket instance

      :param node: Node, Node of the socket to initialize (never None)
      :type node: :class:`Node` | None
      :param socket: Socket, Socket to initialize (never None)
      :type socket: :class:`NodeSocket` | None
      :param data_path: Data Path, Path to specialized socket data (never None)
      :type data_path: str

   .. method:: from_socket(node, socket)

      Setup template parameters from an existing socket

      :param node: Node, Node of the original socket (never None)
      :type node: :class:`Node` | None
      :param socket: Socket, Original socket (never None)
      :type socket: :class:`NodeSocket` | None

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
   - :class:`NodeTreeInterfaceItem.item_type`
   - :class:`NodeTreeInterfaceItem.parent`
   - :class:`NodeTreeInterfaceItem.position`
   - :class:`NodeTreeInterfaceItem.index`

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
   - :class:`NodeTreeInterfaceItem.bl_rna_get_subclass`
   - :class:`NodeTreeInterfaceItem.bl_rna_get_subclass_py`

References
----------

.. hlist::
   :columns: 2

   - :class:`NodeTreeInterface.new_socket`

