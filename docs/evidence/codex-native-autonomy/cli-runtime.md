# Codex CLI runtime evidence

- Verification level: `blocked_auth`
- Tested commit: `46c550c828f0932f48572e516b5589af41be2ed9`
- Tested tree: `062758516ad907a23b371e333cd6e3dc26ca22a1`
- Codex: `codex-cli 0.144.1`
- Localhost probe: passed and released the ephemeral `127.0.0.1` port.

The real `codex exec` process started in a temporary git project and invoked
SAMVIL MCP `read_chain_marker`. It then failed at the authentication boundary:
`invalid_grant: Invalid refresh token`. The bounded command exited with `124`
after the MCP transport failed to reach a terminal response.

This is not a runtime PASS and must not activate Codex native capability. Re-run
after Codex reauthorization.
