"""CLI entry point for read-only Nginx and VPS inspection."""

from pathlib import Path

import typer

from nginx_vps.config import load_target_settings, load_web_settings
from nginx_vps.reporting import render_status_report
from nginx_vps.status import collect_status_snapshot
from nginx_vps.web.client import complete_web_login
from nginx_vps.web.server import serve_web_ui

app = typer.Typer(
    help=(
        "Read-only Nginx and VPS diagnostics with clear port and config visibility. "
        "Run `nginx-vps status --help` or `nginx-vps web serve --help` for secure target and web options."
    ),
    no_args_is_help=True,
)
web_app = typer.Typer(
    help="Serve the secure read-only browser UI with SSH-key challenge login only.",
    no_args_is_help=True,
)
app.add_typer(web_app, name="web")


@app.callback()
def main_callback() -> None:
    """Read-only inspection commands for Nginx and VPS targets."""


@app.command()
def status(
    config: Path | None = typer.Option(
        None,
        "--config",
        dir_okay=False,
        exists=False,
        help=r"Optional local TOML file with a top-level \[target] table.",
    ),
    mode: str | None = typer.Option(
        None,
        "--mode",
        help="Target mode: local or ssh.",
    ),
    ssh_host: str | None = typer.Option(
        None,
        "--ssh-host",
        help="SSH host or local SSH config alias when mode=ssh.",
    ),
    ssh_port: int | None = typer.Option(
        None,
        "--ssh-port",
        min=1,
        max=65535,
        help="SSH port when mode=ssh.",
    ),
    ssh_user: str | None = typer.Option(
        None,
        "--ssh-user",
        help="SSH user when mode=ssh.",
    ),
    ssh_key_path: str | None = typer.Option(
        None,
        "--ssh-key-path",
        help="Path to a local SSH private key. Password authentication is intentionally unsupported.",
    ),
    nginx_conf_path: str | None = typer.Option(
        None,
        "--nginx-conf-path",
        help="Path to nginx.conf on the target.",
    ),
    show_all: bool = typer.Option(
        False,
        "--show-all",
        help="Print all listeners, site summaries, and findings.",
    ),
) -> None:
    """Show a read-only status summary for a target VPS or local host."""
    try:
        settings = load_target_settings(
            config_path=config,
            mode=mode,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            ssh_key_path=ssh_key_path,
            nginx_conf_path=nginx_conf_path,
        )
        snapshot = collect_status_snapshot(settings)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except RuntimeError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    for line in render_status_report(snapshot, show_all=show_all):
        typer.echo(line)

    if snapshot.errors:
        raise typer.Exit(code=1)


@web_app.command("serve")
def web_serve(
    config: Path | None = typer.Option(
        None,
        "--config",
        dir_okay=False,
        exists=False,
        help="Local TOML file with both [target] and [web] tables.",
    ),
    host: str | None = typer.Option(
        None,
        "--host",
        help="Override the bind host for the web UI.",
    ),
    port: int | None = typer.Option(
        None,
        "--port",
        min=1,
        max=65535,
        help="Override the bind port for the web UI.",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="External base URL used for challenge messages and cookie security decisions.",
    ),
    session_secret_env: str | None = typer.Option(
        None,
        "--session-secret-env",
        help="Environment variable name that holds the web session secret.",
    ),
    mode: str | None = typer.Option(
        None,
        "--mode",
        help="Target mode: local or ssh.",
    ),
    ssh_host: str | None = typer.Option(
        None,
        "--ssh-host",
        help="SSH host or local SSH config alias when mode=ssh.",
    ),
    ssh_port: int | None = typer.Option(
        None,
        "--ssh-port",
        min=1,
        max=65535,
        help="SSH port when mode=ssh.",
    ),
    ssh_user: str | None = typer.Option(
        None,
        "--ssh-user",
        help="SSH user when mode=ssh.",
    ),
    ssh_key_path: str | None = typer.Option(
        None,
        "--ssh-key-path",
        help="Path to a local SSH private key. Password authentication is intentionally unsupported.",
    ),
    nginx_conf_path: str | None = typer.Option(
        None,
        "--nginx-conf-path",
        help="Path to nginx.conf on the target.",
    ),
) -> None:
    """Run the secure read-only browser UI."""
    try:
        target_settings = load_target_settings(
            config_path=config,
            mode=mode,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            ssh_key_path=ssh_key_path,
            nginx_conf_path=nginx_conf_path,
        )
        web_settings = load_web_settings(
            config_path=config,
            host=host,
            port=port,
            base_url=base_url,
            session_secret_env=session_secret_env,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    typer.echo(
        f"Serving secure read-only UI on {web_settings.host}:{web_settings.port} "
        f"for target {target_settings.target_label}."
    )
    typer.echo("Browser passwords stay disabled. Login requires a local SSH key signature.")
    try:
        serve_web_ui(web_settings=web_settings, target_settings=target_settings)
    except KeyboardInterrupt:
        typer.echo("Web UI stopped.")


@app.command("web-login")
def web_login(
    base_url: str = typer.Option(
        ...,
        "--base-url",
        help="Base URL of the running NGINX Master6000 web UI.",
    ),
    username: str = typer.Option(
        ...,
        "--username",
        help="Configured login username for the browser session.",
    ),
    challenge_id: str = typer.Option(
        ...,
        "--challenge-id",
        help="Challenge ID shown by the browser login page.",
    ),
    key_path: Path = typer.Option(
        ...,
        "--key-path",
        dir_okay=False,
        exists=False,
        help="Local SSH private key used to sign the browser challenge.",
    ),
) -> None:
    """Approve a browser login by signing the challenge with a local SSH key."""
    try:
        result = complete_web_login(
            base_url=base_url,
            username=username,
            challenge_id=challenge_id,
            key_path=key_path,
        )
    except RuntimeError as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Approved browser login challenge {result.get('challenge_id', challenge_id)} "
        f"for {result.get('username', username)}."
    )


def main() -> None:
    """Run the CLI application."""
    app()


if __name__ == "__main__":
    main()
