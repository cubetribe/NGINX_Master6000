"""Read-only command runners for local and SSH inspection."""

from dataclasses import dataclass
import os
import platform
import subprocess
from typing import Protocol


@dataclass(slots=True)
class SSHConnectionConfig:
    """Minimal SSH target settings for remote inspection."""

    host: str
    user: str | None = None
    port: int | None = None
    key_path: str | None = None


@dataclass(slots=True)
class CommandResult:
    """Captured output from a local or remote command."""

    command: str
    stdout: str
    stderr: str
    exit_code: int


class ReadOnlyCommandRunner(Protocol):
    """Protocol for command runners used by inspection adapters."""

    def run_read_only(self, command: str) -> CommandResult:
        """Run a read-only command and return the captured result."""


class LocalCommandRunner:
    """Run read-only inspection commands on the local machine."""

    def run_read_only(self, command: str) -> CommandResult:
        if platform.system() != "Linux":
            raise RuntimeError(
                "Local inspection currently supports Linux targets only. "
                "Use --mode ssh from macOS or Windows."
            )
        process = subprocess.run(
            ["/bin/sh", "-lc", command],
            capture_output=True,
            check=False,
            text=True,
            timeout=20,
        )
        return CommandResult(
            command=command,
            stdout=process.stdout,
            stderr=process.stderr,
            exit_code=process.returncode,
        )


class SSHCommandRunner:
    """Run read-only inspection commands through the system SSH client."""

    def __init__(self, config: SSHConnectionConfig) -> None:
        self.config = config

    def run_read_only(self, command: str) -> CommandResult:
        """Run a remote read-only command and return its output."""
        host_ref = self.config.host
        if self.config.user:
            host_ref = f"{self.config.user}@{host_ref}"

        ssh_command = [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "PreferredAuthentications=publickey",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            "PubkeyAuthentication=yes",
            "-o",
            "KbdInteractiveAuthentication=no",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
        ]
        if self.config.port is not None:
            ssh_command.extend(["-p", str(self.config.port)])
        if self.config.key_path is not None:
            ssh_command.extend(["-i", self.config.key_path, "-o", "IdentitiesOnly=yes"])
        ssh_command.extend([host_ref, command])
        process = subprocess.run(
            ssh_command,
            capture_output=True,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
            text=True,
            timeout=30,
        )
        return CommandResult(
            command=" ".join(ssh_command),
            stdout=process.stdout,
            stderr=process.stderr,
            exit_code=process.returncode,
        )
