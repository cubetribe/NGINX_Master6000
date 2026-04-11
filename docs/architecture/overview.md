# Architecture Overview

## Direction

The project starts as a read-only CLI because the core product value is operational clarity, not configuration editing. The first architecture should make inspection logic easy to test and easy to reuse later.

The current MVP resolves a local or SSH target, collects listener data through `ss -H -ltnp`, collects the effective Nginx config through `nginx -T -c <path>`, and turns both inputs into a normalized inventory plus human-readable findings. That same inspection core now powers a minimal secure browser UI.

## Layers

- `cli`: command definitions and output formatting.
- `core`: normalized models, inventory composition, and conflict evaluation.
- `adapters`: boundaries for SSH execution, Nginx filesystem parsing, and process/port discovery.
- `web`: WSGI app, SSH-key challenge auth, rate limiting, and secure session handling.

## Data Flow

The implemented MVP data flow is:

1. The CLI reads optional local TOML settings and CLI overrides, auto-discovers `config/app.local.toml` or `config/app.toml` when present, then resolves whether inspection runs against the local host or an SSH target.
2. The SSH path shells out to the system `ssh` client in batch mode so local OpenSSH config and local SSH keys stay the source of truth, with optional explicit `--ssh-key-path` support when a beginner wants a direct key path instead of an SSH alias.
3. Adapter layers collect raw process, port, and Nginx config inputs from `ss` and `nginx -T`.
4. Core inventory logic normalizes those inputs into a single snapshot of listeners, config files, parsed site summaries, warnings, and errors.
5. Conflict logic prioritizes actionable findings such as Nginx warnings, missing active Nginx listeners, and multi-process socket ownership.
6. The web layer reuses the same snapshot and conflict logic, but adds a separate SSH-signature login flow: the browser starts a short-lived challenge, the operator signs it locally with `ssh-keygen -Y sign`, and the server verifies the signature against configured public keys before issuing a secure session cookie.

## Design Constraints

- Read-only by default.
- Clear separation between I/O and pure logic.
- Testability through fixtures instead of live VPS dependencies.
- Stable package boundaries that can support a future API or UI.
- SSH keys remain outside the app and inside the operator's existing SSH tooling.
- Browser login stays password-free and read-only, with short-lived challenges, session cookies, and per-IP-plus-user lockout.
