# Skill Migration Checklist

Use this checklist when converting a legacy SAMVIL stage skill into a
host-aware ultra-thin entry.

## Target Shape

- Active `SKILL.md` stays under 120 lines.
- Original body is preserved as `SKILL.legacy.md` in the same skill directory.
- Active body delegates domain rules, schemas, and examples to the legacy file.
- Active body owns only orchestration: inputs, MCP gates, file outputs, approval,
  stage completion, and host-specific chaining.

## Required Sections

1. **Inputs**: list the project files and host fields the skill reads.
2. **MCP Gate**: call `get_orchestration_state` and `stage_can_proceed`.
3. **Host Capability**: call `resolve_host_capability` and
   `host_chain_strategy`.
4. **Build Work**: point to `SKILL.legacy.md` for detailed construction rules.
5. **After Approval**: write the one stage-owned output file and call
   `complete_stage`.
6. **Chain**: use `skill_tool` where available, otherwise write
   `.samvil/next-skill.json`.
7. **Invariants**: name the stage authority file and the only writer.

## MCP Preferences

- Prefer manifest/decision-log MCP tools over long ad-hoc scans.
- `complete_stage(session_id, stage, "pass")` is the stage exit path.
- `save_event` is allowed for best-effort entry/progress events.
- If MCP is unavailable, continue from files and state degraded orchestration.

## Validation

- Run `python3 scripts/skill-thinness-report.py --fail-over 120`.
- Run `python3 scripts/check-skill-wiring.py`.
- Run `bash scripts/pre-commit-check.sh` before claiming done.
