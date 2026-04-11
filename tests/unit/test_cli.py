"""CLI and packaging contract tests."""

from importlib.metadata import distribution
from pathlib import Path
import subprocess
import sysconfig

from typer.testing import CliRunner

from nginx_vps.cli import app
from nginx_vps.config import TargetSettings
from nginx_vps.core.models import InventorySnapshot
from nginx_vps.status import collect_status_snapshot

runner = CliRunner()


def test_status_renders_snapshot(monkeypatch) -> None:
    def fake_load_target_settings(**_: object) -> object:
        return object()

    def fake_collect_status_snapshot(_: object) -> InventorySnapshot:
        return InventorySnapshot(
            target_label="deploy@example-vps:22",
            mode="ssh",
            notes=["Read-only inspection only."],
        )

    monkeypatch.setattr("nginx_vps.cli.load_target_settings", fake_load_target_settings)
    monkeypatch.setattr("nginx_vps.cli.collect_status_snapshot", fake_collect_status_snapshot)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Target: deploy@example-vps:22" in result.stdout
    assert "Safety: read-only inspection only" in result.stdout
    assert "No listening TCP ports could be collected" in result.stdout
    assert "Nginx data could not be collected" in result.stdout


def test_console_script_entry_point_contract() -> None:
    console_scripts = {
        entry_point.name: entry_point.value
        for entry_point in distribution("nginx_vps").entry_points
        if entry_point.group == "console_scripts"
    }
    script_name = "nginx-vps.exe" if sysconfig.get_platform().startswith("win") else "nginx-vps"
    script_path = Path(sysconfig.get_path("scripts")) / script_name
    top_level_help = subprocess.run(
        [str(script_path), "--help"],
        capture_output=True,
        check=False,
        text=True,
    )
    status_help = subprocess.run(
        [str(script_path), "status", "--help"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert console_scripts["nginx-vps"] == "nginx_vps.cli:main"
    assert script_path.exists()
    assert top_level_help.returncode == 0
    assert "Usage: nginx-vps [OPTIONS] COMMAND [ARGS]..." in top_level_help.stdout
    assert "status" in top_level_help.stdout
    assert "web" in top_level_help.stdout
    assert "web-login" in top_level_help.stdout
    assert status_help.returncode == 0
    assert "Show a read-only status summary" in status_help.stdout
    assert "[target]" in status_help.stdout
    assert "--ssh-key-path" in status_help.stdout


def test_web_login_command_renders_success(monkeypatch) -> None:
    def fake_complete_web_login(**_: object) -> dict[str, object]:
        return {
            "challenge_id": "challenge-123",
            "username": "operator",
        }

    monkeypatch.setattr("nginx_vps.cli.complete_web_login", fake_complete_web_login)

    result = runner.invoke(
        app,
        [
            "web-login",
            "--base-url",
            "https://nginx.example.com",
            "--username",
            "operator",
            "--challenge-id",
            "challenge-123",
            "--key-path",
            "/tmp/id_operator",
        ],
    )

    assert result.exit_code == 0
    assert "Approved browser login challenge challenge-123 for operator." in result.stdout


def test_web_serve_help_mentions_ssh_challenge_login() -> None:
    result = runner.invoke(app, ["web", "serve", "--help"])

    assert result.exit_code == 0
    assert "Run the secure read-only browser UI" in result.stdout
    assert "--session-secret-env" in result.stdout
    assert "--ssh-key-path" in result.stdout


def test_status_error_only_report_does_not_claim_no_findings(monkeypatch) -> None:
    def fake_load_target_settings(**_: object) -> object:
        return object()

    def fake_collect_status_snapshot(_: object) -> InventorySnapshot:
        return InventorySnapshot(
            target_label="local",
            mode="local",
            errors=[
                "Local inspection currently supports Linux targets only. "
                "Use --mode ssh from macOS or Windows."
            ],
        )

    monkeypatch.setattr("nginx_vps.cli.load_target_settings", fake_load_target_settings)
    monkeypatch.setattr("nginx_vps.cli.collect_status_snapshot", fake_collect_status_snapshot)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert "No obvious findings detected from the current snapshot." not in result.stdout
    assert "No findings rendered because inspection did not complete successfully" in result.stdout
    assert "Local inspection currently supports Linux targets only." in result.stdout


def test_collect_status_snapshot_deduplicates_identical_collection_errors(monkeypatch) -> None:
    error_message = (
        "Local inspection currently supports Linux targets only. "
        "Use --mode ssh from macOS or Windows."
    )

    def fail_port_collection(_: object) -> list[object]:
        raise RuntimeError(error_message)

    def fail_nginx_collection(_: object, __: Path) -> None:
        raise RuntimeError(error_message)

    monkeypatch.setattr("nginx_vps.status.collect_port_bindings", fail_port_collection)
    monkeypatch.setattr("nginx_vps.status.load_nginx_inventory", fail_nginx_collection)

    snapshot = collect_status_snapshot(TargetSettings(mode="local"))

    assert snapshot.errors == [error_message]
