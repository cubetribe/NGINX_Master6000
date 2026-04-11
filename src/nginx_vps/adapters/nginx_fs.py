"""Nginx filesystem adapter boundary."""

from pathlib import Path

from nginx_vps.core.models import NginxSite


def load_nginx_sites(nginx_conf_path: Path) -> list[NginxSite]:
    """Load Nginx site definitions from the configured entrypoint."""
    raise NotImplementedError("Nginx filesystem parsing is not implemented yet.")
