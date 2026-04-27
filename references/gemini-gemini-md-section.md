# SAMVIL GEMINI.md Section (Gemini CLI)

Add this content to your project's GEMINI.md or AGENTS.md file.
SAMVIL MCP server must be configured in settings.json mcpServers.

---

## SAMVIL Pipeline

SAMVIL is an AI vibe-coding harness that generates full applications from a one-line prompt.
Pipeline stages: Interview → Seed → Design → Scaffold → Build → QA → Deploy → Evolve → Retro

### Starting the pipeline

Run: `/samvil`

### Stage chain

Each stage reads `.samvil/next-skill.json` to find the next stage.
Run `/samvil-<stage-name>` to execute a specific stage.

Available stages:
- `/samvil` — Orchestrator (health check, tier selection, chain start)
- `/samvil-interview` — Engineering interview
- `/samvil-pm-interview` — PM interview
- `/samvil-seed` — Generate seed.json
- `/samvil-council` — Council review
- `/samvil-design` — Generate blueprint
- `/samvil-scaffold` — Create project skeleton
- `/samvil-build` — Build features
- `/samvil-qa` — QA verification
- `/samvil-deploy` — Deploy application
- `/samvil-evolve` — Evolve seed
- `/samvil-retro` — Retrospective
- `/samvil-analyze` — Analyze existing project
- `/samvil-doctor` — Environment diagnostic
- `/samvil-update` — Update SAMVIL

### Chain markers

SAMVIL uses `.samvil/next-skill.json` to track pipeline progress.
After each stage completes, it writes the next stage info to this file.
The next invocation reads it and continues automatically.

### MCP server setup

Add to your settings.json:

```json
{
  "mcpServers": {
    "samvil": {
      "command": "python3",
      "args": ["-m", "samvil_mcp.server"]
    }
  }
}
```
