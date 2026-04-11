"""Nginx config inspection adapter built on `nginx -T`."""

from pathlib import Path
import re
import shlex

from nginx_vps.adapters.ssh import ReadOnlyCommandRunner
from nginx_vps.core.models import NginxInventory, NginxListenDirective, NginxSite

_FILE_MARKER_RE = re.compile(r"^# configuration file (?P<path>.+):$")
_LISTEN_RE = re.compile(r"^listen\s+(?P<value>.+?);$")
_SERVER_NAME_RE = re.compile(r"^server_name\s+(?P<value>.+?);$")


def load_nginx_inventory(
    runner: ReadOnlyCommandRunner,
    nginx_conf_path: Path,
) -> NginxInventory:
    """Load the effective Nginx config through `nginx -T`."""
    command = f"nginx -T -c {shlex.quote(str(nginx_conf_path))} 2>&1"
    result = runner.run_read_only(command)
    inventory = parse_nginx_t_output(result.stdout, entrypoint=str(nginx_conf_path))

    if result.exit_code != 0 and not inventory.errors:
        error_text = result.stdout.strip() or result.stderr.strip() or "unknown nginx error"
        inventory.errors.append(error_text)

    return inventory


def parse_nginx_t_output(output: str, *, entrypoint: str) -> NginxInventory:
    """Parse `nginx -T` output into a normalized config inventory."""
    config_files: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    site_sections: dict[str, list[str]] = {}

    current_path: str | None = None
    for line in output.splitlines():
        marker = _FILE_MARKER_RE.match(line)
        if marker is not None:
            current_path = marker.group("path")
            config_files.append(current_path)
            site_sections.setdefault(current_path, [])
            continue

        if "[warn]" in line:
            warnings.append(line.strip())
            continue
        if line.startswith("nginx:") and "syntax is ok" not in line and "test is successful" not in line:
            errors.append(line.strip())
            continue
        if current_path is not None:
            site_sections[current_path].append(line)

    sites = [
        site
        for path, lines in site_sections.items()
        for site in _parse_sites_from_file(path, lines)
    ]
    return NginxInventory(
        entrypoint=entrypoint,
        config_files=config_files,
        sites=sites,
        warnings=warnings,
        errors=errors,
        config_test_passed="test is successful" in output,
    )


def _parse_sites_from_file(path: str, lines: list[str]) -> list[NginxSite]:
    sites: list[NginxSite] = []
    brace_depth = 0
    server_depth: int | None = None
    current_server_names: list[str] = []
    current_listens: list[NginxListenDirective] = []

    for raw_line in lines:
        uncommented = raw_line.split("#", 1)[0].strip()
        if uncommented.startswith("server") and uncommented.endswith("{") and server_depth is None:
            server_depth = brace_depth + uncommented.count("{")
            current_server_names = []
            current_listens = []

        if server_depth is not None and uncommented:
            listen_match = _LISTEN_RE.match(uncommented)
            if listen_match is not None:
                directive = _parse_listen_directive(listen_match.group("value"))
                if directive is not None:
                    current_listens.append(directive)
            server_name_match = _SERVER_NAME_RE.match(uncommented)
            if server_name_match is not None:
                current_server_names.extend(
                    token for token in server_name_match.group("value").split() if token
                )

        brace_depth += uncommented.count("{")
        brace_depth -= uncommented.count("}")

        if server_depth is not None and brace_depth < server_depth:
            sites.append(
                NginxSite(
                    name=_site_name(path, current_server_names, len(sites) + 1),
                    source_path=path,
                    listen_ports=sorted({directive.port for directive in current_listens}),
                    server_names=sorted(dict.fromkeys(current_server_names)),
                    listen_directives=list(current_listens),
                )
            )
            server_depth = None
            current_server_names = []
            current_listens = []

    return sites


def _parse_listen_directive(value: str) -> NginxListenDirective | None:
    tokens = value.split()
    if not tokens:
        return None

    endpoint = tokens[0]
    address = "*"
    port: int | None = None

    if endpoint.isdigit():
        port = int(endpoint)
    elif endpoint.startswith("[") and "]:" in endpoint:
        address, port_text = endpoint.rsplit("]:", 1)
        address = address[1:]
        port = int(port_text) if port_text.isdigit() else None
    elif ":" in endpoint:
        address, port_text = endpoint.rsplit(":", 1)
        port = int(port_text) if port_text.isdigit() else None

    if port is None:
        return None

    option_tokens = set(tokens[1:])
    return NginxListenDirective(
        address=address,
        port=port,
        raw=value,
        ssl="ssl" in option_tokens,
        http2="http2" in option_tokens,
        default_server="default_server" in option_tokens,
    )


def _site_name(path: str, server_names: list[str], index: int) -> str:
    if server_names:
        return server_names[0]
    return f"{Path(path).name}#{index}"
