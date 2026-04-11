# Product Scope

## Problem Statement

Managing Nginx on a VPS often fails at the visibility layer first. Operators need to know which ports are occupied, which processes own them, which Nginx files are active, and where overlapping configuration creates confusion.

## Target Outcome

The first release should give a reliable, read-only overview of Nginx and VPS runtime state that a human can understand quickly without digging through scattered files and shell output.

## MVP Capabilities

- Inspect a local machine or SSH target without changing server state.
- Inventory listening ports and the processes behind them.
- Trace active Nginx configuration from the configured `nginx.conf` entrypoint.
- Detect obvious conflicts such as Nginx config warnings, competing port usage, and duplicate default servers.
- Present findings in plain language suitable for operators and developers.
- Keep password-based SSH out of the public CLI path and prefer local key-based access for remote targets.

## Non-Goals

- Editing Nginx config files.
- Restarting services or applying fixes.
- Full hosting control-panel behavior.
- Domain, DNS, certificate, or deployment management.

## Success Signals

- A user can identify a port collision quickly.
- A user can see which Nginx files are active from one command.
- Output is understandable without requiring deep Nginx internals knowledge.
