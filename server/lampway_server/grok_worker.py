# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Candidate Grok worker boundary; it never makes the adapter worker-ready.

The native Grok `wrap` command may invoke this module. Only owned pane metadata
is read. Explicit current human consent can enable a temporary HOME directory
view and Cursor MCP attribution mask, with the disclosed immediate-name limits.
Existing child backing paths, login and native settings remain native. Existing
policies are bind-mounted; an occupied additional requirements slot refuses.
No host policy, credential or native configuration file is changed. Actual namespace,
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

NATIVE_SHA256 = 'c80de0155706ff2d995623887b102f2d0abd2c62b2643dea3a0cebaf7dd724d5'
COMPAT_VERSION = 1
COMPAT_EFFECTS = (
    'Only explicitly enrolled Grok swarm workers use this temporary compatibility view; Grok MAIN is unchanged.',
    'Inside the worker, Cursor MCP imports are disabled and ~/.cursor/mcp.json is replaced by a read-only canonical-name attribution entry. The native Grok lampway_pane connector remains the actual route.',
    'Inside Grok swarm workers, remote MCP connectors using HTTP or SSE are denied. The native STDIO lampway_pane connector is retained; this restriction does not disable model access or built-in network tools and does not establish worker readiness.',
    'A temporary read-only HOME directory view preserves existing child paths and backing. In-place file writes and writes inside backed child directories remain available, except for the masked Cursor MCP file. Workers cannot create or remove immediate HOME names, rename them or atomically replace them.',
    'The same split applies to ~/.cursor: existing children other than mcp.json retain backing and in-place file writes. Creating new immediate ~/.cursor names, deleting, renaming or atomically replacing immediate entries, and changes to the masked mcp.json are refused. An absent ~/.cursor exists only in the temporary view.',
    'HOME directory identity changes inside the worker. HOME paths, native login, persona, model settings, budgets and built-in tools are retained; no existing config or credential contents are copied and no persistent host file or directory is created.',
    'The existing restrictive MCP policies and pane binding remain enforced. Consent adds no project trust, security grant, outbound route or account call, and does not establish native worker readiness.',
)
COMPAT_EFFECTS_SHA256 = hashlib.sha256(json.dumps(
    {'version': COMPAT_VERSION, 'effects': list(COMPAT_EFFECTS)}, sort_keys=True).encode()).hexdigest()


def compat_metadata(home, project_root, state_dir):
    """Describe exact already-consented scope; runtime independently rechecks it."""
    return {'version': COMPAT_VERSION, 'home': str(_absolute(str(home))),
            'project_root': str(_absolute(str(project_root))), 'state_dir': str(_absolute(str(state_dir)))}


def _compat_consent(view, cwd):
    if not isinstance(view, dict) or set(view) != {'version', 'home', 'project_root', 'state_dir'}:
        raise ValueError('Grok compatibility enrollment requires exact version, HOME, project_root and state_dir')
    if type(view['version']) is not int or view['version'] != COMPAT_VERSION:
        raise ValueError('Grok compatibility enrollment version is not current')
    home = _absolute(view['home'])
    if str(home) != os.environ.get('HOME') or home.resolve() != home:
        raise ValueError('Grok compatibility HOME must remain the original native HOME')
    if home == Path('/') or home == Path('/etc') or home.is_relative_to('/etc') or cwd == home or cwd.is_relative_to(home / '.cursor'):
        raise ValueError('Grok compatibility HOME view overlaps native policy or project discovery; choose a distinct project directory')
    project = _absolute(view['project_root']); state = _absolute(view['state_dir'])
    if project.resolve() != project or not cwd.is_relative_to(project):
        raise ValueError('Grok compatibility project_root differs from its owned worker scope')
    from . import capabilities as CAP
    check = getattr(CAP, 'grok_worker_problem', None)
    if check is None or (problem := check(str(project), state_dir=str(state))):
        raise ValueError('Grok compatibility consent refused: ' + (problem if check else 'current consent interface is unavailable'))
    return home


