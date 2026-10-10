# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Candidate Grok worker boundary; it never makes the adapter worker-ready.

The native Grok `wrap` command may invoke this module. Only owned pane metadata
is read. Native HOME/login/persona/configuration remain native. Existing policies
are bind-mounted; an occupied additional requirements slot refuses. No host
policy, credential or native configuration file is changed. Actual namespace,
MCP exclusion and herdr lifecycle proof are required before enabling this route.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys

NATIVE_SHA256 = '41626a53292324140b92556b9d42ff5542e3dcd04aff85eafb8689dd4adb44fc'


def candidate_paths(native):
    """Installed paths only; no launch, credential/config read, or readiness grant."""
    if sys.platform != 'linux':
        raise ValueError('Grok worker candidate requires an unprivileged Linux namespace runner')
    bwrap = shutil.which('bwrap')
    connector = Path(sys.executable).parent / 'lampway-pane-mcp'
    if not bwrap or not connector.is_file():
        raise ValueError('Grok worker needs ordinary bubblewrap and this server interpreter\'s installed lampway-pane-mcp')
    return {'native': str(_absolute(str(native))), 'bwrap': str(_absolute(bwrap)), 'connector': str(connector)}


def _shim_source(config_path, root):
    return ('#!' + sys.executable + ' -I\nimport os\n'
            'os.environ["LAMPWAY_HERMES_CONNECTOR_CONFIG"] = ' + repr(str(config_path)) + '\n'
            'os.environ["LAMPWAY_HERMES_CONNECTOR_ROOT"] = ' + repr(str(root)) + '\n'
            'from lampway_server.pane_mcp import main\nraise SystemExit(main())\n')


def _native_wrap_parent(native, outer):
    """Only our direct parent is inspected; an arbitrary old socket is not adopted."""
    parent = Path('/proc') / str(os.getppid())
    try:
        argv = (parent / 'cmdline').read_bytes().decode().split('\0')
        index = argv.index('--leader-socket')
        return ((parent / 'exe').resolve() == native.resolve() and
                argv[index + 1] == str(outer) and 'wrap' in argv)
    except (OSError, ValueError, IndexError):
        return False


def _directory_access(path):
    """Retain original effective traversal/read access in the owned read-only skeleton.

    Ownership cannot be transferred without a host grant. Fail closed when an
    ownership change would alter the invoking user's access, rather than grant
    that user the original root owner's permissions.
    """
    info = path.stat(); mode = stat.S_IMODE(info.st_mode)
    role = 6 if info.st_uid == os.getuid() else (3 if info.st_gid in os.getgroups() + [os.getgid()] else 0)
    effective = (mode >> role) & 7
    actual = (4 if os.access(path, os.R_OK) else 0) | (1 if os.access(path, os.X_OK) else 0)
    if ((mode >> 6) & 5) != (effective & 5) or actual != (effective & 5):
        raise ValueError('private policy directory cannot preserve original traversal permissions')
    return mode


def _absolute(value):
    if not isinstance(value, str) or not value or '\0' in value or not os.path.isabs(value):
        raise ValueError('worker paths must be absolute')
    return Path(value)


def _owned_json(path):
    if path.is_symlink() or path.resolve() != path:
        raise ValueError('worker metadata must not be a symlink')
    parent = path.parent.stat()
    if stat.S_IMODE(parent.st_mode) != 0o700 or parent.st_uid != os.getuid():
        raise ValueError('worker metadata directory must be owned mode 0700')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid() or info.st_size > 1024 * 1024:
            raise ValueError('worker metadata must be owned regular mode 0600')
        value = json.load(stream)
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError('unsupported worker metadata')
    return value


def _binary(value, expected):
    path = _absolute(value)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK) or info.st_mode & (stat.S_ISUID | stat.S_ISGID):
        raise ValueError('worker executable must be ordinary non-setuid executable')
    try:
        if os.getxattr(path, 'security.capability'):
            raise ValueError('worker executable must have no granted file capabilities')
    except OSError as exc:
        if exc.errno not in (errno.ENODATA, errno.ENOTSUP):
            raise
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('worker executable requires an exact SHA256')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
            raise ValueError('worker executable hash differs from preflight')
    return path


