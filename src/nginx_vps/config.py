"""Configuration loading for inspection and web UI runtime settings."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib
from urllib.parse import urlparse


DEFAULT_NGINX_CONF_PATH = "/etc/nginx/nginx.conf"
DEFAULT_CONFIG_CANDIDATES = (
    Path("config/app.local.toml"),
    Path("config/app.toml"),
)
DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 8420
DEFAULT_WEB_SESSION_SECRET_ENV = "NGINX_VPS_WEB_SESSION_SECRET"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


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


@dataclass(slots=True)
class WebUser:
    """Allowed SSH signing identity for a browser login."""

    username: str
    public_keys: tuple[str, ...]


@dataclass(slots=True)
class WebSettings:
    """Resolved runtime settings for the secure read-only web UI."""

    host: str = DEFAULT_WEB_HOST
    port: int = DEFAULT_WEB_PORT
    base_url: str = f"http://{DEFAULT_WEB_HOST}:{DEFAULT_WEB_PORT}"
    session_secret: str = ""
    session_secret_env: str = DEFAULT_WEB_SESSION_SECRET_ENV
    trusted_proxy_ips: tuple[str, ...] = ("127.0.0.1", "::1")
    challenge_ttl_seconds: int = 120
    challenge_rate_limit: int = 5
    challenge_rate_window_seconds: int = 600
    verify_rate_limit: int = 8
    verify_rate_window_seconds: int = 600
    lockout_threshold: int = 5
    lockout_seconds: int = 900
    session_ttl_seconds: int = 28800
    users: tuple[WebUser, ...] = ()
    config_path: Path | None = None

    def public_keys_for(self, username: str) -> tuple[str, ...]:
        """Return the configured public keys for a login user."""
        for user in self.users:
            if user.username == username:
                return user.public_keys
        return ()

    @property
    def secure_cookies_by_default(self) -> bool:
        """Whether the configured base URL requires secure cookies."""
        return urlparse(self.base_url).scheme == "https"


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


def load_web_settings(
    *,
    config_path: Path | None = None,
    host: str | None = None,
    port: int | None = None,
    base_url: str | None = None,
    session_secret_env: str | None = None,
) -> WebSettings:
    """Load secure web UI settings from TOML and environment."""
    cli_host = _string_value(host)
    cli_port = _int_value(port)
    cli_base_url = _string_value(base_url)
    cli_session_secret_env = _string_value(session_secret_env)
    resolved_config_path = _resolve_config_path(config_path)
    web_data = _load_required_table(resolved_config_path, "web")

    resolved_host = cli_host or _string_value(web_data.get("host")) or DEFAULT_WEB_HOST
    resolved_port = cli_port or _int_value(web_data.get("port")) or DEFAULT_WEB_PORT
    resolved_base_url = (
        cli_base_url
        or _string_value(web_data.get("base_url"))
        or _default_web_base_url(resolved_host, resolved_port)
    )
    resolved_secret_env = (
        cli_session_secret_env
        or _string_value(web_data.get("session_secret_env"))
        or DEFAULT_WEB_SESSION_SECRET_ENV
    )
    resolved_secret = os.getenv(resolved_secret_env) or _string_value(web_data.get("session_secret"))

    resolved = WebSettings(
        host=resolved_host,
        port=resolved_port,
        base_url=resolved_base_url,
        session_secret=resolved_secret or "",
        session_secret_env=resolved_secret_env,
        trusted_proxy_ips=tuple(
            _string_list(web_data.get("trusted_proxy_ips")) or ["127.0.0.1", "::1"]
        ),
        challenge_ttl_seconds=_int_value(web_data.get("challenge_ttl_seconds")) or 120,
        challenge_rate_limit=_int_value(web_data.get("challenge_rate_limit")) or 5,
        challenge_rate_window_seconds=_int_value(web_data.get("challenge_rate_window_seconds")) or 600,
        verify_rate_limit=_int_value(web_data.get("verify_rate_limit")) or 8,
        verify_rate_window_seconds=_int_value(web_data.get("verify_rate_window_seconds")) or 600,
        lockout_threshold=_int_value(web_data.get("lockout_threshold")) or 5,
        lockout_seconds=_int_value(web_data.get("lockout_seconds")) or 900,
        session_ttl_seconds=_int_value(web_data.get("session_ttl_seconds")) or 28800,
        users=_parse_web_users(web_data.get("users")),
        config_path=resolved_config_path,
    )
    _validate_web_settings(resolved)
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


def _validate_web_settings(settings: WebSettings) -> None:
    if settings.port < 1 or settings.port > 65535:
        raise ValueError("Web UI port must be between 1 and 65535.")

    parsed = urlparse(settings.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Web UI base_url must be a valid http or https URL.")
    if parsed.scheme != "https" and not _is_local_web_host(parsed.hostname):
        raise ValueError(
            "Web UI base_url must use https unless it targets localhost or a loopback address."
        )

    if len(settings.session_secret) < 32:
        raise ValueError(
            "Web UI session secret must be set via environment or config and contain at least 32 characters."
        )
    if not settings.users:
        raise ValueError("Web UI requires at least one configured [[web.users]] entry.")

    for user in settings.users:
        if not USERNAME_PATTERN.fullmatch(user.username):
            raise ValueError(
                "Web UI usernames may contain only letters, numbers, dot, underscore, dash, and @."
            )
        if not user.public_keys:
            raise ValueError(f"Web UI user {user.username!r} must define at least one public key.")

    for value_name, value in (
        ("challenge_ttl_seconds", settings.challenge_ttl_seconds),
        ("challenge_rate_limit", settings.challenge_rate_limit),
        ("challenge_rate_window_seconds", settings.challenge_rate_window_seconds),
        ("verify_rate_limit", settings.verify_rate_limit),
        ("verify_rate_window_seconds", settings.verify_rate_window_seconds),
        ("lockout_threshold", settings.lockout_threshold),
        ("lockout_seconds", settings.lockout_seconds),
        ("session_ttl_seconds", settings.session_ttl_seconds),
    ):
        if value < 1:
            raise ValueError(f"Web UI {value_name} must be a positive integer.")


def _string_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _int_value(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


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


def _load_required_table(config_path: Path | None, table_name: str) -> dict[str, object]:
    if config_path is None:
        raise ValueError(
            f"Config file with a [{table_name}] table is required. "
            "Pass --config or create config/app.local.toml."
        )
    if not config_path.exists():
        raise ValueError(f"Config file not found: {config_path}")
    with config_path.open("rb") as config_file:
        data = tomllib.load(config_file)
    table = data.get(table_name)
    if not isinstance(table, dict):
        raise ValueError(f"Config file must define a [{table_name}] table.")
    return table


def _parse_web_users(value: object) -> tuple[WebUser, ...]:
    users: list[WebUser] = []
    if not isinstance(value, list):
        return ()

    for raw_user in value:
        if not isinstance(raw_user, dict):
            continue
        username = _string_value(raw_user.get("username"))
        if username is None:
            continue
        public_keys = _string_list(raw_user.get("public_keys"))
        single_key = _string_value(raw_user.get("public_key"))
        if single_key is not None:
            public_keys.append(single_key)
        deduplicated_keys = tuple(dict.fromkeys(public_keys))
        users.append(WebUser(username=username, public_keys=deduplicated_keys))
    return tuple(users)


def _default_web_base_url(host: str, port: int) -> str:
    host_value = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{host_value}:{port}"


def _is_local_web_host(hostname: str | None) -> bool:
    return hostname in {None, "127.0.0.1", "::1", "localhost"}