def _entry_identity(path):
    info = path.lstat()
    kind = 'directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'symlink' if stat.S_ISLNK(info.st_mode) else None
    if kind is None or (kind == 'symlink' and info.st_uid != os.getuid()):
        raise ValueError('Grok compatibility view cannot preserve this native entry')
    row = {'path': str(path), 'kind': kind, 'dev': info.st_dev, 'ino': info.st_ino,
           'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
    if kind == 'symlink':
        row['target'] = os.readlink(path)
    return row


def _owned_view_hash(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 1024 * 1024:
            raise ValueError('Grok compatibility owned view file is invalid')
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _compat_sources(home):
    if home.is_symlink() or not home.is_dir() or home.stat().st_uid != os.getuid():
        raise ValueError('Grok compatibility HOME must be an owned native directory')
    home_mode = _directory_access(home)
    children = [_entry_identity(p) for p in sorted(home.iterdir())]
    cursor = home / '.cursor'
    cursor_children = []
    cursor_mode = 0o700
    if os.path.lexists(cursor):
        if cursor.is_symlink() or not cursor.is_dir() or cursor.stat().st_uid != os.getuid():
            raise ValueError('Grok compatibility .cursor must be an owned directory, never a redirect')
        cursor_mode = _directory_access(cursor)
        cursor_children = [_entry_identity(p) for p in sorted(cursor.iterdir())]
        masked = next((p for p in cursor_children if Path(p['path']).name == 'mcp.json'), None)
        if masked and masked['kind'] != 'file':
            raise ValueError('Grok compatibility cannot mask a redirected or non-file Cursor MCP source')
    return {'home': _entry_identity(home), 'home_mode': home_mode, 'children': children,
            'cursor_mode': cursor_mode, 'cursor_children': cursor_children}


def compat_preflight(view, cwd):
    """Validate consent and native path metadata before probes or owned staging."""
    cwd = _absolute(str(cwd))
    home = _compat_consent(view, cwd)
    # Only metadata is inspected. Native file contents are never read or copied.
    sources = _compat_sources(home)
    for key in ('GROK_HOME', 'GROK_AUTH_PATH'):
        native = os.environ.get(key)
        if native and Path(native).resolve() == home / '.cursor' / 'mcp.json':
            raise ValueError('Grok compatibility cannot mask a native login/configuration location')
        if key == 'GROK_HOME' and native and Path(native).resolve() == home:
            raise ValueError('Grok compatibility cannot split a HOME used directly as GROK_HOME')
    return {'home': str(home), 'sources': sources, 'effects_sha256': COMPAT_EFFECTS_SHA256}


def _compat_plan(view, cwd, work, command, args):
    checked = compat_preflight(view, cwd)
    home = Path(checked['home'])
    sources = checked['sources']
    skeleton = work / 'home-view'
    sentinel = json.dumps({'mcpServers': {'lampway_pane': {'command': str(command), 'args': args, 'enabled': True}}}, sort_keys=True) + '\n'
    mounts = ['--ro-bind', str(skeleton), str(home)]
    entries = []
    for row in sources['children']:
        if Path(row['path']).name != '.cursor':
            entries.append({**row, 'relative': Path(row['path']).name})
    for row in sources['cursor_children']:
        if Path(row['path']).name != 'mcp.json':
            entries.append({**row, 'relative': '.cursor/' + Path(row['path']).name})
    for row in entries:
        if row['kind'] != 'symlink':
            mounts += ['--bind', row['path'], str(home / row['relative'])]
    mounts += ['--setenv', 'GROK_CURSOR_MCPS_ENABLED', 'false']
    digest = hashlib.sha256(json.dumps({'sources': sources, 'mounts': mounts, 'sentinel': sentinel}, sort_keys=True).encode()).hexdigest()
    return {'version': COMPAT_VERSION, 'enrollment': view, 'sources': sources, 'entries': entries,
            'skeleton': str(skeleton), 'sentinel_path': str(skeleton / '.cursor' / 'mcp.json'),
            'sentinel': sentinel, 'sentinel_sha256': hashlib.sha256(sentinel.encode()).hexdigest(),
            'mounts': mounts, 'manifest_sha256': digest, 'effects_sha256': COMPAT_EFFECTS_SHA256}


def _validate_compat(plan, *, prepared=False):
    view = plan.get('compat_view')
    if view is None:
        return
    home = _compat_consent(view['enrollment'], Path(plan['cwd']))
    if _compat_sources(home) != view['sources']:
        raise ValueError('Grok compatibility native source identities or membership changed')
    digest = hashlib.sha256(json.dumps({'sources': view['sources'], 'mounts': view['mounts'], 'sentinel': view['sentinel']}, sort_keys=True).encode()).hexdigest()
    if digest != view['manifest_sha256'] or view['effects_sha256'] != COMPAT_EFFECTS_SHA256:
        raise ValueError('Grok compatibility plan integrity changed')
    if prepared:
        sentinel = Path(view['sentinel_path'])
        if sentinel.is_symlink() or sentinel.stat().st_uid != os.getuid() or stat.S_IMODE(sentinel.stat().st_mode) != 0o400 or _owned_view_hash(sentinel) != view['sentinel_sha256']:
            raise ValueError('Grok compatibility sentinel integrity changed')
        if _prepared_compat_digest(view) != view.get('prepared_sha256'):
            raise ValueError('Grok compatibility prepared mount identities changed')


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
                '--unshare-pid', '--die-with-parent', '--cap-drop', 'ALL', '--bind', '/', '/', '--dev', '/dev', '--proc', '/proc', '--', '/bin/true']}


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
    enrollment = config.get('compat_view')
    if enrollment is not None:
        _compat_consent(enrollment, _absolute(config.get('cwd')))
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
              # Command allow entries constrain STDIO only. A separate name
              # layer can grant the same name on HTTP/SSE, so deny all URLs.
              '[[denied_mcp_servers]]\nserver_url = "*"\n'
              '[[allowed_mcp_servers]]\nserver_command = ' + json.dumps([str(command), *args]) + '\n')
    # A selector list is OR, not AND. Separate native layers must enforce the
    # conjunction. This is a candidate until native CI proves their intersection.
    name_policy = '[[allowed_mcp_servers]]\nserver_name = "lampway_pane"\n'
    compat = _compat_plan(enrollment, cwd, work, command, args) if enrollment is not None else None
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
            '--unshare-pid', '--die-with-parent', '--cap-drop', 'ALL', '--bind', '/', '/', '--dev', '/dev',
            '--proc', '/proc', '--ro-bind', str(work), str(work),
            '--ro-bind', str(skeleton), '/etc', *mounts, '--ro-bind', str(shim), str(command.resolve()),
            *(compat['mounts'] if compat else []),
            *(['--ro-bind', str(work), str(work), '--ro-bind', str(shim), str(command.resolve())] if compat else []),
            '--chdir', str(cwd), '--', str(native), '--leader-socket', str(inner), '--cwd', str(cwd), '--', task]
    plan = {'argv': argv, 'cwd': str(cwd), 'policy': policy, 'policy_path': str(policy_path),
            'name_policy': name_policy, 'name_policy_path': str(name_policy_path),
            'work': str(work), 'skeleton': str(skeleton), 'placeholders': placeholders,
            'config_path': str(path), 'root': str(root), 'inner_socket': str(inner), 'outer_socket': str(outer),
            'directory_modes': modes, 'shim': str(shim), 'connector': str(command),
            'shim_source': _shim_source(path.with_name('mcp.json'), root)}
    if compat is not None:
        plan['compat_view'] = compat
    return plan


