"""Process and port inspection adapter boundary."""

from nginx_vps.core.models import PortBinding


def collect_port_bindings() -> list[PortBinding]:
    """Collect read-only process and listening-port information."""
    raise NotImplementedError("Process and port inspection is not implemented yet.")
