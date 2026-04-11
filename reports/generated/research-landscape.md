# Research Landscape

Date: 2026-04-11

This note summarizes the current landscape around Nginx management tools and sharpens the product direction for NGINX Master6000. The conclusion is consistent with the current README: there is room for a read-only, CLI-first tool that explains existing VPS state instead of taking ownership of the server.

## Benchmark Projects

- [Nginx Proxy Manager](https://github.com/NginxProxyManager/nginx-proxy-manager): strong benchmark for approachable proxy-host UX, but it is built as a gateway product and its quick setup assumes ownership of ports `80`, `81`, and `443`. Good reference for clarity and onboarding, weaker reference for diagnosing an already-running VPS.
- [Nginx UI](https://github.com/0xJacky/nginx-ui): strong benchmark for breadth. It offers config editing, log viewing, config test/reload, and a web terminal, but it is explicitly mutation-oriented and assumes a Debian-style `sites-available` / `sites-enabled` structure in common workflows. Good reference for inventory surface area, weak fit for a low-risk first milestone.
- [ngxtop](https://github.com/lebinh/ngxtop): strong benchmark for focused CLI troubleshooting. It shows that a small read-only command can be useful immediately, but it is limited to access-log parsing and does not explain config topology, active listeners, or process ownership.
- [nginxconfig.io](https://github.com/digitalocean/nginxconfig.io): strong benchmark for setup-time guidance and explainable config generation. It helps users create new configs, but it does not inspect live VPS state or correlate runtime conflicts.
- [Official NGINX documentation](https://nginx.org/en/docs/) and the [Beginner's Guide](https://nginx.org/en/docs/beginners_guide.html): not a competing product, but the baseline source for config structure, contexts, and reload behavior. This should drive parser assumptions and fixtures, not the end-user UX by itself.

## Recurring Operational Pain Points

- Runtime state is fragmented. Operators have to piece together `nginx.conf`, includes, service state, open ports, process owners, and logs before they can answer a simple question like "what is actually active right now?"
- Existing web UIs lean toward editing and ownership. They are useful once they control the environment, but they are less well suited to safely inspecting an already-problematic VPS without adding another control plane.
- Port conflicts are still an operator problem. Even the more capable UIs document their own listen ports or manual conflict adjustments, which implies that low-level socket collisions still escape the product surface.
- Config generation and traffic monitoring solve adjacent problems, not the core diagnosis gap. Generation tools help before deployment, log tools help after requests arrive, but neither explains why a live box is miswired before traffic flows correctly.
- Nginx itself is flexible and file-structured by design. That flexibility is powerful, but it also means that includes, contexts, and reload boundaries are easy to lose track of on a busy VPS.

## Product Opportunities

- Own the diagnostic gap instead of the gateway role. The clearest opening is a tool that inspects arbitrary existing servers without trying to replace their deployment model.
- Stay read-only at the start. This lowers operational risk and directly matches the user pain around "what is wrong on this VPS right now?"
- Correlate three views in one command: listening ports and owning processes, active Nginx config graph, and human-readable conflict findings.
- Prefer explanation over abstraction. The tool should not hide Nginx concepts; it should translate them into a readable summary that points back to the actual files and sockets.
- Keep the first interface as a CLI. That keeps the blast radius small, works well over SSH-driven operations, and leaves room for a later API or UI that reuses the same inventory model.

## Recommended MVP Capabilities

- Target selection for `local` or `ssh` inspection with only minimal connection settings and an optional `nginx_conf_path` override.
- Read-only port inventory that lists listening sockets together with owning process names and, where available later, service context.
- Nginx config inventory rooted at `nginx.conf`, including include expansion, discovered site files, and normalized `listen` directives.
- Conflict detection for the most common operational failures: port collisions, overlapping Nginx listeners, and missing or unexpected include targets.
- A single `status` command that prints an understandable summary first and then points to the concrete files, ports, and processes behind each finding.
- Fixture-driven tests using representative Nginx layouts so parser and conflict logic can mature without needing a live VPS for every iteration.

## Sources

- Nginx Proxy Manager repository: <https://github.com/NginxProxyManager/nginx-proxy-manager>
- Nginx UI repository: <https://github.com/0xJacky/nginx-ui>
- ngxtop repository: <https://github.com/lebinh/ngxtop>
- nginxconfig.io repository: <https://github.com/digitalocean/nginxconfig.io>
- Official NGINX docs: <https://nginx.org/en/docs/>
- Official NGINX Beginner's Guide: <https://nginx.org/en/docs/beginners_guide.html>
