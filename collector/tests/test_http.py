import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from limit_rings.sources import http
from limit_rings.sources.http import get_json
from limit_rings.version import VERSION


def test_user_agent_names_the_widget_version():
    agents = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            agents.append(self.headers.get("User-Agent"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert get_json(f"http://127.0.0.1:{srv.server_port}/", {}) == {}
    finally:
        srv.shutdown()
    assert agents == [f"limit-rings/{VERSION}"]


class _Context:
    def __init__(self, loaded):
        self.loaded = loaded
        self.files = []

    def cert_store_stats(self):
        return {"x509_ca": self.loaded}

    def load_verify_locations(self, cafile=None):
        self.files.append(cafile)


def test_tls_context_falls_back_to_the_system_bundle_when_python_has_no_roots(tmp_path):
    bundle = tmp_path / "cert.pem"
    bundle.write_text("")
    ctx = _Context(loaded=0)
    assert http._tls_context(lambda: ctx, str(bundle)) is ctx
    assert ctx.files == [str(bundle)]


def test_tls_context_leaves_a_working_trust_store_alone(tmp_path):
    bundle = tmp_path / "cert.pem"
    bundle.write_text("")
    ctx = _Context(loaded=140)
    http._tls_context(lambda: ctx, str(bundle))
    assert ctx.files == []


def test_tls_context_without_any_bundle_keeps_the_default(tmp_path):
    ctx = _Context(loaded=0)
    http._tls_context(lambda: ctx, str(tmp_path / "missing.pem"))
    assert ctx.files == []
