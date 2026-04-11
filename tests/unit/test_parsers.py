"""Parser and config tests for the status MVP."""

from pathlib import Path
from types import SimpleNamespace

from nginx_vps.adapters.nginx_fs import parse_nginx_t_output
from nginx_vps.adapters.process_ports import parse_ss_output
from nginx_vps.adapters.ssh import SSHCommandRunner, SSHConnectionConfig
from nginx_vps.config import load_target_settings
from nginx_vps.core.conflicts import detect_conflicts
from nginx_vps.core.inventory import build_inventory
from nginx_vps.core.models import NginxInventory, NginxListenDirective, NginxSite, PortBinding

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_ss_output_aggregates_process_counts() -> None:
    output = (FIXTURES_DIR / "ss_listen.txt").read_text()

    bindings = parse_ss_output(output)
    binding_map = {
        (binding.address, binding.port, binding.process_name): binding for binding in bindings
    }

    assert len(bindings) == 4
    assert binding_map[("127.0.0.1", 2222, "sshd")].pid == 33
    assert binding_map[("::", 443, "nginx")].process_count == 2
    assert binding_map[("0.0.0.0", 443, "nginx")].process_count == 2
    assert binding_map[("0.0.0.0", 8080, "docker-proxy")].pid == 22


def test_parse_nginx_t_output_builds_site_summaries() -> None:
    output = (FIXTURES_DIR / "nginx_t.txt").read_text()

    inventory = parse_nginx_t_output(output, entrypoint="/etc/nginx/nginx.conf")

    assert inventory.config_test_passed is True
    assert len(inventory.config_files) == 3
    assert len(inventory.sites) == 3
    assert any("protocol options redefined" in warning for warning in inventory.warnings)
    assert inventory.sites[0].source_path == "/etc/nginx/sites-enabled/example.conf"
    assert inventory.sites[0].listen_ports == [80]
    assert inventory.sites[1].listen_ports == [443]
    assert "www.example.com" in inventory.sites[1].server_names


def test_load_target_settings_from_toml_and_overrides(tmp_path: Path) -> None:
    key_path = tmp_path / "id_test"
    key_path.write_text("not-a-real-key\n")
    flat_key_path = tmp_path / "id_flat"
    flat_key_path.write_text("not-a-real-key\n")
    config_path = tmp_path / "app.toml"
    config_path.write_text(
        "\n".join(
            [
                "[target]",
                'mode = "ssh"',
                'ssh_host = "flat-host"',
                "ssh_port = 2022",
                'ssh_user = "flat-user"',
                f'ssh_key_path = "{flat_key_path}"',
                'nginx_conf_path = "/custom/nginx.conf"',
                "",
                "[target.ssh]",
                'host = "vps-alias"',
                "port = 2222",
                'user = "deploy"',
                f'key_path = "{key_path}"',
            ]
        )
    )

    settings = load_target_settings(config_path=config_path, ssh_user="root")

    assert settings.mode == "ssh"
    assert settings.ssh_host == "vps-alias"
    assert settings.ssh_port == 2222
    assert settings.ssh_user == "root"
    assert settings.ssh_key_path == key_path
    assert settings.nginx_conf_path == "/custom/nginx.conf"


def test_load_target_settings_auto_discovers_local_config(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    key_path = config_dir / "id_auto"
    key_path.write_text("not-a-real-key\n")
    config_path = config_dir / "app.local.toml"
    config_path.write_text(
        "\n".join(
            [
                "[target]",
                'mode = "ssh"',
                'ssh_host = "local-config-host"',
                "ssh_port = 2200",
                'ssh_user = "deploy"',
                'ssh_key_path = "id_auto"',
            ]
        )
    )
    monkeypatch.chdir(tmp_path)

    settings = load_target_settings()

    assert settings.mode == "ssh"
    assert settings.ssh_host == "local-config-host"
    assert settings.ssh_port == 2200
    assert settings.ssh_user == "deploy"
    assert settings.ssh_key_path == key_path
    assert settings.config_path == config_path


def test_load_target_settings_local_mode_override_ignores_config_ssh_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "app.toml"
    config_path.write_text(
        "\n".join(
            [
                "[target]",
                'mode = "ssh"',
                'ssh_host = "flat-host"',
                "ssh_port = 2022",
                'ssh_user = "flat-user"',
                'ssh_key_path = "missing-flat-key"',
                'nginx_conf_path = "/custom/nginx.conf"',
                "",
                "[target.ssh]",
                'host = "nested-host"',
                "port = 2222",
                'user = "deploy"',
                'key_path = "missing-nested-key"',
            ]
        )
    )

    settings = load_target_settings(config_path=config_path, mode="local")

    assert settings.mode == "local"
    assert settings.ssh_host is None
    assert settings.ssh_port is None
    assert settings.ssh_user is None
    assert settings.ssh_key_path is None
    assert settings.nginx_conf_path == "/custom/nginx.conf"
    assert settings.config_path == config_path


def test_ssh_command_runner_prefers_public_key_auth(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

    monkeypatch.setattr("nginx_vps.adapters.ssh.subprocess.run", fake_run)

    runner = SSHCommandRunner(
        SSHConnectionConfig(
            host="vps-alias",
            user="deploy",
            port=2222,
            key_path="/tmp/id_test",
        )
    )

    result = runner.run_read_only("true")

    assert result.exit_code == 0
    assert result.stdout == "ok\n"
    command = captured["command"]
    assert isinstance(command, list)
    assert command[0] == "ssh"
    assert "BatchMode=yes" in command
    assert "PreferredAuthentications=publickey" in command
    assert "PasswordAuthentication=no" in command
    assert "PubkeyAuthentication=yes" in command
    assert "KbdInteractiveAuthentication=no" in command
    assert "IdentitiesOnly=yes" in command
    assert "deploy@vps-alias" in command
    assert "true" == command[-1]


def test_detect_conflicts_surfaces_nginx_warning_and_missing_port() -> None:
    snapshot = build_inventory(
        target_label="deploy@example-vps:22",
        mode="ssh",
        port_bindings=[
            PortBinding(
                protocol="tcp",
                address="0.0.0.0",
                port=8080,
                process_name="docker-proxy",
                pid=42,
            )
        ],
        nginx=NginxInventory(
            entrypoint="/etc/nginx/nginx.conf",
            warnings=["protocol options redefined for 0.0.0.0:443"],
            sites=[
                NginxSite(
                    name="example.com",
                    source_path="/etc/nginx/sites-enabled/example.conf",
                    listen_ports=[443],
                    server_names=["example.com"],
                    listen_directives=[
                        NginxListenDirective(
                            address="0.0.0.0",
                            port=443,
                            raw="443 ssl http2",
                            ssl=True,
                            http2=True,
                        )
                    ],
                )
            ],
        ),
    )

    conflicts = detect_conflicts(snapshot)

    assert any(conflict.kind == "nginx-warning" for conflict in conflicts)
    assert any(conflict.kind == "nginx-port-not-active" for conflict in conflicts)


def test_detect_conflicts_ignores_systemd_socket_activation_pair() -> None:
    snapshot = build_inventory(
        target_label="local",
        mode="local",
        port_bindings=[
            PortBinding(
                protocol="tcp",
                address="0.0.0.0",
                port=2222,
                process_name="systemd",
                pid=1,
            ),
            PortBinding(
                protocol="tcp",
                address="0.0.0.0",
                port=2222,
                process_name="sshd",
                pid=33,
            ),
        ],
    )

    conflicts = detect_conflicts(snapshot)

    assert conflicts == []
