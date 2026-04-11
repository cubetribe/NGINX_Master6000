# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial Python project scaffold with a CLI entry point for read-only Nginx/VPS inspection.
- Core package structure for inventory modeling, conflict detection, and adapter boundaries.
- Seed documentation for product scope, architecture, and the CLI-first decision.
- GitHub community files for contributing, pull requests, issue intake, code ownership, and security reporting.
- GitHub automation for CI, packaging smoke checks, dependency audits, and Dependabot updates.
- A working `nginx-vps status` MVP for Linux `local` targets and SSH-backed remote inspection.
- Read-only adapters for `ss -H -ltnp`, `nginx -T`, target config loading, and human-readable findings.
- Fixture-driven parser tests plus live validation against a real SSH target and a Linux `local` run.
- A persisted MVP implementation brief under `reports/generated/`.
- Explicit `--ssh-key-path` support and local config auto-discovery for beginner-friendly, key-only SSH workflows.

### Docs

- Initial README with product vision, MVP scope, non-goals, setup, and roadmap.
- Open-source README rewrite with clearer project positioning, operator pain points, and community onboarding guidance.
- Added a secure VPS onboarding tutorial and a ready-to-paste Vibe Coding assistant prompt with SSH key-only guidance.
- Updated public docs to reflect the working MVP, SSH-alias guidance, and the real `nginx-vps status` flow.

### Infra

- Baseline `pyproject.toml`, pytest configuration, example config, project placeholders, and stricter secret-focused ignore rules.

### Changed

- Replaced the temporary proprietary placeholder with an Apache-2.0 open-source license.
- Replaced the placeholder CLI with real local/SSH inspection and output formatting.
