"""Check the private gateway's HTTP exposure without reading real session data."""
import http.client
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server


class GatewayHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def request(self, path, method="GET"):
        conn = http.client.HTTPConnection(*self.httpd.server_address, timeout=5)
        try:
            conn.request(method, path)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_only_frontend_assets_are_served(self):
        for path in ("/", "/app.js?v=1", "/styles.css", "/manifest.webmanifest"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 200)
        for path in ("/server.py", "/.git/config", "/.env", "/reference/",
                     "/docs/DEV-PLAN.md", "/%2e%2e/server.py", "/tools/"):
            for method in ("GET", "HEAD"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(path, method)[0], 404)

    def test_head_returns_headers_without_body(self):
        status, headers, body = self.request("/", "HEAD")
        self.assertEqual(status, 200)
        self.assertGreater(int(headers["Content-Length"]), 0)
        self.assertEqual(body, b"")

    def test_json_routes_remain_available_without_wildcard_cors(self):
        with patch.object(server, "get_usage", return_value={"totals": {}}):
            status, headers, body = self.request("/api/usage")
            self.assertEqual(status, 200)
            self.assertEqual(body, b'{"totals": {}}')
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(self.request("/api/usage", "HEAD")[2], b"")


if __name__ == "__main__":
    unittest.main()
