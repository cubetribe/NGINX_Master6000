# Architecture Overview

## Direction

The project starts as a read-only CLI because the core product value is operational clarity, not configuration editing. The first architecture should make inspection logic easy to test and easy to reuse later.

The current repository contains only the initial scaffold. Target resolution, configuration loading, and live inspection remain planned MVP behavior rather than implemented runtime features.

## Layers

- `cli`: command definitions and output formatting.
- `core`: normalized models, inventory composition, and conflict evaluation.
- `adapters`: boundaries for SSH execution, Nginx filesystem parsing, and process/port discovery.

## Data Flow

The planned MVP data flow is:

1. The CLI reads minimal local settings and resolves whether inspection should run against the local host or an SSH target.
2. The CLI loads the configured `nginx.conf` path, defaulting to the standard server entrypoint unless overridden.
3. Adapter layers collect raw process, port, and Nginx config inputs.
4. Core inventory logic normalizes those inputs into a single snapshot.
5. Conflict logic evaluates the snapshot and returns human-readable findings.

## Design Constraints

- Read-only by default.
- Clear separation between I/O and pure logic.
- Testability through fixtures instead of live VPS dependencies.
- Stable package boundaries that can support a future API or UI.
