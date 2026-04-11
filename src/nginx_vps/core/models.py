"""Core models for inventory and conflict reporting."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class PortBinding:
    """Represents a listening process bound to a TCP port."""

    port: int
    protocol: str
    address: str
    process_name: str
    pid: int | None = None
    process_count: int = 1


@dataclass(slots=True)
class NginxListenDirective:
    """Represents a parsed Nginx listen directive."""

    address: str
    port: int
    raw: str
    ssl: bool = False
    http2: bool = False
    default_server: bool = False


@dataclass(slots=True)
class NginxSite:
    """Represents a discovered Nginx site or include fragment."""

    name: str
    source_path: str
    listen_ports: list[int] = field(default_factory=list)
    server_names: list[str] = field(default_factory=list)
    enabled: bool = True
    listen_directives: list[NginxListenDirective] = field(default_factory=list)


@dataclass(slots=True)
class NginxInventory:
    """Normalized view of the effective Nginx configuration."""

    entrypoint: str
    config_files: list[str] = field(default_factory=list)
    sites: list[NginxSite] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    config_test_passed: bool = False


@dataclass(slots=True)
class Conflict:
    """Represents a human-readable finding from the inventory."""

    kind: str
    summary: str
    details: str
    port: int | None = None


@dataclass(slots=True)
class InventorySnapshot:
    """Normalized read-only inventory of process and Nginx state."""

    target_label: str
    mode: str
    config_path: str | None = None
    port_bindings: list[PortBinding] = field(default_factory=list)
    nginx: NginxInventory | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
