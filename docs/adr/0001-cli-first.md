# ADR 0001: Start With a CLI-First Architecture

- Status: Accepted
- Date: 2026-04-11

## Context

The project goal is to make Nginx and VPS state understandable, especially around occupied ports, active config, and conflict detection. The first problem to solve is reliable visibility, not server mutation or UI workflows.

## Decision

Start with a Python 3.12 CLI application using Typer for command wiring and pytest for fixture-driven validation. Keep the public package name focused on the product surface (`nginx_vps`) while keeping the workspace folder name unchanged.

## Consequences

- The first milestone can prioritize read-only inspection and clear output.
- Core logic can remain independent from SSH and filesystem adapters.
- A future API or web UI can reuse the same normalized inventory and conflict logic.
- Interactive editing, provisioning, and remediation are deferred until the inspection model is stable.
