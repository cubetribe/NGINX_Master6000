"""Status collection orchestration for local and SSH targets."""

from pathlib import Path

from nginx_vps.adapters.nginx_fs import load_nginx_inventory
from nginx_vps.adapters.process_ports import collect_port_bindings
from nginx_vps.adapters.ssh import LocalCommandRunner, SSHCommandRunner, SSHConnectionConfig
from nginx_vps.config import TargetSettings
from nginx_vps.core.inventory import build_inventory
from nginx_vps.core.models import InventorySnapshot


def collect_status_snapshot(settings: TargetSettings) -> InventorySnapshot:
    """Collect a read-only inventory snapshot for the resolved target."""
    runner = _build_runner(settings)

    warnings: list[str] = []
    errors: list[str] = []
    notes = [
        "Read-only inspection only. No files, services, or remote state were modified.",
    ]
    if settings.mode == "ssh":
        if settings.ssh_key_path is not None:
            notes.append(
                f"SSH uses the local key {settings.ssh_key_path.name}. "
                "The CLI never stores passwords and does not upload private keys."
            )
        else:
            notes.append(
                "SSH uses your local OpenSSH configuration and local keys. "
                "This tool does not read, store, or upload private keys."
            )
        notes.append("Password-based SSH is intentionally unsupported by the CLI.")

    try:
        port_bindings = collect_port_bindings(runner)
    except (RuntimeError, TimeoutError) as exc:
        port_bindings = []
        _append_unique_error(errors, exc)

    try:
        nginx_inventory = load_nginx_inventory(runner, Path(settings.nginx_conf_path))
    except (RuntimeError, TimeoutError) as exc:
        nginx_inventory = None
        _append_unique_error(errors, exc)
    else:
        warnings.extend(nginx_inventory.warnings)
        errors.extend(nginx_inventory.errors)

    return build_inventory(
        target_label=settings.target_label,
        mode=settings.mode,
        config_path=str(settings.config_path) if settings.config_path is not None else None,
        port_bindings=port_bindings,
        nginx=nginx_inventory,
        warnings=warnings,
        errors=errors,
        notes=notes,
    )


def _build_runner(settings: TargetSettings) -> LocalCommandRunner | SSHCommandRunner:
    if settings.mode == "ssh":
        return SSHCommandRunner(
            SSHConnectionConfig(
                host=settings.ssh_host or "",
                user=settings.ssh_user,
                port=settings.ssh_port,
                key_path=str(settings.ssh_key_path.expanduser()) if settings.ssh_key_path is not None else None,
            )
        )
    return LocalCommandRunner()


def _append_unique_error(errors: list[str], exc: RuntimeError | TimeoutError) -> None:
    """Keep repeated collection failures from rendering as duplicate report errors."""
    message = str(exc)
    if message not in errors:
        errors.append(message)
