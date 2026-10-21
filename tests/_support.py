"""Shared helpers for the offline tests of the bundled scripts.

Run from the repo root with:  python3 -m unittest discover -s tests -v

- Scripts are loaded by file path, so the tests exercise exactly what an
  agent would run (no packaging needed).
- Outbound network access is disabled for the whole test process, so a
  missed mock fails loudly instead of calling filterlabs.ai.
- Each test gets a temporary directory; module-level paths (TOKEN_PATH,
  SESSION_DIR, CONFIG_PATH) are pointed into it, so nothing touches ~/.hermes.
"""
import base64
import importlib.util
import io
import json
import os
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _refuse(*a, **k):
    raise RuntimeError("network access is disabled in the offline tests")


socket.socket.connect = _refuse
socket.socket.connect_ex = _refuse
socket.create_connection = _refuse

AUTH_PY = "skills/ubiquity-auth/scripts/filterlabs_auth.py"
ER_PY = "skills/ubiquity-entity-review/scripts/entity_review.py"
LEAK_PY = "skills/ubiquity-skill-dev-workflow/scripts/scan_for_leaks.py"
REPOLOC_PY = "skills/ubiquity-skill-dev-workflow/scripts/repo_location.py"


def load_script(rel, name):
    spec = importlib.util.spec_from_file_location(name, str(REPO / rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_jwt(sub="11111111-2222-3333-4444-555555555555", email="tester@example.com"):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64({'sub': sub, 'email': email})}.sig"


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._raw = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeServer:
    """Stand-in for urllib.request.urlopen. `routes` is a list of
    (method, path_prefix, handler); handler(req, body) -> (status, json).
    Every call is recorded in self.calls."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, req, data=None, timeout=None, *a, **k):
        url, method, raw = req.full_url, req.get_method(), req.data
        body = None
        if raw:
            try:
                body = json.loads(raw)
            except Exception:
                body = raw.decode()
        path = url.split("://", 1)[1]
        path = path[path.index("/"):]
        headers = {k.lower(): v for k, v in req.header_items()}
        self.calls.append({"method": method, "url": url, "path": path,
                           "headers": headers, "body": body, "timeout": timeout})
        for m, prefix, handler in self.routes:
            if m == method and path.startswith(prefix):
                status, resp = handler(req, body)
                if status >= 400:
                    raise urllib.error.HTTPError(url, status, "err", {}, io.BytesIO(
                        json.dumps(resp).encode()))
                return FakeResponse(status, resp)
        raise AssertionError(f"unmocked request {method} {path}")


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.home = Path(self._td.name)
        self._old_umask = os.umask(0o022)

    def tearDown(self):
        os.umask(self._old_umask)
        self._td.cleanup()
