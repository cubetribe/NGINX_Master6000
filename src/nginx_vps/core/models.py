"""Core models for inventory and conflict reporting."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class PortBinding:
    """Represents a listening process bound to a TCP or UDP port."""

    port: int
    protocol: str
    process_name: str
    pid: int | None = None


@dataclass(slots=True)
class NginxSite:
    """Represents a discovered Nginx site or include fragment."""

    name: str
    source_path: str
    listen_ports: list[int] = field(default_factory=list)
    enabled: bool = True


@dataclass(slots=True)
class Conflict:
    """Represents a human-readable conflict found in the inventory."""

    kind: str
    summary: str
    details: str
    port: int | None = None


@dataclass(slots=True)
class InventorySnapshot:
    """Normalized read-only inventory of process and Nginx state."""

    port_bindings: list[PortBinding] = field(default_factory=list)
    nginx_sites: list[NginxSite] = field(default_factory=list)
