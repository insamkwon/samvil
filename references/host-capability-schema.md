# Host Capability Schema (v3.3+)

HostCapability declares runtime differences as data. SAMVIL skills should ask
what the host can do instead of assuming Claude Code behavior.

## Shape

```json
{
  "name": "codex_cli",
  "skill_invocation": "manual",
  "parallel_agents": false,
  "mcp_tools": true,
  "file_marker_handoff": true,
  "browser_preview": true,
  "native_task_update": false,
  "notes": ["Prefer MCP tools plus explicit file markers."],
  "chain_via": "file_marker"
}
```

## Known Hosts

| Host | Chain via | Notes |
|---|---|---|
| `claude_code` | `skill_tool` | Can directly invoke the next SAMVIL skill |
| `codex_cli` | `file_marker` | Uses `.samvil/next-skill.json` for portable continuation |
| `opencode` | `file_marker` | Avoid Claude-specific assumptions |
| `generic` | `file_marker` | Fallback for unknown hosts |

Unknown host names resolve to `generic`.

## Chain Strategies

`skill_tool`:

- use when the runtime has a native skill invocation mechanism
- current known host: `claude_code`

`file_marker`:

- write `.samvil/next-skill.json`
- next session or host reads the marker and continues manually
- preferred portable fallback for Codex/OpenCode/generic

Example marker:

```json
{
  "next_skill": "samvil-council",
  "reason": "council required for selected tier",
  "from_stage": "seed"
}
```

## MCP Tools

- `resolve_host_capability(host_name?)`
- `host_chain_strategy(host_name?)`

Both tools are read-only and return JSON.

## Seed PoC

`skills/samvil-seed/SKILL.md` is the first ultra-thin PoC:

- active skill body is under 90 lines
- full rules are preserved in `skills/samvil-seed/SKILL.legacy.md`
- chaining goes through `host_chain_strategy`
- non-skill-tool hosts use `.samvil/next-skill.json`

This proves the Phase 2 mass-migration shape without deleting the existing seed
knowledge.
