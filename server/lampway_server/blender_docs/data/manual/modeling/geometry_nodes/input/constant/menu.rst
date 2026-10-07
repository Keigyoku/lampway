.. index:: Geometry Nodes; Menu
.. _bpy.types.FunctionNodeInputMenu:
.. --- copy below this line ---

*********
Menu Node
*********

.. figure:: /images/node-types_FunctionNodeInputMenu.webp
   :align: right
   :alt: Menu Node.

The *Menu* node outputs a menu value that can be used to control nodes that support menu sockets.

The available menu items are determined by the socket the node is connected to.
When connected to a node with a predefined menu, the *Menu* node exposes the same list of options.
Custom menus can also be created with the :doc:`../../utilities/menu_switch`
node and then used as the source for this node.


Outputs
=======

Menu
   The selected menu value.

   The available options are defined by the connected menu socket.
