"""Inventory composition utilities."""

from collections.abc import Iterable

from nginx_vps.core.models import InventorySnapshot, NginxSite, PortBinding


def build_inventory(
    *,
    port_bindings: Iterable[PortBinding] = (),
    nginx_sites: Iterable[NginxSite] = (),
) -> InventorySnapshot:
    """Compose a normalized read-only inventory snapshot from adapter inputs."""
    return InventorySnapshot(
        port_bindings=list(port_bindings),
        nginx_sites=list(nginx_sites),
    )
