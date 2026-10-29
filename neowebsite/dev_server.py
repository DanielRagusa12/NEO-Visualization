"""Serve the real static site locally with explicitly synthetic test data."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / 'static'
FIXTURE = ROOT / 'tests' / 'fixtures' / 'latest.json'


class PreviewHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        '.webm': 'video/webm',
        '.webp': 'image/webp',
    }

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def send_fixture(self, include_body):
        data = FIXTURE.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-NEO-Fixture', 'synthetic')
        self.end_headers()
        if include_body:
            self.wfile.write(data)

    def do_GET(self):
        if urlsplit(self.path).path == '/data/latest.json':
            self.send_fixture(True)
        else:
            super().do_GET()

    def do_HEAD(self):
        if urlsplit(self.path).path == '/data/latest.json':
            self.send_fixture(False)
        else:
            super().do_HEAD()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    handler = partial(PreviewHandler, directory=str(STATIC_ROOT))
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'Local site: http://127.0.0.1:{args.port}/', flush=True)
        print('Data is synthetic. No NASA, AWS, or production requests are made by this server.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
