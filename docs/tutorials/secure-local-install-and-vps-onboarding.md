# Secure Local Install and VPS Onboarding

This guide is for the safest early workflow:

1. install NGINX Master6000 on your local machine
2. connect to your VPS over SSH
3. use a dedicated local SSH key
4. avoid password-based login for normal operation

For the current milestone, this is still safer than exposing a writable management surface on the VPS. If you later add the web UI, keep it read-only, keep it behind HTTPS, and keep browser login password-free.

## Security Baseline

Before you start, follow these rules:

- Do not store passwords, private keys, or certificates in this repository.
- Do not paste secrets or full production configs into AI tools.
- Prefer a dedicated local SSH key just for this VPS or this project.
- If possible, use a dedicated Linux user with `sudo` instead of daily root login.
- If your server still needs password login for first access, use it only to install your public key and then move to key-based access.

## Recommended Setup Model

Recommended:

- your laptop or workstation runs `nginx-vps`
- your VPS is the inspection target
- SSH uses a local key such as `~/.ssh/id_ed25519` or a dedicated key like `~/.ssh/id_nginx_master6000`

Not recommended as the first public tutorial:

- storing a VPS password in a prompt
- asking an AI assistant to guess SSH credentials
- copying private keys into repo files
- enabling broad password-based remote access just to get started

## Step 1: Generate a Dedicated Local SSH Key

On your local machine:

```bash
ssh-keygen -t ed25519 -C "nginx-master6000" -f ~/.ssh/id_nginx_master6000
chmod 600 ~/.ssh/id_nginx_master6000
chmod 644 ~/.ssh/id_nginx_master6000.pub
```

This creates:

- private key: `~/.ssh/id_nginx_master6000`
- public key: `~/.ssh/id_nginx_master6000.pub`

Never upload or commit the private key.

## Step 2: Install the Public Key on the VPS

If your server already allows key-based login:

```bash
ssh-copy-id -i ~/.ssh/id_nginx_master6000.pub -p <SSH_PORT> <SSH_USER>@<SSH_HOST>
```

If you must use password login once for bootstrap, do it only long enough to install the public key.

Then verify key access:

```bash
ssh -i ~/.ssh/id_nginx_master6000 -p <SSH_PORT> <SSH_USER>@<SSH_HOST> "echo ok"
```

## Step 3: Prefer Key-Only SSH Going Forward

After key login works, your VPS should move toward:

- key-based SSH login for operators
- no password sharing in chat, prompts, or notes
- reduced reliance on direct root password access

If you manage the SSH daemon yourself, the target end-state is usually:

- `PubkeyAuthentication yes`
- `PasswordAuthentication no`

Do not change SSH daemon settings blindly on a production VPS. Confirm that key login works in a second terminal first.

## Step 4: Install NGINX Master6000 Locally

Clone the repository on your local machine:

```bash
git clone https://github.com/cubetribe/NGINX_Master6000.git
cd NGINX_Master6000
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
nginx-vps --help
python3 -m pytest
```

Why local install first:

- your SSH key stays on your machine
- the tool can inspect remote state without exposing another public web surface
- setup is simpler for the current read-only milestone
- the app reuses your local OpenSSH setup instead of managing key material itself

## Step 5: Prepare Local Target Settings Safely

Do not edit the committed example file with real values.

Instead create a local-only config file such as:

```toml
[target]
mode = "ssh"
nginx_conf_path = "/etc/nginx/nginx.conf"

[target.ssh]
host = "your-vps.example"
port = 22
user = "deploy"
key_path = "~/.ssh/id_nginx_master6000"
```

If you already have a local SSH alias with `HostName`, `User`, `Port`, and `IdentityFile`, you can keep the real file even smaller:

```toml
[target]
mode = "ssh"
ssh_host = "your-ssh-alias"
nginx_conf_path = "/etc/nginx/nginx.conf"
```

Keep real local config files untracked, for example:

- `config/app.local.toml`
- `.env.local`

Do not store:

- private key content
- VPS passwords
- internal customer inventories

## Step 6: First Read-Only Checks

Before you automate anything, confirm the server manually:

```bash
ssh -i ~/.ssh/id_nginx_master6000 -p <SSH_PORT> <SSH_USER>@<SSH_HOST> "nginx -t"
ssh -i ~/.ssh/id_nginx_master6000 -p <SSH_PORT> <SSH_USER>@<SSH_HOST> "ss -ltnp | head"
```

The point of the first milestone is visibility, not mutation.

## Optional: Run the Read-Only Web UI on the VPS

If you want a browser surface later, keep the model conservative:

- run the Python web process on `127.0.0.1`
- put Nginx in front of it on `443`
- require a local SSH-key challenge for login
- do not add a browser password fallback

The dedicated deployment guide is here:

- [Secure web UI deployment](secure-web-ui-deployment.md)

## Step 7: Run the MVP Safely

Use either your auto-discovered local config file:

```bash
nginx-vps status
```

Or call the target explicitly with your SSH alias or host and key path:

```bash
nginx-vps status \
  --mode ssh \
  --ssh-host your-ssh-alias \
  --ssh-key-path ~/.ssh/id_nginx_master6000
```

What the current MVP does:

- lists active listening TCP ports and the processes behind them
- runs `nginx -T` read-only and summarizes active config files and parsed site blocks
- surfaces Nginx warnings and obvious findings without editing the server

What it does not do:

- edit config files
- reload Nginx
- copy SSH keys
- store credentials in the repository

## For Less Experienced VPS Users

Use this checklist:

- I created a local SSH key
- I installed only the public key on the server
- I verified SSH key login before touching SSH settings
- I cloned the repo locally, not into a public shared folder
- I did not paste passwords or private keys into prompts
- I understand that this first version is read-only and diagnostic-first

## If You Want AI Assistance

Use the companion prompt:

- [Vibe coding assistant prompt](vibecoding-vps-onboarding-prompt.md)

It is written to keep the assistant conservative, explain steps clearly, and avoid password-based shortcuts.
