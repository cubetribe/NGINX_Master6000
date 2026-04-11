# Web UI Implementation Brief

## Goal

Add the smallest real browser UI on top of the existing read-only diagnostics pipeline without introducing a browser password.

## Implemented Shape

- `nginx-vps web serve` starts a local threaded WSGI server.
- `nginx-vps web-login` performs the local CLI approval step.
- The browser UI starts a short-lived SSH-signature challenge.
- The local CLI signs the challenge with `ssh-keygen -Y sign`.
- The server verifies the signature against configured public keys with `ssh-keygen -Y verify`.
- After approval, the server issues an HttpOnly session cookie with `SameSite=Strict`.

## Security Controls

- No password form and no password verifier in the browser flow.
- Per-IP plus username rate limits and lockout after repeated failed signatures.
- Challenge expiry.
- Secure-cookie mode when the configured base URL is HTTPS.
- Proxy-aware client IP detection limited to trusted proxy IPs.
- Read-only dashboard only; no mutating routes were added.

## Reuse

The dashboard reuses:

- `load_target_settings`
- `collect_status_snapshot`
- `detect_conflicts`
- `render_status_report`

This keeps the CLI and browser outputs grounded in the same inspection pipeline.
