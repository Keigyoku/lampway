#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pack explicit owned diagnostic roots without changing native evidence paths.

Colon names remain inside a gzip tar; symlinks are never followed. Special
resources are recorded as omissions, not acceptance evidence. Missing roots are
NOTRUN. The embedded manifest and separate uploadable JSON are identical.
"""
import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile


def _absolute(path):
    path = Path(path)
    if '..' in path.parts:
        raise ValueError('parent traversal is not an owned artifact path')
    return path.absolute()


@contextmanager
def _directory(path):
    """Open each directory component without following redirected parents."""
    path = _absolute(path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        yield fd
    finally:
        os.close(fd)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _kind(info):
    for predicate, name in [(stat.S_ISREG, 'file'), (stat.S_ISDIR, 'directory'),
                            (stat.S_ISLNK, 'symlink'), (stat.S_ISSOCK, 'socket'),
                            (stat.S_ISFIFO, 'fifo'), (stat.S_ISCHR, 'character-device'),
                            (stat.S_ISBLK, 'block-device')]:
        if predicate(info.st_mode): return name
    return 'unknown'


def _entry(name, info):
    entry = tarfile.TarInfo(name)
    entry.mode = stat.S_IMODE(info.st_mode)
    entry.uid, entry.gid, entry.mtime = info.st_uid, info.st_gid, info.st_mtime
    return entry


class _HashReader:
    def __init__(self, stream):
        self.stream = stream; self.sha = hashlib.sha256()
    def read(self, size=-1):
        data = self.stream.read(size); self.sha.update(data); return data


def _walk(tar, fd, prefix, root_device, manifest):
    before = os.fstat(fd)
    if before.st_uid != os.getuid() or before.st_dev != root_device:
        raise ValueError('artifact directory changed ownership/device')
    names = sorted(os.listdir(fd))
    for name in names:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if info.st_uid != os.getuid() or info.st_dev != root_device:
            raise ValueError('artifact entry is outside the owned root/device')
        archive_name = prefix + '/' + name
        kind = _kind(info)
        row = {'path': archive_name, 'type': kind, 'mode': stat.S_IMODE(info.st_mode),
               'uid': info.st_uid, 'gid': info.st_gid, 'mtime_ns': info.st_mtime_ns}
        entry = _entry(archive_name, info)
        if kind == 'directory':
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                if _identity(os.fstat(child)) != _identity(info):
                    raise ValueError('artifact directory changed before opening')
                entry.type = tarfile.DIRTYPE; tar.addfile(entry)
                row['included'] = True; manifest['entries'].append(row)
                _walk(tar, child, archive_name, root_device, manifest)
                if _identity(os.fstat(child)) != _identity(info):
                    raise ValueError('artifact directory changed during packing')
            finally: os.close(child)
        elif kind == 'file':
            child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(child, 'rb') as stream:
                if _identity(os.fstat(stream.fileno())) != _identity(info):
                    raise ValueError('artifact file changed before opening')
                reader = _HashReader(stream); entry.size = info.st_size
                tar.addfile(entry, reader)
                if _identity(os.fstat(stream.fileno())) != _identity(info):
                    raise ValueError('artifact file changed during packing')
                row.update(included=True, size=info.st_size, sha256=reader.sha.hexdigest())
                manifest['entries'].append(row)
        elif kind == 'symlink':
            target = os.readlink(name, dir_fd=fd)
            entry.type = tarfile.SYMTYPE; entry.linkname = target; tar.addfile(entry)
            row.update(included=True, target=target, dereferenced=False)
            manifest['entries'].append(row)
        else:
            row.update(included=False, omission='nonportable native resource; not acceptance evidence')
            manifest['entries'].append(row)
        if _identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) != _identity(info):
            raise ValueError('artifact entry changed during packing')
    if sorted(os.listdir(fd)) != names or _identity(os.fstat(fd)) != _identity(before):
        raise ValueError('artifact root changed during packing')


@contextmanager
def _new_output(path):
    path = _absolute(path)
    with _directory(path.parent) as parent:
        fd = os.open(path.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        identity = os.fstat(fd)
        try:
            with os.fdopen(fd, 'w+b') as stream:
                yield stream
                stream.flush(); os.fsync(stream.fileno())
                current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                    raise ValueError('artifact output was redirected during packing')
        except BaseException:
            try:
                current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                    os.unlink(path.name, dir_fd=parent)
            except FileNotFoundError: pass
            raise


def pack(roots, archive, manifest_path, *, root_parent):
    root_parent = _absolute(root_parent)
    roots = [_absolute(root) for root in roots]
    if any(root == root_parent or not root.is_relative_to(root_parent) for root in roots):
        raise ValueError('input root escapes explicit owned output parent')
    archive, manifest_path = _absolute(archive), _absolute(manifest_path)
    if not roots or len(set(roots)) != len(roots):
        raise ValueError('explicit distinct owned output roots required')
    if archive == manifest_path or any(p.is_relative_to(root) for root in roots
                                      for p in (archive, manifest_path)):
        raise ValueError('artifact outputs must be distinct and outside input roots')
    manifest = {'version': 1, 'acceptance': False, 'roots': [], 'entries': []}
    with _new_output(archive) as output, _new_output(manifest_path) as separate:
        with tarfile.open(fileobj=output, mode='w:gz', format=tarfile.PAX_FORMAT,
                          dereference=False) as tar:
            for index, root in enumerate(roots):
                prefix = f'root-{index:03d}'
                try:
                    root.lstat()
                except FileNotFoundError:
                    manifest['roots'].append({'input': str(root), 'archive_prefix': prefix,
                                              'status': 'NOTRUN', 'reason': 'owned output root missing'})
                    continue
                with _directory(root) as fd:
                    info = os.fstat(fd)
                    if info.st_uid != os.getuid():
                        raise ValueError('input root is not owned by current fixture user')
                    manifest['roots'].append({'input': str(root), 'archive_prefix': prefix, 'status': 'PACKED'})
                    entry = _entry(prefix, info); entry.type = tarfile.DIRTYPE; tar.addfile(entry)
                    _walk(tar, fd, prefix, info.st_dev, manifest)
            body = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
            entry = tarfile.TarInfo('artifact-manifest.json'); entry.size = len(body); entry.mode = 0o600
            tar.addfile(entry, io.BytesIO(body)); separate.write(body)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootparent', '--root-parent', type=Path, required=True)
    parser.add_argument('--owned-root', '--root', type=Path, action='append', required=True)
    parser.add_argument('--archive', '--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    options = parser.parse_args()
    result = pack(options.owned_root, options.archive, options.manifest, root_parent=options.rootparent)
    print(json.dumps({'roots': result['roots'], 'acceptance': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
