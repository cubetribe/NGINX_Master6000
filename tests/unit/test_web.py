"""Secure web UI contract tests."""

from contextlib import contextmanager
import http.cookiejar
import re
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path
from urllib import parse, request

import pytest

from nginx_vps.config import TargetSettings, WebSettings, WebUser, load_web_settings
from nginx_vps.core.models import InventorySnapshot
from nginx_vps.web.app import WebApplication
from nginx_vps.web.auth import AuthError, AuthService
from nginx_vps.web.server import QuietRequestHandler, ThreadingWSGIServer


def test_load_web_settings_from_toml_and_env(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "app.toml"
    config_path.write_text(
        "\n".join(
            [
                "[web]",
                'host = "127.0.0.1"',
                "port = 8420",
                'base_url = "https://nginx.example.com"',
                'session_secret_env = "TEST_WEB_SESSION_SECRET"',
                'trusted_proxy_ips = ["127.0.0.1", "::1"]',
                "",
                "[[web.users]]",
                'username = "operator"',
                'public_keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKey operator@test"]',
            ]
        )
    )
    monkeypatch.setenv("TEST_WEB_SESSION_SECRET", "s" * 48)

    settings = load_web_settings(config_path=config_path)

    assert settings.host == "127.0.0.1"
    assert settings.port == 8420
    assert settings.base_url == "https://nginx.example.com"
    assert settings.session_secret == "s" * 48
    assert settings.public_keys_for("operator") == (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKey operator@test",
    )


def test_auth_service_locks_out_after_repeated_failed_signatures(tmp_path: Path) -> None:
    if shutil.which("ssh-keygen") is None:
        pytest.skip("ssh-keygen is required for web auth tests")

    key_path = _generate_test_keypair(tmp_path / "id_operator")
    public_key = key_path.with_suffix(".pub").read_text(encoding="utf-8").strip()
    settings = WebSettings(
        host="127.0.0.1",
        port=8420,
        base_url="http://127.0.0.1:8420",
        session_secret="s" * 48,
        users=(
            WebUser(
                username="operator",
                public_keys=(public_key,),
            ),
        ),
    )
    service = AuthService(settings)
    challenge = service.create_challenge("operator", "203.0.113.10")

    for _ in range(settings.lockout_threshold):
        with pytest.raises(AuthError) as exc:
            service.approve_challenge(
                challenge_id=challenge.challenge_id,
                username="operator",
                client_ip="203.0.113.10",
                signature="not-a-valid-signature",
            )
        assert exc.value.status_code in {401, 429}

    with pytest.raises(AuthError) as locked:
        service.create_challenge("operator", "203.0.113.10")

    assert locked.value.status_code == 429


def test_web_ui_end_to_end_ssh_login_flow(tmp_path: Path) -> None:
    if shutil.which("ssh-keygen") is None:
        pytest.skip("ssh-keygen is required for web auth tests")

    key_path = _generate_test_keypair(tmp_path / "id_operator")
    public_key = key_path.with_suffix(".pub").read_text(encoding="utf-8").strip()
    port = _find_free_port()
    settings = WebSettings(
        host="127.0.0.1",
        port=port,
        base_url=f"http://127.0.0.1:{port}",
        session_secret="s" * 48,
        users=(
            WebUser(
                username="operator",
                public_keys=(public_key,),
            ),
        ),
    )
    app = WebApplication(
        web_settings=settings,
        target_settings=TargetSettings(mode="local"),
        snapshot_provider=lambda _: InventorySnapshot(
            target_label="local",
            mode="local",
            notes=["Read-only inspection only."],
        ),
    )

    with _run_test_server(app, settings.host, settings.port):
        opener = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        login_page = opener.open(f"{settings.base_url}/login", timeout=5).read().decode("utf-8")
        assert "Browser passwords are intentionally disabled." in login_page
        assert 'type="password"' not in login_page

        challenge_page = opener.open(
            request.Request(
                f"{settings.base_url}/login/challenge",
                data=parse.urlencode({"username": "operator"}).encode("utf-8"),
                method="POST",
            ),
            timeout=5,
        ).read().decode("utf-8")
        challenge_match = re.search(r'data-challenge-id="([^"]+)"', challenge_page)
        assert challenge_match is not None
        challenge_id = challenge_match.group(1)

        approval = subprocess.run(
            [
                sys.executable,
                "-m",
                "nginx_vps.cli",
                "web-login",
                "--base-url",
                settings.base_url,
                "--username",
                "operator",
                "--challenge-id",
                challenge_id,
                "--key-path",
                str(key_path),
            ],
            capture_output=True,
            check=False,
            text=True,
        )

        assert approval.returncode == 0, approval.stderr
        assert f"Approved browser login challenge {challenge_id} for operator." in approval.stdout

        dashboard = opener.open(f"{settings.base_url}/login", timeout=5).read().decode("utf-8")
        assert "Logged in as <strong>operator</strong>" in dashboard
        assert "Read-only Diagnostics" in dashboard
        assert "Raw Report" in dashboard
        assert 'type="password"' not in dashboard


def test_web_ui_health_accepts_head_requests() -> None:
    port = _find_free_port()
    settings = WebSettings(
        host="127.0.0.1",
        port=port,
        base_url=f"http://127.0.0.1:{port}",
        session_secret="s" * 48,
        users=(WebUser(username="operator", public_keys=("ssh-ed25519 AAAATEST operator@test",)),),
    )
    app = WebApplication(
        web_settings=settings,
        target_settings=TargetSettings(mode="local"),
        snapshot_provider=lambda _: InventorySnapshot(target_label="local", mode="local"),
    )

    with _run_test_server(app, settings.host, settings.port):
        req = request.Request(f"{settings.base_url}/health", method="HEAD")
        with request.urlopen(req, timeout=5) as response:
            assert response.status == 200


@contextmanager
def _run_test_server(app: WebApplication, host: str, port: int):
    from wsgiref.simple_server import make_server

    server = make_server(
        host,
        port,
        app,
        server_class=ThreadingWSGIServer,
        handler_class=QuietRequestHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _find_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _generate_test_keypair(key_path: Path) -> Path:
    subprocess.run(
        [
            "ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-f",
            str(key_path),
        ],
        check=True,
    )
    return key_path
