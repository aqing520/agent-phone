"""Check the private gateway's HTTP exposure without reading real session data."""
import http.client
import json
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

    def request(self, path, method="GET", body=None, headers=None):
        conn = http.client.HTTPConnection(*self.httpd.server_address, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_only_frontend_assets_are_served(self):
        for path in ("/", "/app.js?v=1", "/styles.css", "/manifest.webmanifest"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 200)
        for path in ("/server.py", "/control.py", "/.git/config", "/.env", "/reference/",
                     "/docs/DEV-PLAN.md", "/%2e%2e/server.py", "/tools/"):
            for method in ("GET", "HEAD"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(path, method)[0], 404)

    def test_head_returns_headers_without_body(self):
        status, headers, body = self.request("/", "HEAD")
        self.assertEqual(status, 200)
        self.assertGreater(int(headers["Content-Length"]), 0)
        self.assertEqual(headers["Cache-Control"], "no-cache")
        self.assertEqual(body, b"")

    def test_json_routes_remain_available_without_wildcard_cors(self):
        with patch.object(server, "get_usage", return_value={"totals": {}}):
            status, headers, body = self.request("/api/usage")
            self.assertEqual(status, 200)
            self.assertEqual(body, b'{"totals": {}}')
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(self.request("/api/usage", "HEAD")[2], b"")

    def send_headers(self, **extra):
        return {"Content-Type":"application/json", "X-Agent-Phone-CSRF":server.CSRF_TOKEN, **extra}

    def test_send_requires_csrf_and_same_origin(self):
        with patch.object(server, "get_control_service") as service:
            status, _, _ = self.request('/api/send', 'POST', '{}', {'Content-Type':'application/json'})
            self.assertEqual(status, 403)
            status, _, _ = self.request('/api/send', 'POST', '{}', self.send_headers(Origin='https://evil.example'))
            self.assertEqual(status, 403)
            status, _, _ = self.request('/api/send', 'POST', '{}', self.send_headers(Host='evil.example:5173'))
            self.assertEqual(status, 403)
            service.assert_not_called()

    def test_send_rejects_forms_bad_json_and_oversized_body(self):
        with patch.object(server, "get_control_service") as service:
            for body, headers, expected in (
                ('{}',self.send_headers(**{'Content-Type':'text/plain'}),415),
                ('not-json',self.send_headers(),400),
                ('x'*65537,self.send_headers(),413),
            ):
                self.assertEqual(self.request('/api/send','POST',body,headers)[0],expected)
            service.assert_not_called()

    def test_send_and_job_status_routes(self):
        with patch.object(server, 'get_control_service') as service:
            service.return_value.submit.return_value = {'id':'fixture','status':'queued'}
            status, _, body = self.request('/api/send','POST','{}',self.send_headers())
            self.assertEqual(status,202)
            self.assertEqual(json.loads(body)['job']['status'],'queued')
            service.return_value.get.return_value = {'id':'fixture','status':'completed'}
            self.assertEqual(json.loads(self.request('/api/jobs?id=fixture')[2])['job']['status'],'completed')

    def test_control_token_is_not_exposed_to_rebinding_host(self):
        with patch.object(server, 'get_control_service') as service:
            status, _, body = self.request('/api/control',headers={'Host':'evil.example:5173'})
            self.assertEqual(status,403)
            self.assertNotIn(server.CSRF_TOKEN.encode(),body)
            service.assert_not_called()

    def test_history_is_not_exposed_to_rebinding_host(self):
        with patch.object(server, 'get_messages') as messages:
            status, _, _ = self.request('/api/messages?session=fixture',headers={'Host':'evil.example:5173'})
            self.assertEqual(status,403)
            messages.assert_not_called()


if __name__ == "__main__":
    unittest.main()
