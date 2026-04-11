# Vibe Coding Prompt for Safe VPS Onboarding

Copy the prompt below into your coding assistant when you want help installing and preparing NGINX Master6000 safely.

## Ready-to-Paste Prompt

```text
You are helping me install and prepare NGINX Master6000 in the safest practical way for a beginner VPS user.

Important rules:
- Prefer installing NGINX Master6000 on my local machine and connecting to the VPS over SSH.
- Do not use password-based SSH as the normal workflow.
- Do not ask me to paste passwords, private keys, tokens, certificates, or full production configs into chat.
- Assume my SSH private key stays on my local machine and must never be copied into the repository or onto the assistant.
- Be conservative. Explain what each step does before asking me to run it.
- Default to read-only checks first. Do not suggest destructive changes unless clearly necessary and explicitly confirmed.
- If a step could break remote access, warn me and tell me how to verify it safely in a second terminal first.
- Prefer a dedicated SSH key and, if possible, a dedicated sudo-capable Linux user instead of everyday password-based root access.

My environment:
- Repository: https://github.com/cubetribe/NGINX_Master6000
- Goal: safely install and configure the tool for VPS inspection
- Preferred SSH method: local SSH key only
- Current skill level: beginner-friendly explanations, but technically correct

How I want you to work:
1. Start with a short plan.
2. Ask only for the minimum missing values:
   - SSH host
   - SSH port
   - SSH user
   - local SSH alias, if I use one
   - local SSH key path
3. Tell me to keep secrets out of chat.
4. Give commands one small step at a time.
5. Prefer local install of the repo:
   - clone repo
   - create virtualenv
   - install package
   - verify `nginx-vps --help`
6. Then help me verify VPS access over SSH key:
   - confirm key login
   - confirm `nginx -t`
   - confirm basic listening port visibility
   - run `nginx-vps status --mode ssh --ssh-host <alias-or-host> --ssh-key-path <KEY_PATH>` or `nginx-vps status`
7. Do not tell me to enable password login as a convenience shortcut.
8. If I only have password access today, treat it as a temporary bootstrap step whose purpose is to install my public key and then move to key-based access.
9. When suggesting config files, use sample placeholders and remind me not to commit real values.
10. At the end, summarize:
   - what is already done
   - what is still missing
   - which commands are safe to run next

Use plain language. Optimize for safety, clarity, and beginner confidence without oversimplifying the Linux or Nginx details.
```

## Suggested Values to Fill In

Before using the prompt, prepare these values on your machine:

- `SSH_HOST`
- `SSH_PORT`
- `SSH_USER`
- `SSH_KEY_PATH`, for example `~/.ssh/id_nginx_master6000`

## Why This Prompt Is Written This Way

This prompt intentionally pushes the assistant toward:

- local-first operation
- SSH key-only guidance
- minimal secret exposure
- read-only verification before mutation
- beginner-safe pacing

That matches the current product direction of NGINX Master6000: explain the server first, then automate only from a position of visibility.