def prepare(plan):
    """Only the pane-owned boundary is written; bind sources are never copied."""
    _validate_compat(plan)
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
    if (view := plan.get('compat_view')) is not None:
        home = Path(view['skeleton'])
        home.mkdir(mode=view['sources']['home_mode']); home.chmod(view['sources']['home_mode'])
        cursor = home / '.cursor'
        cursor.mkdir(mode=view['sources']['cursor_mode']); cursor.chmod(view['sources']['cursor_mode'])
        for row in view['entries']:
            target = home / row['relative']
            if row['kind'] == 'symlink':
                target.symlink_to(row['target'])
            elif row['kind'] == 'directory':
                target.mkdir(mode=0o755)
            else:
                target.touch(mode=0o600)
        sentinel = Path(view['sentinel_path'])
        sentinel.write_text(view['sentinel']); sentinel.chmod(0o400)
        view['prepared_sha256'] = _prepared_compat_digest(view)
        _validate_compat(plan, prepared=True)


def _prepared_compat_digest(view):
    root = Path(view['skeleton'])
    rows = []
    for path in [root, *sorted(root.rglob('*'))]:
        row = _entry_identity(path)
        row['path'] = str(path.relative_to(root))
        if row['uid'] != os.getuid():
            raise ValueError('Grok compatibility owned view identity changed')
        if row['kind'] == 'file':
            row['sha256'] = _owned_view_hash(path)
        rows.append(row)
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


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
        _validate_compat(plan, prepared=True)
        os.execve(plan['argv'][0], plan['argv'], env)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'Grok worker not started: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
