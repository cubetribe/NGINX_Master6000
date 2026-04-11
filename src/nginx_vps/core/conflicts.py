"""Pure conflict detection helpers."""

from nginx_vps.core.models import Conflict, InventorySnapshot


def detect_conflicts(snapshot: InventorySnapshot) -> list[Conflict]:
    """Detect actionable findings from a normalized snapshot."""
    conflicts: list[Conflict] = []

    process_ports: dict[int, set[str]] = {}
    process_addresses: dict[int, set[str]] = {}
    for binding in snapshot.port_bindings:
        process_ports.setdefault(binding.port, set()).add(binding.process_name)
        process_addresses.setdefault(binding.port, set()).add(binding.address)

    for port, process_names in sorted(process_ports.items()):
        if len(process_names) == 2 and "systemd" in process_names:
            continue
        if len(process_names) > 1:
            processes = ", ".join(sorted(process_names))
            addresses = ", ".join(sorted(process_addresses.get(port, set())))
            conflicts.append(
                Conflict(
                    kind="multi-process-port",
                    summary=f"Multiple processes listen on TCP port {port}.",
                    details=f"Observed processes: {processes}. Observed addresses: {addresses}.",
                    port=port,
                )
            )

    if snapshot.nginx is not None:
        for warning in snapshot.nginx.warnings:
            conflicts.append(
                Conflict(
                    kind="nginx-warning",
                    summary="Nginx reported a configuration warning during inspection.",
                    details=warning,
                )
            )

        nginx_ports = {
            directive.port
            for site in snapshot.nginx.sites
            for directive in site.listen_directives
        }
        active_nginx_ports = {
            binding.port
            for binding in snapshot.port_bindings
            if binding.process_name == "nginx"
        }

        for port in sorted(nginx_ports - active_nginx_ports):
            conflicts.append(
                Conflict(
                    kind="nginx-port-not-active",
                    summary=f"Nginx config references port {port}, but no active nginx listener was observed there.",
                    details="This can happen when the service is down, config test failed, or another process owns the socket.",
                    port=port,
                )
            )

        default_servers: dict[tuple[str, int], list[str]] = {}
        for site in snapshot.nginx.sites:
            for directive in site.listen_directives:
                if directive.default_server:
                    key = (directive.address, directive.port)
                    default_servers.setdefault(key, []).append(site.source_path)

        for (address, port), source_paths in sorted(default_servers.items()):
            if len(source_paths) > 1:
                sources = ", ".join(sorted(source_paths))
                conflicts.append(
                    Conflict(
                        kind="duplicate-default-server",
                        summary=f"Multiple Nginx configs declare default_server for {address}:{port}.",
                        details=f"Observed files: {sources}.",
                        port=port,
                    )
                )

    return conflicts
