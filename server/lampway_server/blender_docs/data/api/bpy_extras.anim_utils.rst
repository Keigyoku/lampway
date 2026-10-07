bpy_extras submodule (bpy_extras.anim_utils)
============================================

.. module:: bpy_extras.anim_utils

.. function:: action_get_channelbag_for_slot(action, slot)

   Returns the first channelbag found for the slot.
   In case there are multiple layers or strips they are iterated until a
   channelbag for that slot is found. In case no matching channelbag is found, returns None.
   
   :param action: Action to search.
   :type action: :class:`bpy.types.Action` | None
   :param slot: Slot to look up.
   :type slot: :class:`bpy.types.ActionSlot` | None
   :return: The first matching channelbag, or None when not found or when *action* or *slot* is None.
   :rtype: :class:`bpy.types.ActionChannelbag` | None

.. function:: action_get_first_suitable_slot(action, target_id_type)

   Return the first Slot of the given Action that's suitable for the given ID type.
   
   Typically you should not need this function; when an Action is assigned to a
   data-block, just use the slot that was assigned along with it.
   
   :param action: Action to search.
   :type action: :class:`bpy.types.Action` | None
   :param target_id_type: ID type identifier the slot must accept (e.g. ``'OBJECT'``).
   :type target_id_type: str
   :return: The first suitable slot, or None when none match or when *action* is None.
   :rtype: :class:`bpy.types.ActionSlot` | None

.. function:: action_ensure_channelbag_for_slot(action, slot)

   Ensure a layer and a keyframe strip exists, then ensure that strip has a channelbag for the slot.
   
   :param action: Action to populate.
   :type action: :class:`bpy.types.Action`
   :param slot: Slot to ensure a channelbag for.
   :type slot: :class:`bpy.types.ActionSlot`
   :return: The channelbag for *slot* in the first keyframe strip.
   :rtype: :class:`bpy.types.ActionChannelbag`

.. function:: animdata_get_channelbag_for_assigned_slot(anim_data)

   Return the first channelbag used in the given *anim_data* or None if there is no Action + Slot combination defined.
   
   :param anim_data: Animation data to inspect.
   :type anim_data: :class:`bpy.types.AnimData` | None
   :return: The first channelbag for the assigned slot, or None.
   :rtype: :class:`bpy.types.ActionChannelbag` | None

.. function:: bake_action(obj, *, action, frames, bake_options)

   :param obj: Object to bake.
   :type obj: :class:`bpy.types.Object`
   :param action: An action to bake the data into, or None for a new action
      to be created.
   :type action: :class:`bpy.types.Action` | None
   :param frames: Frames to bake.
   :type frames: Iterable[int]
   :param bake_options: Options for baking.
   :type bake_options: :class:`anim_utils.BakeOptions`
   :return: Action or None.
   :rtype: :class:`bpy.types.Action` | None

.. function:: bake_action_objects(object_action_pairs, *, frames, bake_options)

   A version of :func:`bake_action_objects_iter` that takes frames and returns the output.
   
   :param object_action_pairs: Sequence of object action tuples,
      action is the destination for the baked data. When None a new action will be created.
   :type object_action_pairs: Sequence[tuple[:class:`bpy.types.Object`, :class:`bpy.types.Action` | None]]
   :param frames: Frames to bake.
   :type frames: Iterable[int]
   :param bake_options: Options for baking.
   :type bake_options: :class:`anim_utils.BakeOptions`
   :return: A sequence of Action or None types (aligned with ``object_action_pairs``)
   :rtype: Sequence[:class:`bpy.types.Action`]

.. function:: bake_action_iter(obj, *, action, bake_options)

   A coroutine that bakes action for a single object.
   
   :param obj: Object to bake.
   :type obj: :class:`bpy.types.Object`
   :param action: An action to bake the data into, or None for a new action
      to be created.
   :type action: :class:`bpy.types.Action` | None
   :param bake_options: Options for baking.
   :type bake_options: :class:`anim_utils.BakeOptions`
   :return: an action or None
   :rtype: :class:`bpy.types.Action` | None

.. function:: bake_action_objects_iter(object_action_pairs, bake_options)

   A coroutine that bakes actions for multiple objects.
   
   :param object_action_pairs: Sequence of object action tuples,
      action is the destination for the baked data. When None a new action will be created.
   :type object_action_pairs: Sequence[tuple[:class:`bpy.types.Object`, :class:`bpy.types.Action` | None]]
   :param bake_options: Options for baking.
   :type bake_options: :class:`anim_utils.BakeOptions`
   :return: A generator that yields None for each frame, then finally
      yields a tuple of actions (aligned with *object_action_pairs*).
   :rtype: Generator

