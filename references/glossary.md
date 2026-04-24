# SAMVIL v3.2 Glossary

Authoritative vocabulary for the harness. Every new doc, skill, and MCP
tool must use these names. `scripts/check-glossary.sh` greps for banned
terms and fails CI.

**Why this matters**: three separate "tier" concepts collided in v3.1
(pipeline tier vs model cost band vs interview intensity). v3.2 renames
them so no two axes share a value name.

---

## Canonical names

| Concept | v3.2 name | Values |
|---------|-----------|--------|
| Whole-pipeline rigor / robustness budget | **`samvil_tier`** | `minimal`, `standard`, `thorough`, `full`, `deep` |
| Model cost band (from Ouroboros) | **`cost_tier`** | `frugal`, `balanced`, `frontier` |
| Interview intensity | **`interview_level`** | `quick`, `normal`, `deep`, `max`, `auto` |
| Stage gate (§3.⑥) | **`gate`** | 8 named gates: `interview_to_seed`, `seed_to_council`, `council_to_design`, `design_to_scaffold`, `scaffold_to_build`, `build_to_qa`, `qa_to_deploy`, `any_to_retro` |
| Evolve convergence checks | **`evolve_checks`** | the 5 checks (similarity / regression / stagnation / stall / metrics-alignment) previously misnamed "evolve gates" |
| Agent persona identity | **`agent_persona`** | 37 personas across 4 tiers (minimal/standard/thorough/full) |
| Agent model-responsibility layer (§3.⑤) | **`model_role`** | `generator`, `reviewer`, `judge`, `repairer`, `researcher`, `compressor` |
| Contract ledger entry (§3.①) | **`claim`** | typed record with status `pending` / `verified` / `rejected` |
| Typed subset of claim | **`claim.type`** | `seed_field_set`, `ac_verdict`, `gate_verdict`, `evolve_decision`, `policy_adoption`, `evidence_posted`, `claim_disputed`, `consensus_verdict`, `migration_applied`, `stagnation_declared` |

## Banned or legacy names

The sweep below is enforced by `scripts/check-glossary.sh`. If a check
flags a false positive (e.g. a historical changelog entry), annotate the
line with `# glossary-allow` to whitelist it.

| Old / banned | Reason | Replacement |
|--------------|--------|-------------|
| `model_tier` | collided with `samvil_tier` | **`cost_tier`** |
| `interview_depth` | collided with `samvil_tier.thorough` | **`interview_level`** |
| `L2 Standard` (interview) | ambiguous vs `samvil_tier.standard` | **`interview_level.normal`** |
| "evolve gates" / "the 5 gates" (in Evolve context) | overloads ⑥ Stage Gate | **`evolve_checks`** |
| "evidence claim" (loose usage) | overloaded "claim" | use **`claim`** only for ledger entries; otherwise say "evidence entry" |
| `agent_tier` (for model cost) | misused v3.1 field | **`cost_tier`** (or `samvil_tier` if you meant pipeline rigor) |

**Note on historical mentions**: changelog entries in `CLAUDE.md` and
`README.md` that describe past v3.1 features may still read "5 gates" in
the Evolve context. These are historical facts about v3.1 and are
whitelisted. New docs must use `evolve_checks`.

## Quick reference — "what do I call this?"

- *"The user picked thorough rigor"* → `samvil_tier=thorough`.
- *"We're routing to the cheap model pool"* → `cost_tier=frugal`.
- *"Interview ran on the deep setting"* → `interview_level=deep`.
- *"Build-worker wrote the code, qa-functional judged it"* → generator
  claim + judge verification, where `model_role[build-worker]=generator`
  and `model_role[qa-functional]=judge`.
- *"The Evolve loop converged"* → all 5 `evolve_checks` passed.
- *"We blocked at the build→QA gate"* → `gate=build_to_qa`,
  `verdict=block`.

## How this file evolves

- New term collisions surface in retro as `observation[severity: high]`.
  Add a row here and to `scripts/check-glossary.sh` in the same commit.
- Renames never happen silently. A rename requires a migration entry in
  `references/migration-v3.1-to-v3.2.md` (or the current live migration
  doc) and a deprecation window unless the term is brand-new in v3.2.
- The glossary is the single source of truth. If `CLAUDE.md` and this
  file disagree, this file wins and `CLAUDE.md` is patched.
