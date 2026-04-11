# MVP Implementation Brief

## Scope

- One read-only command: `nginx-vps status`
- Target modes:
  - `local` for Linux hosts
  - `ssh` through the system `ssh` client using the operator's local SSH config and local keys
- Data collected:
  - active listening TCP ports and owning processes
  - effective Nginx config via `nginx -T`
  - parsed site summaries, active config files, and Nginx warnings
- Explicitly out of scope:
  - config edits
  - reloads or restarts
  - password auth workflows
  - app-managed SSH key handling

## Required Commands

- `ss -H -ltnp`
- `nginx -T -c <nginx_conf_path> 2>&1`
- `ssh -T -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no`

## Parsing Strategy

- Parse `ss` line-by-line into normalized TCP listeners with:
  - address
  - port
  - process name
  - representative PID
  - process count for repeated worker processes
- Parse `nginx -T` by section markers:
  - `# configuration file /path:`
  - collect warnings before and between file sections
  - track `server {}` blocks with brace depth
  - parse `listen` and `server_name` directives inside each server block
- Build one normalized snapshot from both adapters, then derive findings from:
  - Nginx warnings
  - configured Nginx ports without active `nginx` listeners
  - multi-process socket ownership except the common `systemd` socket-activation pair

## Failure Modes To Handle

- local mode on non-Linux host
- missing `ss`
- missing `nginx`
- SSH alias with host-specific port or user in local SSH config
- SSH key missing or password prompt blocked by batch mode
- `nginx -T` warning-only success
- `nginx -T` non-zero exit with useful stderr/stdout
- partial data availability, for example ports collected but Nginx parse failed

## Acceptance Test Matrix

- Unit:
  - `ss` parser aggregates repeated worker processes
  - `nginx -T` parser extracts config files, site summaries, and warnings
  - target config loader merges TOML plus CLI overrides
  - conflict logic ignores `systemd` socket activation noise
- CLI:
  - `status` renders a normalized snapshot
  - installed console script `nginx-vps` resolves correctly
- Real validation:
  - local macOS operator -> `ssh` mode against a real VPS
  - Linux VPS -> `local` mode from a temporary isolated venv
  - both paths confirm:
    - listener inventory
    - active Nginx config inventory
    - surfaced Nginx warnings