.. class:: AutoKeying

   Auto-keying support.

   .. classmethod:: active_keyingset(context)

      Return the active keying set, if it should be used.
      
      Only returns the active keying set when the auto-key settings indicate
      it should be used, and when it is not using absolute paths (because
      that's not supported by the Copy Global Transform add-on).
      
      :param context: The context.
      :type context: :class:`bpy.types.Context`
      :return: The active keying set, or None when it should not be used.
      :rtype: :class:`bpy.types.KeyingSet` | None

   .. classmethod:: autokey_transformation(context, target)

      Auto-key transformation properties.
      
      :param context: The context.
      :type context: :class:`bpy.types.Context`
      :param target: The object or pose bone to keyframe.
      :type target: :class:`bpy.types.Object` | :class:`bpy.types.PoseBone`

   .. classmethod:: autokeying_options(context)

      Retrieve the Auto Keyframe options, or None if disabled.
      
      :param context: The context.
      :type context: :class:`bpy.types.Context`
      :return: The keyframing option flags, or None when auto-keying is disabled.
      :rtype: set[str] | None

   .. classmethod:: key_transformation(target, options)

      Keyframe transformation properties, avoiding keying locked channels.
      
      :param target: The object or pose bone to keyframe.
      :type target: :class:`bpy.types.Object` | :class:`bpy.types.PoseBone`
      :param options: Keyframing options.
      :type options: set[str]

   .. classmethod:: key_transformation_via_keyingset(context, target, keyingset)

      Auto-key transformation properties with the given keying set.
      
      :param context: The context.
      :type context: :class:`bpy.types.Context`
      :param target: The object or pose bone to keyframe.
      :type target: :class:`bpy.types.Object` | :class:`bpy.types.PoseBone`
      :param keyingset: The keying set to use.
      :type keyingset: :class:`bpy.types.KeyingSet`

   .. classmethod:: keyframe_channels(target, options, data_path, group, locks)

      Keyframe channels, avoiding keying locked channels.
      
      :param target: The object or pose bone to keyframe.
      :type target: :class:`bpy.types.Object` | :class:`bpy.types.PoseBone`
      :param options: Keyframing options.
      :type options: set[str]
      :param data_path: The data path to keyframe.
      :type data_path: str
      :param group: The group name for the keyframes.
      :type group: str
      :param locks: Per-channel lock status.
      :type locks: Iterable[bool]

   .. classmethod:: keying_options(context)

      Retrieve the general keyframing options from user preferences.
      
      :param context: The context.
      :type context: :class:`bpy.types.Context`
      :return: The keyframing option flags.
      :rtype: set[str]

   .. classmethod:: keying_options_from_keyingset(context, keyingset)

      Retrieve the general keyframing options from user preferences.
      
      :param context: The context.
      :type context: :class:`bpy.types.Context`
      :param keyingset: The keying set to read options from.
      :type keyingset: :class:`bpy.types.KeyingSet`
      :return: The keyframing option flags.
      :rtype: set[str]

   .. classmethod:: keytype(the_keytype)

      Context manager to set the key type that's inserted.
      
      :param the_keytype: The key type to use.
      :type the_keytype: str
      :return: A context manager that resets the key type on exit.
      :rtype: Iterator[None]

   .. classmethod:: options(*, keytype='', use_loc=True, use_rot=True, use_scale=True, force_autokey=False)

      Context manager to set various keyframing options.
      
      :param keytype: The key type to use.
      :type keytype: str
      :param use_loc: Key location channels.
      :type use_loc: bool
      :param use_rot: Key rotation channels.
      :type use_rot: bool
      :param use_scale: Key scale channels.
      :type use_scale: bool
      :param force_autokey: Allow use without the user activating auto-keying.
      :type force_autokey: bool
      :return: A context manager that resets the options on exit.
      :rtype: Iterator[None]

   .. staticmethod:: get_4d_rotlock(bone)

      Retrieve the lock status for 4D rotation.
      
      :param bone: The pose bone to check.
      :type bone: :class:`bpy.types.PoseBone`
      :return: Lock status for W, X, Y, Z rotation channels.
      :rtype: list[bool]



.. class:: BakeOptions

   BakeOptions(only_selected: bool, do_pose: bool, do_object: bool, do_visual_keying: bool, do_constraint_clear: bool, do_parents_clear: bool, do_clean: bool, do_location: bool, do_rotation: bool, do_scale: bool, do_bbone: bool, do_custom_props: bool)

   .. details:: Special Methods

      .. method:: __eq__(other)

         :param other: The other operand.
         :type other: object
         :rtype: bool

      .. method:: __repr__()

         :rtype: str



