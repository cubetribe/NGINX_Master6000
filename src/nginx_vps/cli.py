"""CLI entry point for read-only Nginx and VPS inspection."""

import typer

app = typer.Typer(
    help="Read-only Nginx and VPS diagnostics with clear port and config visibility.",
    no_args_is_help=True,
)


@app.callback()
def main_callback() -> None:
    """Read-only inspection commands for Nginx and VPS targets."""


@app.command()
def status() -> None:
    """Show a read-only status summary for a target VPS or local host."""
    typer.echo(
        "Read-only status inspection is not implemented yet. "
        "This scaffold will later report listening ports, active Nginx config, "
        "and detected conflicts without changing server state."
    )


def main() -> None:
    """Run the CLI application."""
    app()


if __name__ == "__main__":
    main()
