# NGINX Master6000

NGINX Master6000 is building an explainable control plane for self-hosted Nginx.

The goal is not to hide Nginx behind another black box. The goal is to make a real VPS readable: which ports are in use, which processes own them, which Nginx files are active, and where configuration or runtime conflicts are waiting to break production.

## Why This Project Exists

Nginx failures are often not caused by one dramatic mistake. They are caused by missing visibility.

- A port is already occupied by another service.
- A config file is included from somewhere unexpected.
- Multiple listeners overlap in a way that is hard to see.
- The server "looks fine" until the next reload, deploy, or certificate renewal.

Today, teams often solve this by SSH archaeology: `ss`, `lsof`, `systemctl`, `nginx -t`, `sites-enabled`, hand-written notes, and too much guesswork. NGINX Master6000 exists to replace that guesswork with a readable operational picture.

## What Problem We Solve

We want one trustworthy place to answer questions like:

- What is listening on this machine right now?
- Which process owns port 80 or 443?
- Which Nginx files are actually active?
- Where are the obvious conflicts before they create downtime?
- How can a teammate understand the server without reverse-engineering it from scratch?

## Product Direction

The long-term direction is an open, safety-first platform for understanding and managing Nginx on VPS infrastructure.

The first milestone is intentionally smaller and safer:

- Read-only inspection first.
- Local and SSH-based target support.
- Port and process visibility.
- Nginx configuration inventory rooted in `nginx.conf`.
- Human-readable conflict detection.

This repository currently contains the initial scaffold for that MVP. It does not yet implement live inspection logic.

## Safety-First Principles

Security is part of the product and part of the repository.

- No secrets, private keys, certificates, or host-specific credentials belong in this repository.
- Sample configuration stays minimal and intentionally excludes authentication material.
- The first runtime milestone is read-only by default.
- Packaging and CLI entry points are tested so the public contract stays trustworthy.
- GitHub automation is set up to run tests, package smoke checks, and dependency audits.

## Why Open Source

This problem shows up across small teams, agencies, indie operators, homelabs, startups, and community VPS setups. Open source is the right model for building trust here:

- the diagnosis logic should be inspectable
- the safety posture should be visible
- the roadmap should be shaped by real operator pain
- the community should be able to verify, challenge, and improve the tool

## Repository Layout

```text
NGINX_Master6000/
├─ README.md
├─ CHANGELOG.md
├─ LICENSE
├─ CONTRIBUTING.md
├─ CODE_OF_CONDUCT.md
├─ pyproject.toml
├─ .github/
├─ config/
│  └─ app.example.toml
├─ docs/
│  ├─ product/
│  ├─ architecture/
│  └─ adr/
├─ src/
│  └─ nginx_vps/
├─ tests/
├─ examples/
├─ reports/
└─ state/
```

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
nginx-vps --help
python3 -m pytest
```

## Community Standards

Before opening a pull request or issue:

- read [CONTRIBUTING.md](CONTRIBUTING.md)
- read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- read [.github/SECURITY.md](.github/SECURITY.md)
- never paste credentials, internal IPs, private certificates, or private keys into public threads

## Roadmap

1. Build a reliable local and SSH target model for inspection.
2. Parse active Nginx configuration into a normalized inventory.
3. Detect port collisions, overlapping listeners, and config surprises with actionable output.
4. Add machine-readable output without sacrificing human-readable diagnostics.
5. Reuse the same core model for a future API or UI layer once the diagnostic foundation is stable.
