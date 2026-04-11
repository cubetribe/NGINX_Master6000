# Contributing to NGINX Master6000

Thanks for contributing.

This project is being built as an explainable, safety-first tool for understanding Nginx on real VPS infrastructure. That means contributions need to improve clarity, reduce operational risk, and keep the repository safe for public collaboration.

## Before You Start

- Read [README.md](README.md) for the product direction.
- Read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Read [.github/SECURITY.md](.github/SECURITY.md).

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

## Branching

- Use short-lived branches for focused changes.
- Keep pull requests small and reviewable.
- Do not mix unrelated refactors into the same contribution.

## Security Rules

- Never commit secrets, private keys, certificates, passwords, tokens, `.env` files, or real server inventories.
- Never post credentials, internal IP addresses, or customer infrastructure details in issues or pull requests.
- Use sample data, fixtures, and redacted logs only.
- If you find a vulnerability, follow [.github/SECURITY.md](.github/SECURITY.md) instead of opening a public issue.

## Contribution Priorities

We especially value contributions that improve:

- Nginx config readability and parser reliability
- port and process diagnostics
- conflict detection quality
- test coverage with realistic fixtures
- documentation that helps non-experts understand what the tool is telling them

## Pull Request Checklist

Before opening a pull request:

- run the relevant tests locally
- update docs if behavior or setup changed
- explain the operator problem your change solves
- confirm that no sensitive data was added to the diff
