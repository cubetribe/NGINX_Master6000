# Security Policy

## Supported Versions

This project is in early development. Security fixes are expected to land on the active `main` branch first.

| Version | Supported |
| --- | --- |
| 0.x | Yes |

## Reporting a Vulnerability

- Do not open a public GitHub issue for a suspected vulnerability.
- Prefer GitHub Private Vulnerability Reporting for this repository.
- If private reporting is not enabled yet, contact a maintainer privately through GitHub before disclosing details publicly.

## Repository Safety Rules

- Never include secrets, tokens, certificates, private keys, passwords, or real infrastructure inventories in issues, pull requests, fixtures, or sample configs.
- Redact hostnames, IP addresses, usernames, and internal paths when sharing diagnostics.
- Use minimal reproducible examples rather than live production data.

## Operator Safety Guidance

- Prefer running the tool from your local machine and reaching the VPS over SSH.
- Use a dedicated local SSH key for the VPS instead of password authentication.
- Do not paste private keys, password prompts, or unredacted server outputs into AI assistants or public GitHub threads.
- If your VPS still allows password login, treat that as a temporary migration state and move to key-only access before normal operation.

## Maintainer Checklist

Before public launch, maintainers should enable:

- branch protection for `main`
- required status checks
- private vulnerability reporting
- Dependabot alerts and security updates
- secret scanning, if available for the repository
