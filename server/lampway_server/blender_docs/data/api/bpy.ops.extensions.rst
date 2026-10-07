Extensions Operators
====================

.. module:: bpy.ops.extensions

.. function:: package_disable()

   Turn off this extension

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3593 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3593>`__

.. function:: package_install(*, repo_directory="", repo_index=-1, pkg_id="", enable_on_install=True, url="", do_legacy_replace=False)

   Download and install the extension

   :param repo_directory: Repo Directory, (optional, never None)
   :type repo_directory: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :param pkg_id: Package ID, (optional, never None)
   :type pkg_id: str
   :param enable_on_install: Enable on Install, Enable after installing (optional)
   :type enable_on_install: bool
   :param url: URL, (optional, never None)
   :type url: str
   :param do_legacy_replace: Do Legacy Replace, (optional)
   :type do_legacy_replace: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1502 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1502>`__


.. function:: package_install_files(*, filter_glob="*.zip;*.py", directory="", files=None, filepath="", repo='', enable_on_install=True, target='', overwrite=True, url="")

   Install extensions from files into a locally managed repository

   :param filter_glob: filter_glob, (optional, never None)
   :type filter_glob: str
   :param directory: Directory, (optional, never None)
   :type directory: str
   :param files: files, (optional)
   :type files: :class:`bpy_prop_collection`\ [:class:`OperatorFileListElement`] | None
   :param filepath: filepath, (optional, never None)
   :type filepath: str
   :param repo: User Repository, The user repository to install extensions into (optional)
   :type repo: str
   :param enable_on_install: Enable on Install, Enable after installing (optional)
   :type enable_on_install: bool
   :param target: Legacy Target Path, Path to install legacy add-on packages to (optional)
   :type target: str
   :param overwrite: Legacy Overwrite, Remove existing add-ons with the same ID (optional)
   :type overwrite: bool
   :param url: URL, (optional, never None)
   :type url: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1502 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1502>`__


.. function:: package_install_marked(*, enable_on_install=True)

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :param enable_on_install: Enable on Install, Enable after installing (optional)
   :type enable_on_install: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1502 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1502>`__


.. function:: package_mark_clear(*, pkg_id="", repo_index=-1)

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :param pkg_id: Package ID, (optional, never None)
   :type pkg_id: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3680 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3680>`__


.. function:: package_mark_clear_all()

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3727 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3727>`__

.. function:: package_mark_set(*, pkg_id="", repo_index=-1)

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :param pkg_id: Package ID, (optional, never None)
   :type pkg_id: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3666 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3666>`__


.. function:: package_mark_set_all()

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3691 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3691>`__

.. function:: package_obsolete_marked()

   Zeroes package versions, useful for development - to test upgrading

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3784 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3784>`__

.. function:: package_show_clear(*, pkg_id="", repo_index=-1)

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :param pkg_id: Package ID, (optional, never None)
   :type pkg_id: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3753 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3753>`__


.. function:: package_show_set(*, pkg_id="", repo_index=-1)

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :param pkg_id: Package ID, (optional, never None)
   :type pkg_id: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3739 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3739>`__


.. function:: package_show_settings(*, pkg_id="", repo_index=-1)

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :param pkg_id: Package ID, (optional, never None)
   :type pkg_id: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3767 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3767>`__


.. function:: package_theme_disable(*, pkg_id="", repo_index=-1)

   Reset to the default theme if this theme is active

   :param pkg_id: Package ID, (optional, never None)
   :type pkg_id: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3621 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3621>`__


.. function:: package_theme_enable(*, pkg_id="", repo_index=-1)

   Turn on this theme

   :param pkg_id: Package ID, (optional, never None)
   :type pkg_id: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3607 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3607>`__


.. function:: package_uninstall(*, repo_directory="", repo_index=-1, pkg_id="")

   Disable and uninstall the extension

   :param repo_directory: Repo Directory, (optional, never None)
   :type repo_directory: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :param pkg_id: Package ID, (optional, never None)
   :type pkg_id: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1502 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1502>`__


.. function:: package_uninstall_marked()

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1502 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1502>`__

.. function:: package_uninstall_system()

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3584 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3584>`__

.. function:: package_upgrade_all(*, use_active_only=False)

   Upgrade installed extensions to their latest version from remote repositories

   :param use_active_only: Active Only, Only upgrade the active repository (optional)
   :type use_active_only: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1502 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1502>`__


.. function:: repo_enable_from_drop(*, repo_index=-1)

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1835 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1835>`__


.. function:: repo_lock_all()

   Lock repositories - to test locking

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3853 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3853>`__

.. function:: repo_refresh_all(*, use_active_only=False)

   Refresh extension & legacy add-ons, reloading modules & meta-data (similar to restarting)

   :param use_active_only: Active Only, Only refresh the active repository (optional)
   :type use_active_only: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1744 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1744>`__


.. function:: repo_sync(*, repo_directory="", repo_index=-1)

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :param repo_directory: Repo Directory, (optional, never None)
   :type repo_directory: str
   :param repo_index: Repo Index, (in [-inf, inf], optional)
   :type repo_index: int
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1502 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1502>`__


.. function:: repo_sync_all(*, use_active_only=False)

   Refresh the list of extensions for all the remote repositories

   :param use_active_only: Active Only, Only sync the active repository (optional)
   :type use_active_only: bool
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1502 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1502>`__


.. function:: repo_unlock()

   Remove the repository file-system lock

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:1922 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L1922>`__

.. function:: repo_unlock_all()

   Unlock repositories - to test unlocking

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3879 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3879>`__

.. function:: status_clear()

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3652 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3652>`__

.. function:: status_clear_errors()

   Undocumented, consider `contributing <https://developer.blender.org/>`__.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3641 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3641>`__

.. function:: userpref_allow_online()

   Allow Blender to access the internet. Add-ons that follow this setting will only connect to the internet if enabled. However, Blender cannot prevent third-party add-ons from violating this rule.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:4005 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L4005>`__

.. function:: userpref_allow_online_popup()

   Allow Blender to access the internet. Add-ons that follow this setting will only connect to the internet if enabled. However, Blender cannot prevent third-party add-ons from violating this rule.

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:4020 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L4020>`__

.. function:: userpref_show_for_update()

   Open extensions preferences

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3944 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3944>`__

.. function:: userpref_show_online()

   Show system preferences "Network" panel to allow online access

   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3984 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3984>`__

.. function:: userpref_tags_set(*, value=False, data_path="")

   Set the value of all tags

   :param value: Value, Enable or disable all tags (optional)
   :type value: bool
   :param data_path: Data Path, (optional, never None)
   :type data_path: str
   :return: Result of the operator call.
   :rtype: set[Literal[:ref:`rna_enum_operator_return_items`]]
   :File: `addons_core/bl_pkg/bl_extension_ops.py\:3913 <https://projects.blender.org/blender/blender/src/branch/main/scripts/addons_core/bl_pkg/bl_extension_ops.py#L3913>`__


