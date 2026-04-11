"""CLI smoke tests for the initial scaffold."""

from importlib.metadata import distribution
from pathlib import Path
import subprocess
import sysconfig

from typer.testing import CliRunner

from nginx_vps.cli import app

runner = CliRunner()


def test_status_prints_read_only_placeholder() -> None:
    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "read-only status inspection is not implemented yet" in result.stdout.lower()
    assert "without changing server state" in result.stdout.lower()


def test_console_script_entry_point_contract() -> None:
    console_scripts = {
        entry_point.name: entry_point.value
        for entry_point in distribution("nginx_vps").entry_points
        if entry_point.group == "console_scripts"
    }
    script_name = "nginx-vps.exe" if sysconfig.get_platform().startswith("win") else "nginx-vps"
    script_path = Path(sysconfig.get_path("scripts")) / script_name
    result = subprocess.run(
        [str(script_path), "status"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert console_scripts["nginx-vps"] == "nginx_vps.cli:main"
    assert script_path.exists()
    assert result.returncode == 0
    assert "read-only status inspection is not implemented yet" in result.stdout.lower()