def native_connector_identity(native_listing, command, args=()):
    """Parse native `mcp list --json`; return identity only, never native secret fields.

    The caller supplies output from the existing launcher probe. This module
    never reads native configuration/credentials or invokes `mcp add`.
    """
    try:
        rows = json.loads(native_listing)
    except (ValueError, TypeError) as exc:
        raise ValueError('Grok MCP listing is unavailable or malformed; verify the dedicated native pane MCP connector setup') from exc
    if not isinstance(rows, list):
        raise ValueError('Grok MCP listing is not the native JSON array')
    canonical = [row for row in rows if isinstance(row, dict) and row.get('name') == 'lampway_pane']
    if (len(canonical) != 1 or canonical[0].get('command') != str(command) or
            canonical[0].get('args', []) != list(args) or canonical[0].get('enabled') is not True or
            canonical[0].get('blocked_reason')):
        raise ValueError('Install/enable the dedicated native pane MCP connector with grok mcp add; existing setup is absent, mismatched or blocked')
    return {'name': 'lampway_pane', 'command': str(command), 'args': list(args)}


def _policy_slots(etc):
    for name in ('requirements.toml', 'managed_config.toml'):
        if os.path.lexists(etc / 'grok' / name):
            raise ValueError(f'native {name} slot is occupied; no policy is replaced')
    if etc.is_symlink() or not etc.is_dir() or (etc / 'grok').is_symlink():
        raise ValueError('native policy directories must not be redirected')
    return {'etc': _directory_access(etc), 'grok': _directory_access(etc / 'grok') if (etc / 'grok').exists() else 0o755}


def preflight(native, bwrap, connector, native_listing, *, etc=Path('/etc')):
    """Pure preactivation checks and launcher probe descriptions; no files/processes.

    An accepted description is NOT a capability or worker-readiness grant: the
    caller must run its namespace probe through the launcher and require actual
    native CI acceptance. Installed alias output must be queried at project cwd.
    """
    def sha(path):
        with _absolute(str(path)).open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    native = _binary(str(native), NATIVE_SHA256)
    bwrap_hash, connector_hash = sha(bwrap), sha(connector)
    bwrap = _binary(str(bwrap), bwrap_hash); connector = _binary(str(connector), connector_hash)
    native_connector_identity(native_listing, connector)
    _policy_slots(etc)
    return {'native': str(native), 'native_sha256': NATIVE_SHA256,
            'bwrap': str(bwrap), 'bwrap_sha256': bwrap_hash,
            'connector': {'command': str(connector), 'args': [], 'sha256': connector_hash},
            'namespace_probe': [str(bwrap), '--unshare-user', '--uid', str(os.getuid()), '--gid', str(os.getgid()),
                '--unshare-pid', '--die-with-parent', '--cap-drop', 'ALL', '--bind', '/', '/', '--proc', '/proc', '--', '/bin/true']}


