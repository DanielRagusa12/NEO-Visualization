import importlib.util
import json
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('neo_dev_server', ROOT / 'dev_server.py')
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


class QuietHandler(dev.PreviewHandler):
    def log_message(self, *_):
        pass


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = partial(QuietHandler, directory=str(dev.STATIC_ROOT))
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_root_is_the_real_site(self):
        with urlopen(self.base + '/') as response:
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            html = response.read().decode()
        self.assertIn('motion.js', html)
        self.assertIn('Shapes, spin axes, rotation periods, and tumbling are illustrative', html)
        self.assertNotIn('LOCAL PROTOTYPE', html)

    def test_data_is_explicitly_synthetic(self):
        with urlopen(self.base + '/data/latest.json') as response:
            self.assertEqual(response.headers['X-NEO-Fixture'], 'synthetic')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            data = json.load(response)
        self.assertIn('Synthetic', data['_fixture'])
        self.assertEqual(len(data['neos']), 6)

    def test_data_head_has_no_body(self):
        with urlopen(Request(self.base + '/data/latest.json', method='HEAD')) as response:
            self.assertGreater(int(response.headers['Content-Length']), 0)
            self.assertEqual(response.read(), b'')

    def test_media_content_types(self):
        for name, expected in [('cratered-poster.webp', 'image/webp'),
                               ('cratered-spin-30fps.webm', 'video/webm')]:
            path = '/assets/models/v1/neos/' + name
            with urlopen(Request(self.base + path, method='HEAD')) as response:
                self.assertEqual(response.headers['Content-Type'], expected)

    def test_authoring_files_are_not_served(self):
        for path in ['/art/neo-asset-studio.blend', '/../art/neo-asset-studio.blend',
                     '/art/neo-varied-motion-studio.blend', '/../art/neo-varied-motion-studio.blend',
                     '/tests/fixtures/latest.json']:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()


if __name__ == '__main__':
    unittest.main()
