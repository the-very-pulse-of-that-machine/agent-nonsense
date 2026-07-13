# Security Policy

## Scope

Agent Nonsense is a local simulator, not a hardened public inference gateway. It has no authentication by default and should bind to `127.0.0.1` unless it is placed behind an authenticated reverse proxy.

File tools are restricted to the configured sandbox. Path traversal, symlink escape, excessive writes, malformed JSON, stream disconnects, and accidental network access are security-sensitive areas.

## Reporting a vulnerability

Do not open a public issue for an unpatched vulnerability. Use the repository's private security advisory feature and include reproduction steps, affected versions, expected impact, and any proposed mitigation.

## Supported versions

Until the first stable release, only the latest `0.x` release receives security fixes.

## Deployment guidance

- Keep the default loopback bind address.
- Use a dedicated sandbox directory with minimal permissions.
- Do not point the sandbox at a source repository containing secrets.
- Do not enable `--native-tools` unless the client implements the complete tool-result handshake.
- Treat preset files as untrusted local input.
