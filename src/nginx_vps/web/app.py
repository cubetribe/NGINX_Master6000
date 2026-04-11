"""Minimal secure WSGI app for the read-only web dashboard."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import html
from http import cookies
import json
import shlex
from urllib.parse import parse_qs

from nginx_vps.config import TargetSettings, WebSettings
from nginx_vps.core.conflicts import detect_conflicts
from nginx_vps.core.models import InventorySnapshot
from nginx_vps.reporting import render_status_report
from nginx_vps.status import collect_status_snapshot
from nginx_vps.web.auth import (
    AuthError,
    AuthService,
    PENDING_COOKIE_NAME,
    SESSION_COOKIE_NAME,
)


@dataclass(slots=True)
class RequestContext:
    """Normalized request data used by the WSGI routes."""

    method: str
    path: str
    query: dict[str, list[str]]
    client_ip: str
    scheme: str
    cookies: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Response:
    """Simple WSGI response container."""

    status: str
    body: bytes
    content_type: str = "text/html; charset=utf-8"
    headers: list[tuple[str, str]] = field(default_factory=list)


class WebApplication:
    """Read-only diagnostic UI with SSH-key-only login."""

    def __init__(
        self,
        *,
        web_settings: WebSettings,
        target_settings: TargetSettings,
        snapshot_provider: Callable[[TargetSettings], InventorySnapshot] | None = None,
        auth_service: AuthService | None = None,
    ) -> None:
        self.web_settings = web_settings
        self.target_settings = target_settings
        self.snapshot_provider = snapshot_provider or collect_status_snapshot
        self.auth = auth_service or AuthService(web_settings)

    def __call__(self, environ: dict[str, object], start_response: Callable[..., object]) -> list[bytes]:
        request = self._build_request(environ)
        response = self._dispatch(request, environ)
        body = b"" if request.method == "HEAD" else response.body
        headers = [
            ("Content-Type", response.content_type),
            ("Content-Length", str(len(response.body))),
            *self._security_headers(request),
            *response.headers,
        ]
        start_response(response.status, headers)
        return [body]

    def _dispatch(self, request: RequestContext, environ: dict[str, object]) -> Response:
        if request.path == "/health" and request.method in {"GET", "HEAD"}:
            return self._text_response("200 OK", "ok\n")
        if request.path == "/login" and request.method in {"GET", "HEAD"}:
            return self._handle_login_page(request)
        if request.path == "/login/challenge" and request.method == "POST":
            return self._handle_create_challenge(request, environ)
        if request.path == "/auth/challenge-info" and request.method in {"GET", "HEAD"}:
            return self._handle_challenge_info(request)
        if request.path == "/auth/complete" and request.method == "POST":
            return self._handle_complete_login(request, environ)
        if request.path == "/logout" and request.method == "POST":
            return self._handle_logout(request)
        if request.path in {"/", "/dashboard"} and request.method in {"GET", "HEAD"}:
            return self._handle_dashboard(request)
        return self._html_response("404 Not Found", _render_simple_page("Not found", "<p>Route not found.</p>"))

    def _handle_login_page(self, request: RequestContext) -> Response:
        session = self.auth.load_session(request.cookies.get(SESSION_COOKIE_NAME), request.client_ip)
        if session is not None:
            return self._redirect("/")

        pending_cookie = request.cookies.get(PENDING_COOKIE_NAME)
        issued_session = self.auth.issue_session_from_pending_cookie(pending_cookie, request.client_ip)
        if issued_session is not None:
            return self._redirect(
                "/",
                extra_headers=[
                    self._set_cookie_header(
                        SESSION_COOKIE_NAME,
                        self.auth.session_cookie_value(issued_session),
                    ),
                    self._clear_cookie_header(PENDING_COOKIE_NAME),
                ],
            )

        pending_challenge = self.auth.challenge_from_pending_cookie(pending_cookie, request.client_ip)
        if pending_challenge is not None:
            return self._html_response(
                "200 OK",
                _render_login_waiting_page(
                    base_url=self.web_settings.base_url,
                    challenge=pending_challenge,
                ),
            )

        clear_pending = [self._clear_cookie_header(PENDING_COOKIE_NAME)] if pending_cookie else []
        return self._html_response(
            "200 OK",
            _render_login_form(),
            extra_headers=clear_pending,
        )

    def _handle_create_challenge(self, request: RequestContext, environ: dict[str, object]) -> Response:
        form_data = parse_qs(_read_body(environ).decode("utf-8"), keep_blank_values=True)
        username = form_data.get("username", [""])[0]

        try:
            challenge = self.auth.create_challenge(username, request.client_ip)
        except AuthError as exc:
            return self._html_response(
                _http_status_line(exc.status_code),
                _render_login_form(error=str(exc)),
                extra_headers=self._retry_headers(exc),
            )

        return self._html_response(
            "200 OK",
            _render_login_waiting_page(
                base_url=self.web_settings.base_url,
                challenge=challenge,
            ),
            extra_headers=[
                self._set_cookie_header(
                    PENDING_COOKIE_NAME,
                    self.auth.pending_cookie_value(challenge),
                )
            ],
        )

    def _handle_challenge_info(self, request: RequestContext) -> Response:
        challenge_id = request.query.get("challenge_id", [""])[0]
        username = request.query.get("username", [""])[0]
        try:
            challenge = self.auth.get_cli_challenge(challenge_id, username, request.client_ip)
        except AuthError as exc:
            return self._json_response(
                _http_status_line(exc.status_code),
                {"error": str(exc)},
                extra_headers=self._retry_headers(exc),
            )

        return self._json_response(
            "200 OK",
            {
                "challenge_id": challenge.challenge_id,
                "username": challenge.username,
                "message": challenge.message,
                "expires_at": _format_timestamp(challenge.expires_at),
            },
        )

    def _handle_complete_login(self, request: RequestContext, environ: dict[str, object]) -> Response:
        body = _read_body(environ)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._json_response("400 Bad Request", {"error": "Request body must be valid JSON."})
        if not isinstance(payload, dict):
            return self._json_response("400 Bad Request", {"error": "Request body must be a JSON object."})

        challenge_id = payload.get("challenge_id")
        username = payload.get("username")
        signature = payload.get("signature")
        if not all(isinstance(value, str) and value for value in (challenge_id, username, signature)):
            return self._json_response(
                "400 Bad Request",
                {"error": "challenge_id, username, and signature are required."},
            )

        try:
            challenge = self.auth.approve_challenge(
                challenge_id=challenge_id,
                username=username,
                client_ip=request.client_ip,
                signature=signature,
            )
        except AuthError as exc:
            return self._json_response(
                _http_status_line(exc.status_code),
                {"error": str(exc)},
                extra_headers=self._retry_headers(exc),
            )

        return self._json_response(
            "200 OK",
            {
                "status": "approved",
                "challenge_id": challenge.challenge_id,
                "username": challenge.username,
            },
        )

    def _handle_dashboard(self, request: RequestContext) -> Response:
        session = self.auth.load_session(request.cookies.get(SESSION_COOKIE_NAME), request.client_ip)
        if session is None:
            return self._redirect("/login")

        snapshot = self.snapshot_provider(self.target_settings)
        conflicts = detect_conflicts(snapshot)
        return self._html_response(
            "200 OK",
            _render_dashboard(
                username=session.username,
                snapshot=snapshot,
                conflicts=conflicts,
                report_lines=render_status_report(snapshot, show_all=True),
            ),
            extra_headers=[
                self._set_cookie_header(
                    SESSION_COOKIE_NAME,
                    self.auth.session_cookie_value(session),
                )
            ],
        )

    def _handle_logout(self, request: RequestContext) -> Response:
        self.auth.clear_session(request.cookies.get(SESSION_COOKIE_NAME))
        return self._redirect(
            "/login",
            extra_headers=[
                self._clear_cookie_header(SESSION_COOKIE_NAME),
                self._clear_cookie_header(PENDING_COOKIE_NAME),
            ],
        )

    def _build_request(self, environ: dict[str, object]) -> RequestContext:
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        cookie_jar = cookies.SimpleCookie()
        cookie_jar.load(str(environ.get("HTTP_COOKIE", "")))
        return RequestContext(
            method=str(environ.get("REQUEST_METHOD", "GET")).upper(),
            path=str(environ.get("PATH_INFO", "/")) or "/",
            query=query,
            client_ip=self._client_ip(environ),
            scheme=self._scheme(environ),
            cookies={name: morsel.value for name, morsel in cookie_jar.items()},
        )

    def _client_ip(self, environ: dict[str, object]) -> str:
        remote_addr = str(environ.get("REMOTE_ADDR", "")) or "unknown"
        if remote_addr in self.web_settings.trusted_proxy_ips:
            forwarded_for = str(environ.get("HTTP_X_FORWARDED_FOR", "")).strip()
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()
            real_ip = str(environ.get("HTTP_X_REAL_IP", "")).strip()
            if real_ip:
                return real_ip
        return remote_addr

    def _scheme(self, environ: dict[str, object]) -> str:
        remote_addr = str(environ.get("REMOTE_ADDR", "")) or "unknown"
        if remote_addr in self.web_settings.trusted_proxy_ips:
            forwarded_proto = str(environ.get("HTTP_X_FORWARDED_PROTO", "")).strip()
            if forwarded_proto:
                return forwarded_proto.split(",")[0].strip()
        return str(environ.get("wsgi.url_scheme", "http"))

    def _security_headers(self, request: RequestContext) -> list[tuple[str, str]]:
        headers = [
            ("Cache-Control", "no-store"),
            ("Cross-Origin-Opener-Policy", "same-origin"),
            ("Cross-Origin-Resource-Policy", "same-origin"),
            (
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            ),
            ("Permissions-Policy", "camera=(), geolocation=(), microphone=()"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
        ]
        if request.scheme == "https" or self.web_settings.secure_cookies_by_default:
            headers.append(("Strict-Transport-Security", "max-age=31536000; includeSubDomains"))
        return headers

    def _html_response(
        self,
        status: str,
        body: str,
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> Response:
        return Response(
            status=status,
            body=body.encode("utf-8"),
            content_type="text/html; charset=utf-8",
            headers=extra_headers or [],
        )

    def _json_response(
        self,
        status: str,
        payload: dict[str, object],
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> Response:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        return Response(
            status=status,
            body=body,
            content_type="application/json; charset=utf-8",
            headers=extra_headers or [],
        )

    def _text_response(self, status: str, body: str) -> Response:
        return Response(
            status=status,
            body=body.encode("utf-8"),
            content_type="text/plain; charset=utf-8",
        )

    def _redirect(
        self,
        location: str,
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> Response:
        headers = [("Location", location)]
        if extra_headers:
            headers.extend(extra_headers)
        return Response(status="303 See Other", body=b"", headers=headers)

    def _set_cookie_header(self, name: str, value: str, *, max_age: int | None = None) -> tuple[str, str]:
        cookie = cookies.SimpleCookie()
        cookie[name] = value
        cookie[name]["path"] = "/"
        cookie[name]["httponly"] = True
        cookie[name]["samesite"] = "Strict"
        if self.web_settings.secure_cookies_by_default:
            cookie[name]["secure"] = True
        if max_age is not None:
            cookie[name]["max-age"] = str(max_age)
        return ("Set-Cookie", cookie.output(header="").strip())

    def _clear_cookie_header(self, name: str) -> tuple[str, str]:
        cookie = cookies.SimpleCookie()
        cookie[name] = ""
        cookie[name]["path"] = "/"
        cookie[name]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        cookie[name]["max-age"] = "0"
        cookie[name]["httponly"] = True
        cookie[name]["samesite"] = "Strict"
        if self.web_settings.secure_cookies_by_default:
            cookie[name]["secure"] = True
        return ("Set-Cookie", cookie.output(header="").strip())

    def _retry_headers(self, exc: AuthError) -> list[tuple[str, str]]:
        if exc.retry_after is None:
            return []
        return [("Retry-After", str(exc.retry_after))]


def _render_login_form(error: str | None = None) -> str:
    error_html = ""
    if error:
        error_html = f'<p class="alert">{html.escape(error)}</p>'

    body = f"""
    <section class="stack">
      <p class="eyebrow">Secure Browser Access</p>
      <h1>NGINX Master6000</h1>
      <p class="lead">Authenticate with your local SSH private key. Browser passwords are intentionally disabled.</p>
      {error_html}
      <form method="post" action="/login/challenge" class="panel">
        <label for="username">Username</label>
        <input id="username" name="username" type="text" autocomplete="username" inputmode="text" required />
        <button type="submit">Start SSH Challenge</button>
      </form>
      <div class="panel muted">
        <p><strong>How this works</strong></p>
        <p>1. Start a browser login challenge.</p>
        <p>2. Run the local CLI command shown on the next screen.</p>
        <p>3. Your browser session unlocks only after the server verifies an OpenSSH signature from your configured public key.</p>
      </div>
    </section>
    """
    return _render_shell("SSH key login", body)


def _render_login_waiting_page(*, base_url: str, challenge: object) -> str:
    challenge_id = html.escape(getattr(challenge, "challenge_id"))
    username = html.escape(getattr(challenge, "username"))
    command = " ".join(
        [
            "nginx-vps",
            "web-login",
            "--base-url",
            shlex.quote(base_url),
            "--username",
            shlex.quote(getattr(challenge, "username")),
            "--challenge-id",
            shlex.quote(getattr(challenge, "challenge_id")),
            "--key-path",
            shlex.quote("~/.ssh/id_vibecoding"),
        ]
    )
    body = f"""
    <meta http-equiv="refresh" content="3" />
    <section class="stack" data-challenge-id="{challenge_id}">
      <p class="eyebrow">Pending Approval</p>
      <h1>Complete the SSH challenge locally</h1>
      <p class="lead">Passwords stay disabled. This login challenge is valid only for the same client IP and expires at {html.escape(_format_timestamp(getattr(challenge, 'expires_at')))}.</p>
      <div class="panel">
        <p><strong>User</strong>: {username}</p>
        <p><strong>Challenge ID</strong>: <code>{challenge_id}</code></p>
        <p><strong>Command</strong></p>
        <pre>{html.escape(command)}</pre>
      </div>
      <div class="panel muted">
        <p>The page refreshes automatically every few seconds and issues a session cookie only after the signed challenge is verified.</p>
      </div>
    </section>
    """
    return _render_shell("Waiting for SSH approval", body)


def _render_dashboard(
    *,
    username: str,
    snapshot: InventorySnapshot,
    conflicts: list[object],
    report_lines: list[str],
) -> str:
    listeners_count = len(snapshot.port_bindings)
    sites_count = len(snapshot.nginx.sites) if snapshot.nginx is not None else 0
    config_files_count = len(snapshot.nginx.config_files) if snapshot.nginx is not None else 0
    config_test = "yes" if snapshot.nginx is not None and snapshot.nginx.config_test_passed else "no"
    errors_count = len(snapshot.errors)
    findings_markup = "".join(
        f"<li><strong>{html.escape(getattr(conflict, 'summary', 'Finding'))}</strong><br />"
        f"{html.escape(getattr(conflict, 'details', ''))}</li>"
        for conflict in conflicts
    )
    findings_block = (
        f"<ul class='list'>{findings_markup}</ul>" if findings_markup else "<p class='empty'>No findings detected.</p>"
    )

    body = f"""
    <section class="topbar">
      <div>
        <p class="eyebrow">Read-only Diagnostics</p>
        <h1>NGINX Master6000</h1>
        <p class="lead">Logged in as <strong>{html.escape(username)}</strong>. No destructive operations are available from this UI.</p>
      </div>
      <form method="post" action="/logout">
        <button type="submit" class="secondary">Log out</button>
      </form>
    </section>
    <section class="grid">
      <article class="panel stat"><span>Target</span><strong>{html.escape(snapshot.target_label)}</strong></article>
      <article class="panel stat"><span>Listeners</span><strong>{listeners_count}</strong></article>
      <article class="panel stat"><span>Sites</span><strong>{sites_count}</strong></article>
      <article class="panel stat"><span>Config files</span><strong>{config_files_count}</strong></article>
      <article class="panel stat"><span>Findings</span><strong>{len(conflicts)}</strong></article>
      <article class="panel stat"><span>Nginx config test</span><strong>{config_test}</strong></article>
      <article class="panel stat"><span>Errors</span><strong>{errors_count}</strong></article>
      <article class="panel stat"><span>Mode</span><strong>{html.escape(snapshot.mode)}</strong></article>
    </section>
    <section class="grid single">
      <article class="panel">
        <h2>Notes</h2>
        <ul class="list">
          {''.join(f'<li>{html.escape(note)}</li>' for note in snapshot.notes) or '<li>No extra notes.</li>'}
        </ul>
      </article>
      <article class="panel">
        <h2>Findings</h2>
        {findings_block}
      </article>
      <article class="panel">
        <h2>Raw Report</h2>
        <pre>{html.escape(chr(10).join(report_lines))}</pre>
      </article>
    </section>
    """
    return _render_shell("Dashboard", body)


def _render_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)} | NGINX Master6000</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f3efe4;
        --panel: #fff8ed;
        --ink: #17222d;
        --muted: #53606d;
        --border: #d8c9a8;
        --accent: #a6421d;
        --accent-soft: #f0d8c6;
        --alert: #8e1b0f;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
        background:
          radial-gradient(circle at top right, rgba(166, 66, 29, 0.16), transparent 30%),
          linear-gradient(180deg, #fcf7eb 0%, var(--bg) 100%);
        color: var(--ink);
      }}
      main {{ max-width: 960px; margin: 0 auto; padding: 40px 24px 80px; }}
      h1, h2 {{ margin: 0; line-height: 1.05; }}
      h1 {{ font-size: clamp(2rem, 4vw, 3.6rem); letter-spacing: -0.03em; }}
      h2 {{ font-size: 1.2rem; margin-bottom: 12px; }}
      p {{ margin: 0; line-height: 1.55; }}
      .stack {{ display: grid; gap: 18px; }}
      .topbar {{ display: flex; gap: 20px; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; }}
      .lead {{ color: var(--muted); max-width: 56rem; }}
      .eyebrow {{
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.78rem;
        color: var(--accent);
        margin-bottom: 8px;
        font-weight: 700;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 14px;
        margin-bottom: 18px;
      }}
      .grid.single {{ grid-template-columns: 1fr; }}
      .panel {{
        border: 1px solid var(--border);
        border-radius: 18px;
        padding: 18px;
        background: var(--panel);
        box-shadow: 0 18px 45px rgba(23, 34, 45, 0.08);
      }}
      .panel.muted {{ background: rgba(255, 248, 237, 0.7); }}
      .stat span {{
        display: block;
        color: var(--muted);
        font-size: 0.86rem;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}
      .stat strong {{ font-size: 1.5rem; }}
      .alert {{
        border: 1px solid rgba(142, 27, 15, 0.2);
        background: rgba(142, 27, 15, 0.08);
        color: var(--alert);
        padding: 12px 14px;
        border-radius: 12px;
      }}
      .list {{
        margin: 0;
        padding-left: 18px;
        display: grid;
        gap: 10px;
      }}
      .empty {{ color: var(--muted); }}
      code, pre, input {{
        font-family: "SFMono-Regular", "SF Mono", Menlo, Consolas, monospace;
      }}
      pre {{
        white-space: pre-wrap;
        word-break: break-word;
        background: #201815;
        color: #f5ede5;
        padding: 16px;
        border-radius: 14px;
        border: 1px solid rgba(255, 248, 237, 0.12);
        overflow-x: auto;
      }}
      form {{ display: grid; gap: 12px; }}
      label {{ font-weight: 600; }}
      input {{
        width: 100%;
        border: 1px solid var(--border);
        background: #fffdfa;
        padding: 12px 14px;
        border-radius: 12px;
        font-size: 1rem;
      }}
      button {{
        border: 0;
        border-radius: 999px;
        padding: 12px 18px;
        background: var(--accent);
        color: white;
        font-weight: 700;
        cursor: pointer;
      }}
      button.secondary {{
        background: #2f4a5f;
      }}
      @media (max-width: 700px) {{
        main {{ padding: 28px 18px 48px; }}
        .topbar {{ flex-direction: column; }}
      }}
    </style>
  </head>
  <body>
    <main>{body}</main>
  </body>
</html>"""


def _render_simple_page(title: str, body: str) -> str:
    return _render_shell(title, f'<section class="stack"><h1>{html.escape(title)}</h1>{body}</section>')


def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def _http_status_line(status_code: int) -> str:
    mapping = {
        400: "400 Bad Request",
        401: "401 Unauthorized",
        403: "403 Forbidden",
        404: "404 Not Found",
        410: "410 Gone",
        429: "429 Too Many Requests",
    }
    return mapping.get(status_code, "400 Bad Request")


def _read_body(environ: dict[str, object]) -> bytes:
    stream = environ.get("wsgi.input")
    content_length = environ.get("CONTENT_LENGTH", "0")
    if stream is None:
        return b""
    try:
        length = int(content_length) if content_length else 0
    except (TypeError, ValueError):
        length = 0
    return stream.read(max(length, 0))
