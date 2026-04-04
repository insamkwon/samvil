# Evolve Protocol

> Improve the seed through evaluation feedback. Wonder → Reflect → New Seed → Verify.

## Pipeline

```
QA Result → Wonder ("what was lacking?") → Reflect ("how to improve?") → Seed v(N+1)
  → Validate → User Approve → Rebuild (changed parts) → Re-QA → Convergence Check
                                                                    ↓
                                                              converged? → Stop
                                                              not yet? → Another cycle
```

## Convergence

- **Metric**: Jaccard similarity between seed v(N) and v(N+1)
- **Threshold**: ≥ 0.95 = converged (seeds are nearly identical = no more improvements)
- **Max iterations**: 30 (hard cap)
- **Trend tracking**: converging / diverging / stable

## Evolution Rules

1. **Preserve core identity**: name, mode, core_experience must not change
2. **Max 2 new features per evolution**: prevents scope explosion
3. **Version increments by 1**: v1 → v2 → v3
4. **User approves every change**: no auto-modification
5. **Rebuild only what changed**: don't re-scaffold from scratch

## Wonder Agent Focus

- What surprised us during build?
- What did QA find that the seed didn't anticipate?
- Which assumptions proved wrong?
- What user expectations are missing?

## Reflect Agent Focus

- Which wonder discoveries are most impactful?
- What's the minimal seed change that addresses them?
- Is the change reversible?
- Does it contradict existing decisions?

## MCP Tools

| Tool | Purpose |
|------|---------|
| `get_evolve_context` | Gather context with convergence trend |
| `compare_seeds` | Similarity between two versions |
| `check_convergence` | Is the evolution converging? |
| `validate_evolved_seed` | Check evolution rules |
| `save_seed_version` | Persist new version |
| `get_seed_history` | All versions for comparison |
