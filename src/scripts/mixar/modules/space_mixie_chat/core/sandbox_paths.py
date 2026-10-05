# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The sandbox's one file-system gate.

Every path a sandboxed script hands to anything that reads or writes a file goes through ``check_read`` or
``check_write``: the path is resolved with ``os.path.realpath`` (so a symlink that points out of a root is judged by
where it lands) and must be contained in an allowed root by ``os.path.commonpath`` (so ``/tmp/root`` does not admit
``/tmp/rootx``, which a plain prefix test did).

Roots:
  write   the temp directory, the Lampway home (projects, copies), and the blend file that is open;
  read    the write roots plus the open blend file's directory and Blender's own install.
``LAMPWAY_SANDBOX_READ_ROOTS`` / ``LAMPWAY_SANDBOX_WRITE_ROOTS`` (``os.pathsep``-separated) add roots for a setup that
keeps its pieces elsewhere.

Who calls it:
  * ``restricted_open`` (sandbox_modules) for every read and write;
  * the module proxy, for numpy's file functions (``load`` also refuses ``allow_pickle``, which runs code) and for every
    ``bpy.ops.<mod>.<op>`` reached through the proxy (``guard_operator``: a path-bearing operator is gated as a write or
    a read by its name, and the operators that run Python from a file or open the user's files are refused outright);
  * the AST pass and the wrapped ``getattr`` (``guard_file_method``) for methods that take a path: ``ndarray.tofile`` /
    ``dump``, ``Image.save`` / ``save_render``, ``bpy.data.libraries.write`` / ``load``, ``bpy.data.<images|texts|sounds|
    fonts|movieclips>.load`` and ``Text.as_module`` (refused: it executes the text).
"""

import ast
import os
import tempfile

# Operators refused outright: they run Python from a file, replace the open file, or hand a path/URL to the OS.
DENIED_OPERATORS = (
    "script.", "preferences.", "extensions.", "text.run_script", "text.open", "text.save", "text.save_as",
    "wm.open_mainfile", "wm.revert_mainfile", "wm.recover_", "wm.read_", "wm.path_open", "wm.url_open",
    "wm.console_toggle", "wm.sysinfo", "wm.app_template_install", "wm.keyconfig_import", "wm.keyconfig_export",
)
# An operator whose name carries one of these writes files; every other path-bearing operator reads.
WRITE_WORDS = ("save", "export", "render", "bake", "write", "screenshot", "pack", "snapshot", "dump", "backup")
PATH_KWARGS = ("filepath", "directory", "filename")

# Methods the AST pass and the wrapped getattr route through guard_file_method.
FILE_METHOD_NAMES = frozenset({"tofile", "dump", "save", "save_render", "write", "load", "as_module", "unpack", "reload"})
_WRITE_METHODS = frozenset({"tofile", "dump", "save", "save_render", "write", "unpack"})

# numpy functions gated by identity (so numpy.lib.npyio.load is the same gate as numpy.load), with their direction.
_NUMPY_FILE_FUNCTIONS = {
    "load": "read", "loadtxt": "read", "genfromtxt": "read", "fromregex": "read", "fromfile": "read",
    "save": "write", "savez": "write", "savez_compressed": "write", "savetxt": "write",
}


class SandboxPathError(PermissionError):
    pass


def _realpath(path) -> str:
    return os.path.realpath(_abspath(path))


def _abspath(path) -> str:
    p = os.fsdecode(os.fspath(path))
    if p.startswith("//"):                     # Blender's blend-relative prefix
        try:
            import bpy
            return bpy.path.abspath(p)
        except Exception:                      # noqa: BLE001 - no bpy: treat it as a plain path
            pass
    return os.path.abspath(p)


def contained(path, root) -> bool:
    """True when ``path`` resolves to ``root`` or somewhere inside it."""
    real = _realpath(path)
    real_root = _realpath(root)
    try:
        return os.path.commonpath([real, real_root]) == real_root
    except ValueError:                          # different drives
        return False


def _env_roots(var: str) -> list:
    raw = os.environ.get(var, "")
    return [r for r in raw.split(os.pathsep) if r]


def _lampway_home():
    try:
        from mixar.modules.lampway_tools.settings import lampway_home, load
        return [str(lampway_home()), str(load().project_root)]
    except Exception:                           # noqa: BLE001 - no settings module outside the add-on
        return []


def _open_blend() -> str:
    try:
        import bpy
        return bpy.data.filepath or ""
    except Exception:                           # noqa: BLE001
        return ""


def _blender_install() -> list:
    try:
        import bpy
        binary = bpy.app.binary_path
        return [os.path.dirname(binary)] if binary else []
    except Exception:                           # noqa: BLE001
        return []


def write_roots() -> tuple:
    roots = [tempfile.gettempdir()] + _lampway_home() + _env_roots("LAMPWAY_SANDBOX_WRITE_ROOTS")
    return tuple(dict.fromkeys(_realpath(r) for r in roots))


def read_roots() -> tuple:
    roots = list(write_roots())
    blend = _open_blend()
    if blend:
        roots.append(os.path.dirname(blend))
    roots += _blender_install() + _env_roots("LAMPWAY_SANDBOX_READ_ROOTS")
    return tuple(dict.fromkeys(_realpath(r) for r in roots))


def _check(path, roots, verb: str) -> str:
    real = _realpath(path)
    blend = _open_blend()
    if blend and real == _realpath(blend):
        return real
    for root in roots:
        try:
            if os.path.commonpath([real, root]) == root:
                return real
        except ValueError:
            continue
    raise SandboxPathError(
        f"{verb} of {os.fspath(path)!r} is outside the sandbox: it resolves to {real!r}, and the sandbox {verb}s only "
        f"inside {', '.join(roots)}"
    )


def check_write(path) -> str:
    """The resolved path, if a script may write it; else SandboxPathError."""
    return _check(path, write_roots(), "write")


def check_read(path) -> str:
    """The resolved path, if a script may read it; else SandboxPathError."""
    return _check(path, read_roots(), "read")


def _is_path(value) -> bool:
    return isinstance(value, (str, bytes, os.PathLike)) and bool(value)


# ----------------------------------------------------------------------------------------------------- operators
def guard_operator(idname: str, op):
    """``op`` (``bpy.ops.<idname>``) with its path arguments gated; a denied operator raises when called."""
    denied = any(idname == d or idname.startswith(d) for d in DENIED_OPERATORS)
    writes = any(word in idname.split(".", 1)[-1] for word in WRITE_WORDS)
    check = check_write if writes else check_read

    def gated(*args, **kwargs):
        if denied:
            raise SandboxPathError(f"bpy.ops.{idname} is not available in the sandbox.")
        for key in PATH_KWARGS:
            if _is_path(kwargs.get(key)):
                check(kwargs[key])
        files = kwargs.get("files")
        if files:
            base = kwargs.get("directory") if _is_path(kwargs.get("directory")) else ""
            for entry in files:
                name = entry.get("name") if isinstance(entry, dict) else getattr(entry, "name", None)
                if _is_path(name):
                    check(os.path.join(base, name))
        if idname in ("render.render", "render.opengl") and (kwargs.get("write_still") or kwargs.get("animation")):
            try:
                import bpy
                target = bpy.context.scene.render.filepath
            except Exception:                   # noqa: BLE001
                target = ""
            if target:
                check_write(os.path.dirname(_abspath(target)) or target)
        return op(*args, **kwargs)

    gated.__name__ = getattr(op, "__name__", idname)
    gated.__doc__ = getattr(op, "__doc__", None)
    return gated


# -------------------------------------------------------------------------------------------- numpy functions
_NUMPY_GATES: dict = {}


def _numpy_gates() -> dict:
    if _NUMPY_GATES:
        return _NUMPY_GATES
    try:
        import numpy
    except ImportError:
        return _NUMPY_GATES
    for name, direction in _NUMPY_FILE_FUNCTIONS.items():
        func = getattr(numpy, name, None)
        if func is None:
            continue
        _NUMPY_GATES[id(func)] = _gate_numpy(name, func, direction)
    return _NUMPY_GATES


def _gate_numpy(name, func, direction):
    check = check_write if direction == "write" else check_read

    def gated(file, *args, **kwargs):
        if name == "load" and kwargs.get("allow_pickle"):
            raise SandboxPathError("numpy.load(allow_pickle=True) is not available in the sandbox: a pickle runs code.")
        if _is_path(file):
            check(file)
        return func(file, *args, **kwargs)

    gated.__name__ = name
    gated.__doc__ = func.__doc__
    return gated


def gated_function(value):
    """``value`` itself, or its gate when it is one of numpy's file functions (matched by identity)."""
    try:
        return _numpy_gates().get(id(value), value)
    except TypeError:
        return value


# ------------------------------------------------------------------------------------------------ methods
def guard_file_attr(owner, name):
    """``getattr(owner, name)``, gated when ``name`` is a file method of an ndarray or a Blender datablock. Blender's RNA
    functions (``bpy.data.images.load``) are ``bpy_func`` objects that know neither their name nor their owner, so the
    gate is told both by the rewritten attribute access."""
    method = getattr(owner, name)
    return guard_file_method(method, owner=owner, name=name) if name in FILE_METHOD_NAMES else method


def guard_file_method(method, owner=None, name=None):
    """A bound ``tofile``/``dump``/``save``/``save_render``/``write``/``load``/``unpack``/``reload``/``as_module`` of an
    ndarray or a Blender datablock, with its path gated; anything else is returned untouched."""
    name = name or getattr(method, "__name__", "")
    owner = owner if owner is not None else getattr(method, "__self__", None)
    if name not in FILE_METHOD_NAMES or owner is None:
        return method
    kind = _owner_kind(owner)
    if kind is None:
        return method
    if name == "as_module":
        def refused(*args, **kwargs):
            raise SandboxPathError("Text.as_module() is not available in the sandbox: it executes the text block.")
        return refused
    check = check_write if name in _WRITE_METHODS else check_read

    def gated(*args, **kwargs):
        target = kwargs.get("filepath", args[0] if args else None)
        if _is_path(target):
            check(target)
        elif name in ("save", "unpack") and kind == "image":
            raw = getattr(owner, "filepath_raw", "") or getattr(owner, "filepath", "")
            if raw:
                check_write(raw)
        elif name == "reload" and kind == "image":
            raw = getattr(owner, "filepath_raw", "") or getattr(owner, "filepath", "")
            if raw:
                check_read(raw)
        return method(*args, **kwargs)

    gated.__name__ = name
    gated.__doc__ = getattr(method, "__doc__", None)
    return gated


def _owner_kind(owner):
    try:
        import numpy
        if isinstance(owner, numpy.ndarray):
            return "ndarray"
    except ImportError:
        pass
    try:
        import bpy
    except ImportError:
        return None
    if isinstance(owner, bpy.types.Image):
        return "image"
    if isinstance(owner, bpy.types.Text):
        return "text"
    # bpy.data.images / .sounds / .libraries ... are BlendData* RNA structs, not bpy_prop_collection instances: the type
    # NAME is the reliable test (the first version of this gate missed `bpy.data.images.load(path)`).
    if isinstance(owner, bpy.types.ID) or type(owner).__name__.startswith("BlendData") \
            or type(owner).__name__ == "bpy_prop_collection":
        return "blend_data"
    return None


class _GuardFileMethods(ast.NodeTransformer):
    def visit_Attribute(self, node):
        self.generic_visit(node)
        if node.attr in FILE_METHOD_NAMES and isinstance(node.ctx, ast.Load):
            # <owner>.<name>  ->  _mixar_guard_file_attr(<owner>, "<name>"): the owner is evaluated once, and the gate
            # knows it and the method's name even when the callable (an RNA function) does not.
            return ast.copy_location(ast.Call(
                func=ast.Name(id="_mixar_guard_file_attr", ctx=ast.Load()),
                args=[node.value, ast.Constant(value=node.attr)], keywords=[]), node)
        return node


def guard_file_methods(tree):
    """Rewrite every ``<expr>.<file method>`` load into ``_mixar_guard_file_method(<expr>.<file method>)``."""
    return ast.fix_missing_locations(_GuardFileMethods().visit(tree))
