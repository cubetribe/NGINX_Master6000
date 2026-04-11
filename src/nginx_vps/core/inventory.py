"""Inventory composition utilities."""

from collections.abc import Iterable

from nginx_vps.core.models import InventorySnapshot, NginxInventory, PortBinding


def build_inventory(
    *,
    target_label: str,
    mode: str,
    config_path: str | None = None,
    port_bindings: Iterable[PortBinding] = (),
    nginx: NginxInventory | None = None,
    warnings: Iterable[str] = (),
    errors: Iterable[str] = (),
    notes: Iterable[str] = (),
) -> InventorySnapshot:
    """Compose a normalized read-only inventory snapshot from adapter inputs."""
    return InventorySnapshot(
        target_label=target_label,
        mode=mode,
        config_path=config_path,
        port_bindings=list(port_bindings),
        nginx=nginx,
        warnings=list(warnings),
        errors=list(errors),
        notes=list(notes),
    )
