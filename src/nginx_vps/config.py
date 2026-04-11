"""Configuration loading for local and SSH inspection targets."""

from dataclasses import dataclass
from pathlib import Path
import tomllib


DEFAULT_NGINX_CONF_PATH = "/etc/nginx/nginx.conf"
DEFAULT_CONFIG_CANDIDATES = (
    Path("config/app.local.toml"),
    Path("config/app.toml"),
)


@dataclass(slots=True)
class TargetSettings:
    """Resolved runtime settings for the inspection target."""

    mode: str = "local"
    ssh_host: str | None = None
    ssh_port: int | None = None
    ssh_user: str | None = None
    ssh_key_path: Path | None = None
    nginx_conf_path: str = DEFAULT_NGINX_CONF_PATH
    config_path: Path | None = None

    @property
    def target_label(self) -> str:
        """Return a human-readable target label."""
        if self.mode == "ssh":
            if self.ssh_user:
                prefix = f"{self.ssh_user}@{self.ssh_host}"
            else:
                prefix = self.ssh_host or "ssh-target"
            if self.ssh_port is not None:
                return f"{prefix}:{self.ssh_port}"
            return prefix
        return "local"


def load_target_settings(
    *,
    config_path: Path | None = None,
    mode: str | None = None,
    ssh_host: str | None = None,
    ssh_port: int | None = None,
    ssh_user: str | None = None,
    ssh_key_path: str | None = None,
    nginx_conf_path: str | None = None,
) -> TargetSettings:
    """Load target settings from TOML and apply explicit CLI overrides."""
    cli_mode = _string_value(mode)
    cli_ssh_host = _string_value(ssh_host)
    cli_ssh_port = _int_value(ssh_port)
    cli_ssh_user = _string_value(ssh_user)
    cli_ssh_key_path = _path_value(ssh_key_path)
    cli_nginx_conf_path = _string_value(nginx_conf_path)
    file_settings: dict[str, object] = {}
    ssh_settings: dict[str, object] = {}
    resolved_config_path = _resolve_config_path(config_path)
    config_base_dir: Path | None = None
    if resolved_config_path is not None:
        if not resolved_config_path.exists():
            raise ValueError(f"Config file not found: {resolved_config_path}")
        with resolved_config_path.open("rb") as config_file:
            data = tomllib.load(config_file)
        target_data = data.get("target")
        if not isinstance(target_data, dict):
            raise ValueError("Config file must define a [target] table.")
        file_settings = target_data
        nested_ssh = target_data.get("ssh")
        if isinstance(nested_ssh, dict):
            ssh_settings = nested_ssh
        config_base_dir = resolved_config_path.parent
    resolved_mode = cli_mode or _string_value(file_settings.get("mode")) or "local"
    use_config_ssh = resolved_mode.lower() != "local"

    resolved = TargetSettings(
        mode=resolved_mode,
        ssh_host=cli_ssh_host
        or (_string_value(ssh_settings.get("host")) if use_config_ssh else None)
        or (_string_value(file_settings.get("ssh_host")) if use_config_ssh else None),
        ssh_port=cli_ssh_port
        or (_int_value(ssh_settings.get("port")) if use_config_ssh else None)
        or (_int_value(file_settings.get("ssh_port")) if use_config_ssh else None),
        ssh_user=cli_ssh_user
        or (_string_value(ssh_settings.get("user")) if use_config_ssh else None)
        or (_string_value(file_settings.get("ssh_user")) if use_config_ssh else None),
        ssh_key_path=cli_ssh_key_path
        or (_path_value(ssh_settings.get("key_path"), base_dir=config_base_dir) if use_config_ssh else None)
        or (
            _path_value(file_settings.get("ssh_key_path"), base_dir=config_base_dir)
            if use_config_ssh
            else None
        ),
        nginx_conf_path=(
            cli_nginx_conf_path
            or _string_value(file_settings.get("nginx_conf_path"))
            or DEFAULT_NGINX_CONF_PATH
        ),
        config_path=resolved_config_path,
    )
    _validate_settings(resolved)
    return resolved


def _validate_settings(settings: TargetSettings) -> None:
    mode = settings.mode.lower()
    if mode not in {"local", "ssh"}:
        raise ValueError("Target mode must be either 'local' or 'ssh'.")
    settings.mode = mode
    if settings.mode == "ssh" and not settings.ssh_host:
        raise ValueError("SSH mode requires ssh_host or --ssh-host.")
    if settings.mode == "local" and any(
        (
            settings.ssh_host is not None,
            settings.ssh_port is not None,
            settings.ssh_user is not None,
            settings.ssh_key_path is not None,
        )
    ):
        raise ValueError("Local mode cannot be combined with SSH settings.")
    if settings.ssh_port is not None and (settings.ssh_port < 1 or settings.ssh_port > 65535):
        raise ValueError("SSH port must be between 1 and 65535.")
    if settings.ssh_key_path is not None and not settings.ssh_key_path.expanduser().is_file():
        raise ValueError(f"SSH key path not found: {settings.ssh_key_path.expanduser()}")


def _string_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _int_value(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _path_value(value: object, *, base_dir: Path | None = None) -> Path | None:
    if isinstance(value, str) and value.strip():
        path = Path(value.strip()).expanduser()
        if not path.is_absolute() and base_dir is not None:
            return (base_dir / path).resolve()
        return path
    return None


def _resolve_config_path(config_path: Path | None) -> Path | None:
    if config_path is not None:
        return config_path.expanduser().resolve()
    for candidate in DEFAULT_CONFIG_CANDIDATES:
        candidate_path = candidate.expanduser()
        if candidate_path.is_file():
            return candidate_path.resolve()
    return None