def build_plan(path, *, task=None, etc=Path('/etc')):
    """Describe a fail-closed plan. `etc` is injectable only for deterministic tests.

    This function starts no process and writes nothing. The CLI always uses /etc.
    It deliberately exposes no flag that changes the native policy source path.
    """
    path = _absolute(str(path))
    config = _owned_json(path)
    root = _absolute(config.get('root'))
    if path.name != 'grok-worker.json' or path.parent.parent != root / 'panes':
        raise ValueError('worker metadata must live in its pane under the supplied root')
    from .pane_mcp import read_config
    bound = read_config(str(path.with_name('mcp.json')), str(root))
    if not bound or not bound['binding'].startswith('swarm:') or bound.get('desktop') is not None or len(bound.get('direct', [])) != 1:
        raise ValueError('worker requires one owned direct-only swarm binding')
    native = _binary(config.get('native'), config.get('native_sha256'))
    bwrap = _binary(config.get('bwrap'), config.get('bwrap_sha256'))
    cwd = _absolute(config.get('cwd'))
    if not cwd.is_dir():
        raise ValueError('worker project cwd is missing')
    task = config.get('task') if task is None else task
    if not isinstance(task, str) or not task or '\0' in task:
        raise ValueError('worker task must be nonempty literal text')
    connector = config.get('connector')
    if not isinstance(connector, dict):
        raise ValueError('worker connector identity is missing')
    command = _binary(connector.get('command'), connector.get('sha256'))
    args = connector.get('args')
    if not command.is_file() or not os.access(command, os.X_OK) or not isinstance(args, list) or not all(isinstance(x, str) and '\0' not in x for x in args):
        raise ValueError('worker connector must have an exact executable argv')
    inner, outer = (_absolute(config.get(name)) for name in ('inner_socket', 'outer_socket'))
    if inner == outer or any(p.parent != path.parent or p.is_symlink() for p in (inner, outer)) or os.path.lexists(inner):
        raise ValueError('worker leaders require distinct owned pane sockets and an unused inner socket')
    if os.path.lexists(outer):
        info = outer.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or not _native_wrap_parent(native, outer):
            raise ValueError('existing outer socket is not owned by this native wrap parent')
    modes = _policy_slots(etc)
    work = path.parent / 'grok-worker-boundary'
    if os.path.lexists(work):
        raise ValueError('worker boundary already exists; do not reuse unknown state')
    skeleton = work / 'etc'
    shim = work / 'pane-mcp'
    policy_path = skeleton / 'grok' / 'requirements.toml'
    name_policy_path = skeleton / 'grok' / 'managed_config.toml'
    # Exactly one argv identity; name-only matching would admit a same-name foreign server.
    policy = ('allow_managed_mcp_servers_only = true\n'
              'enable_all_project_mcp_servers = false\n'
              '[[allowed_mcp_servers]]\nserver_command = ' + json.dumps([str(command), *args]) + '\n')
    # A selector list is OR, not AND. Separate native layers must enforce the
    # conjunction. This is a candidate until native CI proves their intersection.
    name_policy = '[[allowed_mcp_servers]]\nserver_name = "lampway_pane"\n'
    mounts, placeholders = [], []
    for source in sorted(etc.iterdir()):
        if source.name == 'grok':
            if not source.is_dir():
                raise ValueError('native grok policy directory is not a directory')
            children = sorted(source.iterdir())
        else:
            children = [source]
        for child in children:
            rel = child.relative_to(etc)
            destination = Path('/etc') / rel
            if child.is_symlink():
                placeholders.append({'path': str(rel), 'kind': 'symlink', 'target': os.readlink(child)})
            else:
                placeholders.append({'path': str(rel), 'kind': 'directory' if child.is_dir() else 'file'})
                mounts += ['--bind', str(child), str(destination)]
    argv = [str(bwrap), '--unshare-user', '--uid', str(os.getuid()), '--gid', str(os.getgid()),
            '--unshare-pid', '--die-with-parent', '--cap-drop', 'ALL', '--bind', '/', '/',
            '--proc', '/proc', '--ro-bind', str(work), str(work),
            '--ro-bind', str(skeleton), '/etc', *mounts, '--ro-bind', str(shim), str(command.resolve()),
            '--chdir', str(cwd), '--', str(native), '--leader-socket', str(inner), '--cwd', str(cwd), '--', task]
    return {'argv': argv, 'cwd': str(cwd), 'policy': policy, 'policy_path': str(policy_path),
            'name_policy': name_policy, 'name_policy_path': str(name_policy_path),
            'work': str(work), 'skeleton': str(skeleton), 'placeholders': placeholders,
            'config_path': str(path), 'root': str(root), 'inner_socket': str(inner), 'outer_socket': str(outer),
            'directory_modes': modes, 'shim': str(shim), 'connector': str(command),
            'shim_source': _shim_source(path.with_name('mcp.json'), root)}


def prepare(plan):
    """Only the pane-owned boundary is written; bind sources are never copied."""
    work = Path(plan['work'])
    work.mkdir(mode=0o700, exist_ok=False)
    skeleton = Path(plan['skeleton'])
    skeleton.mkdir(mode=plan['directory_modes']['etc'])
    skeleton.chmod(plan['directory_modes']['etc'])
    (skeleton / 'grok').mkdir(mode=plan['directory_modes']['grok'])
    (skeleton / 'grok').chmod(plan['directory_modes']['grok'])
    for item in plan['placeholders']:
        target = skeleton / item['path']
        if item['kind'] == 'symlink':
            target.symlink_to(item['target'])
        elif item['kind'] == 'directory':
            target.mkdir(mode=0o755)
        else:
            target.touch(mode=0o600)
    policy = Path(plan['policy_path'])
    policy.write_text(plan['policy'])
    policy.chmod(0o400)
    name_policy = Path(plan['name_policy_path'])
    name_policy.write_text(plan['name_policy']); name_policy.chmod(0o400)
    shim = Path(plan['shim'])
    shim.write_text(plan['shim_source']); shim.chmod(0o500)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Candidate Grok worker isolation; readiness remains unverified.')
    parser.add_argument('--config', required=True)
    parser.add_argument('--task', help='Literal worker task; use --task=TEXT for leading hyphens.')
    options = parser.parse_args(argv)
    try:
        plan = build_plan(options.config, task=options.task)
        prepare(plan)
        # Native wrap changes the child cwd to HOME; restore the server-pinned project explicitly.
        os.chdir(plan['cwd'])
        env = dict(os.environ)
        env['LAMPWAY_HERMES_CONNECTOR_CONFIG'] = str(Path(plan['config_path']).with_name('mcp.json'))
        env['LAMPWAY_HERMES_CONNECTOR_ROOT'] = plan['root']
        os.execve(plan['argv'][0], plan['argv'], env)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'Grok worker not started: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
