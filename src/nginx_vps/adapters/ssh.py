"""SSH adapter boundary for future remote read-only inspection."""

from dataclasses import dataclass


@dataclass(slots=True)
class SSHConnectionConfig:
    """Minimal SSH target settings for remote inspection."""

    host: str
    user: str
    port: int = 22


class SSHCommandRunner:
    """Placeholder command runner for future SSH-backed collection."""

    def __init__(self, config: SSHConnectionConfig) -> None:
        self.config = config

    def run_read_only(self, command: str) -> str:
        """Run a remote read-only command and return its output."""
        raise NotImplementedError("SSH-backed inspection is not implemented yet.")
