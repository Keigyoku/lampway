.. index:: Geometry Nodes; Value to String
.. _bpy.types.FunctionNodeValueToString:
.. --- copy below this line ---

********************
Value to String Node
********************

.. figure:: /images/node-types_FunctionNodeValueToString.webp
   :align: center
   :alt: Value to String node.

The *Value to String* node generates string representation of the input value.


Inputs
======

Value
   Floating-point value to be converted.

Decimals :guilabel:`Float Data Type`
   Integer value used to determine the precision of the output value.

Base :guilabel:`Integer Data Type`
   Numeric base used to represent integer values.

   For example, use ``2`` for binary, ``8`` for octal, ``10`` for decimal,
   or ``16`` for hexadecimal.

Padding :guilabel:`Integer Data Type`
   Minimum width of the output string.

   If the converted value contains fewer characters than the specified
   width, leading zeros are added until the minimum width is reached.


Properties
==========

Data Type
   The type of numerical value to convert to a string.

   :Float: Convert a floating-point value to a string.
   :Integer: Convert a 32-bit integer to a string.


Outputs
=======

String
   String value representation of the input.
