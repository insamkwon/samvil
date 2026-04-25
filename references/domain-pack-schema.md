# Domain Pack Schema

Domain Packs store reusable product-domain guidance outside long skill bodies.
They are deterministic, file-only context sources for Interview, Design, Build,
and QA stages.

## Boundary

Pattern Registry answers implementation questions:

- framework conventions
- recommended libraries
- framework-specific build and QA checks

Domain Packs answer product-domain questions:

- likely users, workflows, and entities
- interview probes and missing-requirement risks
- common data model and domain edge cases
- domain-specific build and QA guidance

## Shape

```json
{
  "pack_id": "saas-dashboard",
  "name": "SaaS Dashboard",
  "domain": "saas",
  "solution_types": ["dashboard", "web-app"],
  "signals": ["metrics", "admin", "dashboard"],
  "stage_focus": ["interview", "design", "build", "qa"],
  "audiences": ["operator", "manager"],
  "core_entities": ["Account", "User", "Metric", "Report"],
  "key_workflows": ["filter metrics", "compare date ranges"],
  "interview_probes": ["Which metrics drive daily decisions?"],
  "design_guidance": ["Separate KPI, filter, chart, and table states."],
  "build_guidance": ["Model empty, loading, and stale data states explicitly."],
  "qa_focus": ["Filters update all dependent widgets."],
  "risk_checks": ["Ambiguous metric definitions cause false confidence."],
  "sample_data": ["7-day revenue series", "empty dataset"],
  "confidence": "high"
}
```

## MCP Tools

- `list_domain_packs(solution_type?, domain?, stage?)`
- `read_domain_pack(pack_id)`
- `render_domain_context(solution_type?, domain?, stage?)`

## Notes

- Packs are matched by `solution_types`, `domain`, `stage_focus`, and signals.
- Pack content should stay concise enough to render into stage prompts.
- Pack context is additive. It should not override explicit user requirements.

## Built-in Packs

- `saas-dashboard`: metrics-heavy dashboard and reporting products.
- `browser-game`: browser-playable games with score/input/restart loops.
- `mobile-habit`: habit, routine, reminder, and streak tracking apps.
