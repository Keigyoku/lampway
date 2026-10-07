Lampway Operators
=================

.. module:: bpy.ops.lampway

.. function:: vault_drop(*, asset_id="", where="")

   Place the dragged Vault asset where it was dropped

   :param asset_id: Asset, The Vault asset to place (optional, never None)
   :type asset_id: str
   :param where: Where, asset_place's target: cursor, object:<name>, slot:<object>:<index>, node_tree:<material> (optional, never None)
   :type where: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]

