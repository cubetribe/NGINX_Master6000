"""Threaded local server for the secure read-only web UI."""

from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from nginx_vps.config import TargetSettings, WebSettings
from nginx_vps.web.app import WebApplication


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Small threaded WSGI server suitable for the single-node admin UI."""

    daemon_threads = True


class QuietRequestHandler(WSGIRequestHandler):
    """Keep logs concise for local development and systemd runs."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def serve_web_ui(*, web_settings: WebSettings, target_settings: TargetSettings) -> None:
    """Serve the WSGI app until interrupted."""
    app = WebApplication(web_settings=web_settings, target_settings=target_settings)
    with make_server(
        web_settings.host,
        web_settings.port,
        app,
        server_class=ThreadingWSGIServer,
        handler_class=QuietRequestHandler,
    ) as httpd:
        httpd.serve_forever()
