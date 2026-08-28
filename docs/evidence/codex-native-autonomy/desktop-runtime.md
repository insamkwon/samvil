# Codex Desktop MCP idempotency evidence

- Verification level: `manual_desktop`
- Repository HEAD present during observation: `b2709e0e096fa8a9f86591d250dc6b3c9289b668`
- Repository tree present during observation: `57c565c1345752414e3e40da880b18132f489a9c`
- Runtime provenance: `unbound_stale_process`
- Display name: `codex-desktop-display-name-final-idempotency`
- Canonical project root: `/private/tmp/samvil-codex-desktop-mcp-final-7w1pNb`
- Session: `397dfdd3e6a4`
- Fixed transition id: `codex-desktop-live-retry-b2709e0-397dfdd3e6a4`

The actual Codex Desktop MCP tools executed `get_stage_envelope`, `begin_stage`,
and two `commit_stage_transition` calls with the same transition id. Both calls
returned the same committed receipt and event id. SQLite contained exactly one
matching event, while project-local `events.jsonl` and `claims.jsonl` each
contained one line.

This passes the scoped manual idempotency check. It is not a current-HEAD runtime
parity receipt: the connected Desktop MCP process returned a relative instruction
path even though the checked-out controller requires an absolute path, proving the
long-lived process had not reloaded the latest code. Codex Desktop must be
restarted or reopened and the smoke repeated before binding runtime behavior to
this commit/tree.

The literal repository path `$CODEX_HOME/` and the real Codex profile were not
modified during this verification.
