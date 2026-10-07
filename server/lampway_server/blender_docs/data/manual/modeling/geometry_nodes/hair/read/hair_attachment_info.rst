.. index:: Geometry Nodes; Attachment Info

***************
Attachment Info
***************

The *Attachment Info* node retrieves information about how hair curves are
attached to a surface mesh.

This includes the surface geometry, the stored attachment coordinates, and the
surface normal at each attachment point. The node can also be used to determine
whether the attachment data is valid.


Inputs
======

Hair Curves
   Hair curves with stored surface attachment information.


Outputs
=======

Surface Geometry
   Surface geometry the curves are attached to.

Surface Exists
   Whether the attached surface geometry exists.

Attachment UV
   UV coordinates of each curve's attachment point on the surface.

Attachment is Valid
   Whether each curve has valid attachment data.

   This output can be used to detect missing or invalid attachments, for
   example after removing or replacing the surface geometry.

Surface Normal
   Surface normal evaluated at each curve's attachment point.
