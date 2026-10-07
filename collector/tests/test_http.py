import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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
