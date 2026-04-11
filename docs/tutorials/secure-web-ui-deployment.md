# Secure Web UI Deployment

This guide deploys the smallest real browser UI for NGINX Master6000 without adding a browser password.

The web process stays read-only. Authentication works like this:

1. the browser starts a short-lived login challenge
2. you approve it locally with `nginx-vps web-login`
3. the server verifies an OpenSSH signature against configured public keys
4. only then does the browser receive a session cookie

## Security Model

Use these rules:

- keep the Python web server bound to `127.0.0.1`
- terminate TLS in Nginx
- set the session secret through an environment variable
- store only public keys in config
- do not add a password fallback
- keep the UI read-only

## Example Config

Create an untracked config file on the server such as `/etc/nginx-master6000/app.toml`:

```toml
[target]
mode = "local"
nginx_conf_path = "/etc/nginx/nginx.conf"

[web]
host = "127.0.0.1"
port = 8420
base_url = "https://nginx.nm-forum.de"
session_secret_env = "NGINX_VPS_WEB_SESSION_SECRET"
trusted_proxy_ips = ["127.0.0.1", "::1"]
challenge_ttl_seconds = 120
challenge_rate_limit = 5
challenge_rate_window_seconds = 600
verify_rate_limit = 8
verify_rate_window_seconds = 600
lockout_threshold = 5
lockout_seconds = 900
session_ttl_seconds = 28800

[[web.users]]
username = "operator"
public_keys = [
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIreplaceWithYourRealPublicKey operator@laptop",
]
```

Generate a strong session secret on the server:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Export it only into the service environment:

```bash
export NGINX_VPS_WEB_SESSION_SECRET="<generated secret>"
```

## Local Validation

Before adding Nginx in front, test the local bind directly on the VPS:

```bash
nginx-vps web serve --config /etc/nginx-master6000/app.toml
```

From a second terminal on the VPS:

```bash
curl -I http://127.0.0.1:8420/health
```

You should get `200 OK`.

## Systemd Service

Example unit:

```ini
[Unit]
Description=NGINX Master6000 read-only web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/nginx-master6000
Environment=NGINX_VPS_WEB_SESSION_SECRET=<generated secret>
ExecStart=/opt/nginx-master6000/.venv/bin/nginx-vps web serve --config /etc/nginx-master6000/app.toml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Do not store the real secret in Git.

## Nginx Reverse Proxy

Keep the upstream on localhost only:

```nginx
server {
    listen 80;
    server_name nginx.nm-forum.de;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name nginx.nm-forum.de;

    ssl_certificate /etc/letsencrypt/live/nginx.nm-forum.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nginx.nm-forum.de/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8420;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Validate before reload:

```bash
nginx -t
systemctl reload nginx
```

## Browser Login Flow

1. Open `https://nginx.nm-forum.de/login`
2. enter the configured username
3. copy the challenge command shown by the page
4. run it locally on your machine:

```bash
nginx-vps web-login \
  --base-url https://nginx.nm-forum.de \
  --username operator \
  --challenge-id <challenge-id> \
  --key-path ~/.ssh/id_nginx_master6000
```

The browser session unlocks only after the signature is verified.

## Operational Notes

- login is locked per IP plus username after repeated failed signatures
- challenges expire automatically
- the server never asks for, stores, or verifies a browser password
- the server never receives your private key
- the dashboard stays read-only and reuses the existing status logic
