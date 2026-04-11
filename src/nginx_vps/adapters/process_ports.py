"""Process and port inspection adapter."""

from collections import defaultdict
import re

from nginx_vps.adapters.ssh import ReadOnlyCommandRunner
from nginx_vps.core.models import PortBinding

_SS_LINE_RE = re.compile(
    r"^(?P<state>\S+)\s+\d+\s+\d+\s+(?P<local>\S+)\s+\S+(?:\s+(?P<users>users:\(.*\)))?$"
)
_PROCESS_RE = re.compile(r'\("(?P<name>[^"]+)"(?:,pid=(?P<pid>\d+))?')


def collect_port_bindings(runner: ReadOnlyCommandRunner) -> list[PortBinding]:
    """Collect read-only process and listening-port information."""
    result = runner.run_read_only("ss -H -ltnp")
    if result.exit_code != 0:
        error_text = result.stderr.strip() or result.stdout.strip() or "unknown ss error"
        raise RuntimeError(f"Failed to collect listening TCP ports: {error_text}")
    return parse_ss_output(result.stdout)


def parse_ss_output(output: str) -> list[PortBinding]:
    """Parse `ss -H -ltnp` output into normalized port bindings."""
    aggregated: dict[tuple[str, str, int, str], set[int]] = defaultdict(set)

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _SS_LINE_RE.match(line)
        if match is None:
            continue

        address, port = _split_endpoint(match.group("local"))
        if port is None:
            continue

        users_text = match.group("users") or ""
        processes = list(_PROCESS_RE.finditer(users_text))
        if not processes:
            aggregated[("tcp", address, port, "unknown")].add(-1)
            continue

        for process in processes:
            pid_text = process.group("pid")
            pid = int(pid_text) if pid_text is not None else -1
            aggregated[("tcp", address, port, process.group("name"))].add(pid)

    bindings: list[PortBinding] = []
    for (protocol, address, port, process_name), pids in sorted(
        aggregated.items(),
        key=lambda item: (item[0][2], item[0][1], item[0][3]),
    ):
        real_pids = sorted(pid for pid in pids if pid >= 0)
        bindings.append(
            PortBinding(
                protocol=protocol,
                address=address,
                port=port,
                process_name=process_name,
                pid=real_pids[0] if real_pids else None,
                process_count=max(len(real_pids), 1),
            )
        )
    return bindings


def _split_endpoint(value: str) -> tuple[str, int | None]:
    value = value.strip()
    if value.startswith("[") and "]:" in value:
        address, port_text = value.rsplit("]:", 1)
        return address[1:], _parse_port(port_text)
    if ":" not in value:
        return value, None
    address, port_text = value.rsplit(":", 1)
    return address, _parse_port(port_text)


def _parse_port(value: str) -> int | None:
    return int(value) if value.isdigit() else None
