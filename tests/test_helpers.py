"""Offline behavior checks; no provider calls or configured credentials are used."""

import contextlib
import functools
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def load_helper(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'video/scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


narrate = load_helper('narrate')
serve = load_helper('serve')


class NarrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'scenes.json'
        self.manifest.write_text(json.dumps([{'id': 'summary', 'narration': 'Example narration.'}]))
        self.output = self.root / 'audio'

    def invoke(self, *extra):
        argv = ['narrate.py', str(self.manifest), '--out', str(self.output), *extra]
        with mock.patch('sys.argv', argv), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return narrate.main()

    def test_no_credentials_fails_without_network(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(narrate.urllib.request, 'urlopen') as request:
            self.assertEqual(self.invoke(), 2)
            request.assert_not_called()

    def test_invalid_ids_are_rejected_before_network(self):
        self.manifest.write_text(json.dumps([{'id': '../escape', 'narration': 'Example.'}]))
        with mock.patch.object(narrate.urllib.request, 'urlopen') as request:
            self.assertEqual(self.invoke(), 2)
            request.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_private_key_file_generates_receipt_and_cached_audio_needs_no_key(self):
        # Deliberately synthetic fixture; never a real credential.
        key_file = self.root / 'synthetic-key'
        key_file.write_text('offline-test-placeholder')
        response = mock.MagicMock()
        response.headers = {'Content-Type': 'audio/mpeg', 'X-Generation-Id': 'offline-generation'}
        audio = b'example audio bytes' * 20
        response.read.return_value = audio
        response.__enter__.return_value = response
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(narrate.urllib.request, 'urlopen', return_value=response) as request:
            self.assertEqual(self.invoke('--key-file', str(key_file)), 0)
            self.assertEqual(request.call_count, 1)
        receipt = json.loads((self.output / 'summary.json').read_text())
        self.assertEqual(receipt['audio_sha256'], hashlib.sha256(audio).hexdigest())
        self.assertNotIn(key_file.read_text(), json.dumps(receipt))
        key_file.unlink()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(narrate.urllib.request, 'urlopen') as request:
            self.assertEqual(self.invoke(), 0)
            request.assert_not_called()


class ExportServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        (cls.root / 'index.html').write_text('<h1>Reviewed export</h1>')
        (cls.root / 'clip.mp4').write_bytes(b'0123456789')
        (cls.root / '.hidden').write_text('private fixture')
        (cls.root / 'linked.mp4').symlink_to(cls.root / 'clip.mp4')
        (cls.root / 'empty').mkdir()

        class QuietHandler(serve.ExportHandler):
            def log_message(self, *args):
                pass

        # Deliberately synthetic fixture key.
        cls.key = 'k' * 43
        handler = functools.partial(QuietHandler, directory=str(cls.root), key=cls.key)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def get(self, path, keyed=True, **headers):
        prefix = '/' + self.key if keyed else ''
        return urllib.request.urlopen(urllib.request.Request(self.base + prefix + path, headers=headers), timeout=5)

    def assert_status(self, path, status, keyed=True):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get(path, keyed=keyed)
        self.assertEqual(caught.exception.code, status)
        caught.exception.close()

    def test_index_and_full_file(self):
        with self.get('/') as response:
            self.assertIn(b'Reviewed export', response.read())
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
            self.assertEqual(response.headers['X-Robots-Tag'], 'noindex, nofollow')
        with self.get('/clip.mp4') as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b'0123456789')

    def test_partial_suffix_and_open_ranges(self):
        for requested, expected, interval in [('bytes=2-5', b'2345', '2-5'), ('bytes=-3', b'789', '7-9'), ('bytes=8-', b'89', '8-9')]:
            with self.subTest(requested=requested), self.get('/clip.mp4', Range=requested) as response:
                self.assertEqual(response.status, 206)
                self.assertEqual(response.headers['Content-Range'], 'bytes ' + interval + '/10')
                self.assertEqual(response.read(), expected)

    def test_invalid_range_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get('/clip.mp4', Range='bytes=99-100')
        self.assertEqual(caught.exception.code, 416)
        caught.exception.close()

    def test_hidden_symlink_traversal_and_listing_are_rejected(self):
        for path in ['/.hidden', '/linked.mp4', '/%2e%2e/outside', '/empty/']:
            with self.subTest(path=path):
                self.assert_status(path, 403)

    def test_paths_without_the_key_are_not_found(self):
        for path in ['/', '/index.html', '/clip.mp4', '/' + 'x' * 43 + '/clip.mp4', '/' + self.key[:-1] + '/clip.mp4']:
            with self.subTest(path=path):
                self.assert_status(path, 404, keyed=False)

    def test_bare_key_redirects_to_the_directory(self):
        with self.get('') as response:
            self.assertEqual(response.url, self.base + '/' + self.key + '/')
            self.assertIn(b'Reviewed export', response.read())


class KeyFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.export = self.root / 'public'
        self.export.mkdir()

    def test_key_file_is_created_private_and_reused(self):
        key_file = self.root / 'access.key'
        key = serve.load_key(key_file, self.export)
        self.assertRegex(key, serve.KEY_PATTERN)
        self.assertEqual(key_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(serve.load_key(key_file, self.export), key)

    def test_without_key_file_each_key_is_new(self):
        self.assertNotEqual(serve.load_key(None, self.export), serve.load_key(None, self.export))

    def test_key_file_inside_export_is_refused(self):
        with self.assertRaises(SystemExit):
            serve.load_key(self.export / 'access.key', self.export)
        self.assertFalse((self.export / 'access.key').exists())

    def test_short_key_is_refused(self):
        key_file = self.root / 'access.key'
        key_file.write_text('short')
        with self.assertRaises(SystemExit):
            serve.load_key(key_file, self.export)


if __name__ == '__main__':
    unittest.main()
