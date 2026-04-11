"""Pure conflict detection helpers."""

from nginx_vps.core.models import Conflict, InventorySnapshot


def detect_conflicts(snapshot: InventorySnapshot) -> list[Conflict]:
    """Detect obvious port and listen overlaps from a normalized snapshot."""
    conflicts: list[Conflict] = []

    process_ports: dict[int, set[str]] = {}
    for binding in snapshot.port_bindings:
        process_ports.setdefault(binding.port, set()).add(binding.process_name)

    for port, process_names in sorted(process_ports.items()):
        if len(process_names) > 1:
            processes = ", ".join(sorted(process_names))
            conflicts.append(
                Conflict(
                    kind="port-collision",
                    summary=f"Multiple processes appear to claim port {port}.",
                    details=f"Observed processes: {processes}.",
                    port=port,
                )
            )

    listen_ports: dict[int, list[str]] = {}
    for site in snapshot.nginx_sites:
        for port in site.listen_ports:
            listen_ports.setdefault(port, []).append(site.name)

    for port, site_names in sorted(listen_ports.items()):
        if len(site_names) > 1:
            sites = ", ".join(sorted(site_names))
            conflicts.append(
                Conflict(
                    kind="nginx-listen-overlap",
                    summary=f"Multiple Nginx site definitions listen on port {port}.",
                    details=f"Observed site definitions: {sites}.",
                    port=port,
                )
            )

    return conflicts
