"""Shared human-readable reporting helpers."""

from nginx_vps.core.conflicts import detect_conflicts
from nginx_vps.core.models import Conflict, InventorySnapshot, NginxSite, PortBinding


def render_status_report(snapshot: InventorySnapshot, *, show_all: bool = False) -> list[str]:
    """Render a human-readable status report."""
    conflicts = detect_conflicts(snapshot)
    lines = [
        f"Target: {snapshot.target_label}",
        f"Mode: {snapshot.mode}",
        "Safety: read-only inspection only",
    ]
    if snapshot.mode == "ssh":
        lines.append("SSH auth: local OpenSSH keys only")
    if getattr(snapshot, "config_path", None):
        lines.append(f"Config source: {snapshot.config_path}")
    lines.extend(f"Note: {note}" for note in snapshot.notes)

    lines.append("")
    lines.append("Listeners")
    lines.extend(_render_port_bindings(snapshot.port_bindings, show_all=show_all))

    lines.append("")
    lines.append("Nginx")
    lines.extend(_render_nginx(snapshot, show_all=show_all))

    lines.append("")
    lines.append("Findings")
    lines.extend(_render_conflicts_or_failure_notice(snapshot, conflicts, show_all=show_all))

    if snapshot.errors:
        lines.append("")
        lines.append("Errors")
        lines.extend(f"- {error}" for error in snapshot.errors)

    return lines


def _render_port_bindings(bindings: list[PortBinding], *, show_all: bool) -> list[str]:
    if not bindings:
        return ["- No listening TCP ports could be collected."]

    lines: list[str] = []
    display_bindings = bindings if show_all else bindings[:15]
    for binding in display_bindings:
        pid_text = f", pid {binding.pid}" if binding.pid is not None else ""
        count_text = ""
        if binding.process_count > 1:
            count_text = f", {binding.process_count} processes"
        lines.append(
            f"- {binding.protocol} {_format_endpoint(binding.address, binding.port)} -> "
            f"{binding.process_name}{pid_text}{count_text}"
        )

    remaining = len(bindings) - len(display_bindings)
    if remaining > 0:
        lines.append(f"- ... {remaining} more listeners hidden; rerun with --show-all.")
    return lines


def _render_nginx(snapshot: InventorySnapshot, *, show_all: bool) -> list[str]:
    if snapshot.nginx is None:
        return ["- Nginx data could not be collected."]

    lines = [
        f"- Entrypoint: {snapshot.nginx.entrypoint}",
        f"- Config test passed: {'yes' if snapshot.nginx.config_test_passed else 'no'}",
        f"- Active config files: {len(snapshot.nginx.config_files)}",
        f"- Parsed site summaries: {len(snapshot.nginx.sites)}",
    ]

    if snapshot.nginx.config_files:
        preview = snapshot.nginx.config_files if show_all else snapshot.nginx.config_files[:8]
        for config_path in preview:
            lines.append(f"- config: {config_path}")
        remaining_files = len(snapshot.nginx.config_files) - len(preview)
        if remaining_files > 0:
            lines.append(f"- ... {remaining_files} more config files hidden; rerun with --show-all.")

    if snapshot.nginx.sites:
        display_sites = snapshot.nginx.sites if show_all else snapshot.nginx.sites[:12]
        for site in display_sites:
            lines.append(_render_site(site))
        remaining_sites = len(snapshot.nginx.sites) - len(display_sites)
        if remaining_sites > 0:
            lines.append(f"- ... {remaining_sites} more site summaries hidden; rerun with --show-all.")
    return lines


def _render_site(site: NginxSite) -> str:
    ports = ", ".join(str(port) for port in site.listen_ports) if site.listen_ports else "none"
    names = ", ".join(site.server_names[:4]) if site.server_names else "(no server_name)"
    if len(site.server_names) > 4:
        names = f"{names}, +{len(site.server_names) - 4} more"
    return f"- site: {site.name} | ports: {ports} | names: {names} | file: {site.source_path}"


def _render_conflicts(conflicts: list[Conflict], *, show_all: bool) -> list[str]:
    if not conflicts:
        return ["- No obvious findings detected from the current snapshot."]

    lines: list[str] = []
    display_conflicts = conflicts if show_all else conflicts[:12]
    for conflict in display_conflicts:
        lines.append(f"- {conflict.summary}")
        lines.append(f"  {conflict.details}")
    remaining = len(conflicts) - len(display_conflicts)
    if remaining > 0:
        lines.append(f"- ... {remaining} more findings hidden; rerun with --show-all.")
    return lines


def _render_conflicts_or_failure_notice(
    snapshot: InventorySnapshot, conflicts: list[Conflict], *, show_all: bool
) -> list[str]:
    """Render findings, or a failure notice when no usable snapshot was collected."""
    if not conflicts and snapshot.errors and not snapshot.port_bindings and snapshot.nginx is None:
        return ["- No findings rendered because inspection did not complete successfully; see Errors below."]
    return _render_conflicts(conflicts, show_all=show_all)


def _format_endpoint(address: str, port: int) -> str:
    if ":" in address and not address.startswith("["):
        return f"[{address}]:{port}"
    return f"{address}:{port}"

