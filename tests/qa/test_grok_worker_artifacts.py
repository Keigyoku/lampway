# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Evidence packer controls; no native launch or network connection."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('grok_artifacts', Path(__file__).with_name('grok_worker_artifacts.py'))
P = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(P)


class Artifacts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.getenv('LAMPWAY_TEST_ROOT'))
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'native'; self.root.mkdir()
        self.archive, self.manifest = self.parent / 'evidence.tar.gz', self.parent / 'manifest.json'

    def pack(self, roots=None):
        return P.pack(roots or [self.root], self.archive, self.manifest, root_parent=self.parent)

    def test_colon_tree_preserves_raw_receipts_and_exact_manifest(self):
        pane = self.root / 'state/panes/w1:p1'; pane.mkdir(parents=True)
        (pane / 'receipt.json').write_text('{"status":"FAILED"}')
        rejected = pane / 'grok-worker-boundary/etc/adduser.conf'
        rejected.parent.mkdir(parents=True); rejected.write_text('owned synthetic placeholder\n')
        (pane / 'config.toml').write_text('owned=true\n'); (pane / 'native.log').write_text('actual failure\n')
        (pane / 'source.sha256').write_text('synthetic-source-fingerprint\n')
        (pane / 'native.log').chmod(0o640)
        result = self.pack()
        with tarfile.open(self.archive) as tar:
            self.assertEqual(tar.extractfile('root-000/state/panes/w1:p1/receipt.json').read(), b'{"status":"FAILED"}')
            self.assertEqual(tar.getmember('root-000/state/panes/w1:p1/native.log').mode, 0o640)
            self.assertEqual(tar.extractfile('root-000/state/panes/w1:p1/grok-worker-boundary/etc/adduser.conf').read(),
                             b'owned synthetic placeholder\n')
            self.assertEqual(tar.extractfile('artifact-manifest.json').read(), self.manifest.read_bytes())
        self.assertFalse(result['acceptance'])
        self.assertEqual(json.loads(self.manifest.read_text()), result)
        self.assertTrue((pane / 'receipt.json').exists())

    def test_external_and_broken_symlinks_are_links_not_content(self):
        outside = self.parent / 'outside'; outside.write_text('DO_NOT_READ')
        (self.root / 'external').symlink_to(outside)
        (self.root / 'broken').symlink_to(self.parent / 'absent')
        with patch.object(P._HashReader, 'read', side_effect=AssertionError('outside file read')):
            result = self.pack()
        with tarfile.open(self.archive) as tar:
            self.assertTrue(tar.getmember('root-000/external').issym())
            self.assertEqual(tar.getmember('root-000/external').linkname, str(outside))
            self.assertTrue(tar.getmember('root-000/broken').issym())
        self.assertTrue(all(row['dereferenced'] is False for row in result['entries']))

    def test_socket_and_fifo_omissions_are_explicit(self):
        # AF_UNIX owned filesystem resource only; no connect, native or provider.
        sock = socket.socket(socket.AF_UNIX); self.addCleanup(sock.close)
        sock.bind(str(self.root / 'native.sock')); os.mkfifo(self.root / 'pipe')
        result = self.pack()
        self.assertEqual({r['type'] for r in result['entries']}, {'socket', 'fifo'})
        self.assertTrue(all(r['included'] is False and r['omission'] for r in result['entries']))
        with tarfile.open(self.archive) as tar:
            self.assertNotIn('root-000/native.sock', tar.getnames())

    def test_missing_root_is_notrun_and_other_roots_retained(self):
        (self.root / 'receipt.json').write_text('original failure')
        result = self.pack([self.root, self.parent / 'missing'])
        self.assertEqual([r['status'] for r in result['roots']], ['PACKED', 'NOTRUN'])

    def test_existing_destination_refused_without_overwrite(self):
        self.archive.write_text('previous artifact')
        with self.assertRaises(FileExistsError): self.pack()
        self.assertEqual(self.archive.read_text(), 'previous artifact')
        self.assertFalse(self.manifest.exists())

    def test_existing_manifest_refused_without_leaking_new_archive(self):
        self.manifest.write_text('previous manifest')
        with self.assertRaises(FileExistsError): self.pack()
        self.assertEqual(self.manifest.read_text(), 'previous manifest')
        self.assertFalse(self.archive.exists())

    def test_root_or_destination_redirection_refused(self):
        alias = self.parent / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError): self.pack([alias])
        self.assertFalse(self.archive.exists())
        self.archive = alias / 'evidence.tar.gz'
        with self.assertRaises((OSError, ValueError)): self.pack()
        self.assertFalse((self.root / 'evidence.tar.gz').exists())

    def test_path_escape_and_output_inside_root_refused(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.pack([self.parent.parent / 'elsewhere'])
        with self.assertRaisesRegex(ValueError, 'traversal'):
            self.pack([self.root / '..' / 'native'])
        self.archive = self.root / 'recursive.tar.gz'
        with self.assertRaisesRegex(ValueError, 'outside'): self.pack()

    def test_changed_open_destination_refused_without_deleting_replacement(self):
        (self.root / 'data').write_text('original evidence')
        original = P._HashReader.read
        changed = False
        def redirected(reader, size=-1):
            nonlocal changed
            data = original(reader, size)
            if not changed:
                changed = True
                self.archive.unlink(); self.archive.write_text('replacement must survive')
            return data
        with patch.object(P._HashReader, 'read', redirected):
            with self.assertRaisesRegex(ValueError, 'redirected'): self.pack()
        self.assertEqual(self.archive.read_text(), 'replacement must survive')

    def test_changed_open_input_refused_and_partial_outputs_removed(self):
        item = self.root / 'live.log'; item.write_text('old')
        original = P._HashReader.read
        def changed(reader, size=-1):
            data = original(reader, size)
            item.write_text('changed during read')
            return data
        with patch.object(P._HashReader, 'read', changed):
            with self.assertRaisesRegex(ValueError, 'changed'): self.pack()
        self.assertFalse(self.archive.exists()); self.assertFalse(self.manifest.exists())
        self.assertEqual(item.read_text(), 'changed during read')


if __name__ == '__main__': unittest.main()
