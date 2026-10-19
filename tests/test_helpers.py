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

        handler = functools.partial(QuietHandler, directory=str(cls.root))
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

    def get(self, path, **headers):
        return urllib.request.urlopen(urllib.request.Request(self.base + path, headers=headers), timeout=5)

    def test_index_and_full_file(self):
        with self.get('/') as response:
            self.assertIn(b'Reviewed export', response.read())
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
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
                self.get(path)
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()


if __name__ == '__main__':
    unittest.main()
