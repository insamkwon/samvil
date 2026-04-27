"""Domain Packs — reusable product-domain context for SAMVIL v3.6."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DomainPack:
    pack_id: str
    name: str
    domain: str
    solution_types: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    stage_focus: list[str] = field(default_factory=list)
    audiences: list[str] = field(default_factory=list)
    core_entities: list[str] = field(default_factory=list)
    key_workflows: list[str] = field(default_factory=list)
    interview_probes: list[str] = field(default_factory=list)
    design_guidance: list[str] = field(default_factory=list)
    build_guidance: list[str] = field(default_factory=list)
    qa_focus: list[str] = field(default_factory=list)
    risk_checks: list[str] = field(default_factory=list)
    sample_data: list[str] = field(default_factory=list)
    confidence: str = "high"

    def to_dict(self) -> dict:
        return asdict(self)


DOMAIN_PACKS: tuple[DomainPack, ...] = (
    DomainPack(
        pack_id="saas-dashboard",
        name="SaaS Dashboard",
        domain="saas",
        solution_types=["dashboard", "web-app"],
        signals=["metrics", "admin", "dashboard", "reporting", "analytics"],
        stage_focus=["interview", "design", "build", "qa"],
        audiences=["operator", "manager", "admin"],
        core_entities=["Account", "User", "Metric", "Report", "DateRange", "Segment"],
        key_workflows=[
            "Filter metrics by date range and segment.",
            "Compare KPI changes and inspect the underlying table rows.",
            "Export or share a filtered report.",
        ],
        interview_probes=[
            "Which metrics drive a daily decision, and who owns that decision?",
            "What date ranges, segments, and thresholds must be trusted?",
            "What should happen when data is empty, delayed, or partially wrong?",
        ],
        design_guidance=[
            "Separate KPI, filter, chart, and table states so changes are traceable.",
            "Make metric definitions visible enough to prevent ambiguous interpretation.",
            "Prioritize dense scanning over marketing-style presentation.",
        ],
        build_guidance=[
            "Model empty, loading, stale, and error states for each data surface.",
            "Keep filtering logic centralized so KPIs, charts, and tables stay in sync.",
            "Use deterministic fixture data with at least one threshold crossing.",
        ],
        qa_focus=[
            "Filters update all dependent widgets.",
            "Numbers format consistently across KPI cards, charts, and tables.",
            "Empty and delayed-data states are understandable.",
        ],
        risk_checks=[
            "Ambiguous metric definitions cause false confidence.",
            "A chart can look correct while the table or KPI uses a different filter.",
            "Role-specific access may hide data that summaries still count.",
        ],
        sample_data=["7-day revenue series", "empty dataset", "threshold breach"],
    ),
    DomainPack(
        pack_id="browser-game",
        name="Browser Game",
        domain="game",
        solution_types=["game"],
        signals=["score", "level", "player", "collision", "restart"],
        stage_focus=["interview", "design", "build", "qa"],
        audiences=["player"],
        core_entities=["Player", "Level", "Enemy", "Collectible", "Score", "GameState"],
        key_workflows=[
            "Start a session, learn the controls, and enter the main loop.",
            "Win, lose, pause, restart, and recover from game-over.",
            "Track score, health, timer, or progress with clear feedback.",
        ],
        interview_probes=[
            "What is the core 10-second loop the player repeats?",
            "What makes success or failure obvious without reading instructions?",
            "Should the game favor precision, speed, planning, or discovery?",
        ],
        design_guidance=[
            "Define the main loop before adding secondary systems.",
            "Keep input, collision, scoring, and restart behavior explicit.",
            "Use immediate visual feedback for damage, collection, and completion.",
        ],
        build_guidance=[
            "Create a deterministic initial scene and avoid asset dependencies unless provided.",
            "Keep update-loop state small and inspectable.",
            "Add restart and game-over paths in the first playable version.",
        ],
        qa_focus=[
            "Canvas or game surface is nonblank.",
            "Input changes player state.",
            "Collision, scoring, win/loss, and restart paths work.",
        ],
        risk_checks=[
            "The game can render while the loop is not actually interactive.",
            "Restart often leaves old timers or collision objects alive.",
            "Difficulty can be impossible on mobile or keyboard-only controls.",
        ],
        sample_data=["level one fixture", "score threshold", "game-over state"],
    ),
    DomainPack(
        pack_id="mobile-habit",
        name="Mobile Habit Tracker",
        domain="productivity",
        solution_types=["mobile-app", "web-app"],
        signals=["habit", "streak", "reminder", "check-in", "routine"],
        stage_focus=["interview", "design", "build", "qa"],
        audiences=["individual user"],
        core_entities=["Habit", "CheckIn", "Streak", "Reminder", "Goal", "Schedule"],
        key_workflows=[
            "Create a habit and define the schedule.",
            "Check in, miss a day, recover, and inspect streak history.",
            "Edit reminders or pause a habit without losing history.",
        ],
        interview_probes=[
            "What behavior should become easier, and what usually breaks the routine?",
            "How strict should streaks be when the user misses, travels, or pauses?",
            "What notification or reminder behavior would feel helpful rather than noisy?",
        ],
        design_guidance=[
            "Treat missed days, paused habits, and edited schedules as first-class states.",
            "Make today's action fast while keeping history review one step away.",
            "Avoid guilt-heavy copy when a habit is missed.",
        ],
        build_guidance=[
            "Represent dates in a single canonical format and localize only at display time.",
            "Keep check-in mutation idempotent for the same habit/date pair.",
            "Use fixture habits that cover daily, weekly, paused, and missed states.",
        ],
        qa_focus=[
            "Check-in toggles are idempotent.",
            "Streaks survive missed, paused, and edited schedule scenarios.",
            "Reminder settings and timezone-sensitive dates display correctly.",
        ],
        risk_checks=[
            "Timezone boundaries can corrupt streaks.",
            "Editing a habit can accidentally rewrite historical check-ins.",
            "Notifications can become spammy without snooze or pause behavior.",
        ],
        sample_data=["daily habit", "weekly habit", "paused habit", "missed streak"],
    ),
    DomainPack(
        pack_id="game-phaser",
        name="Phaser Game",
        domain="game",
        solution_types=["game"],
        signals=[
            "phaser", "sprite", "scene", "physics", "tilemap", "animation",
            "arcade", "tween", "camera", "input", "particle", "audio",
        ],
        stage_focus=["interview", "design", "build", "qa"],
        audiences=["player"],
        core_entities=[
            "Scene", "Sprite", "Tilemap", "PhysicsGroup", "Tween",
            "GameState", "Camera", "ParticleEmitter", "AudioManager",
            "InputHandler", "HUD", "SaveSlot",
        ],
        key_workflows=[
            "Scene lifecycle: preload assets, create objects, update loop.",
            "Player input mapping (keyboard/touch/gamepad) to sprite movement and actions.",
            "Physics collision groups: player vs enemies, player vs collectibles, player vs world bounds.",
            "Scene transitions with data passing (score, inventory, level config).",
            "Save/load game state to localStorage with versioned schema.",
            "Pause/resume with overlay menu and state preservation.",
        ],
        interview_probes=[
            "Is this arcade physics (bounding boxes) or matter.js (complex shapes)?",
            "How many scenes: single-screen, scrolling world, or multi-level map?",
            "What assets are available: spritesheet, tilemap (Tiled), audio, or generated shapes?",
            "Does the game need save/load between sessions, or is each run independent?",
            "Mobile touch controls, desktop keyboard, or both?",
            "Are there progression systems (XP, upgrades, unlocks) or is each run standalone?",
        ],
        design_guidance=[
            "Design scene graph first: BootScene → MainMenuScene → GameScene → GameOverScene.",
            "Separate game logic from rendering: Scene delegates to systems (MovementSystem, CollisionSystem, ScoringSystem).",
            "Use Phaser's built-in state machine for scene transitions, not custom routing.",
            "Plan the HUD as a separate container overlaid on the game canvas.",
            "Define a GameConfig object with physics defaults, canvas size, and input mappings.",
        ],
        build_guidance=[
            "Use Phaser.Scene class for each distinct game state (boot, menu, play, gameover).",
            "Preload all assets in BootScene with loading bar; never load mid-gameplay.",
            "Use Arcade.Physics for most 2D games; only Matter for complex shapes.",
            "Implement restart by calling scene.restart() or scene.start('GameScene', config).",
            "Keep sprite creation in factory functions for consistent physics body sizing.",
            "Use Phaser tweens for UI animations, not manual interpolation.",
            "Store save data as JSON in localStorage with a version field for migration.",
        ],
        qa_focus=[
            "Game canvas renders without errors on first load.",
            "All scene transitions complete without black screen or stuck state.",
            "Player input (keyboard + touch) moves sprite in expected direction.",
            "Collision detection triggers correct responses (damage, collection, boundary).",
            "Restart returns to identical initial state (no leaked objects or timers).",
            "Save/load round-trip preserves score, inventory, and level progress.",
            "Game runs at 60fps on target device; no frame drops during physics-heavy scenes.",
        ],
        risk_checks=[
            "Phaser scenes can stack if scene.start is called without scene.stop.",
            "Physics bodies created after preload may miss collision setup.",
            "Sprite sheet frame sizing mismatches cause invisible or distorted sprites.",
            "Touch input on mobile may conflict with browser scroll/zoom gestures.",
            "Save data corruption if localStorage quota is exceeded.",
        ],
        sample_data=[
            "player spritesheet (3-frame walk cycle)",
            "single-level tilemap with 3 enemy spawns",
            "game-over state with score 500",
            "save file with level 3 and 2 power-ups",
        ],
    ),
    DomainPack(
        pack_id="webapp-enterprise",
        name="Enterprise Web App",
        domain="enterprise",
        solution_types=["web-app"],
        signals=[
            "auth", "role", "permission", "organization", "tenant",
            "audit", "admin panel", "settings", "invite", "monorepo",
            "api", "dashboard", "team", "workspace",
        ],
        stage_focus=["interview", "design", "build", "qa"],
        audiences=["admin", "team lead", "member", "viewer"],
        core_entities=[
            "Organization", "User", "Role", "Permission", "Team",
            "Workspace", "Invitation", "AuditLog", "Setting", "ApiKey",
            "Webhook", "Notification", "BillingAccount",
        ],
        key_workflows=[
            "Sign up, create organization, invite team members via email.",
            "Role-based access control: assign roles, check permissions per resource.",
            "Multi-tenant data isolation: each org sees only its own data.",
            "Audit trail: log who did what, when, with before/after snapshots.",
            "Settings management: org-level and user-level preferences.",
            "API key management: create, rotate, revoke keys with scoped permissions.",
            "Notification preferences: email, in-app, webhook delivery channels.",
        ],
        interview_probes=[
            "How many user roles are needed, and what resources does each role access?",
            "Is this single-tenant (one org) or multi-tenant (many orgs on same instance)?",
            "What events need audit logging: all mutations or only high-sensitivity ones?",
            "How are team members invited: email link, magic link, or admin manual add?",
            "Is there a billing or subscription component, or is access purely role-based?",
            "What third-party integrations are needed: SSO (SAML/OIDC), webhooks, or APIs?",
        ],
        design_guidance=[
            "Design the permission model early: RBAC (roles) or ABAC (attributes) or hybrid.",
            "Separate auth concerns from business logic using middleware/guards.",
            "Plan tenant isolation: shared database with tenant_id or separate schemas.",
            "Design the API surface first, then build the frontend against it.",
            "Use a monorepo structure: shared types, API client, and UI packages.",
            "Plan for soft deletes and data retention policies from the start.",
        ],
        build_guidance=[
            "Implement auth with industry-standard libraries (NextAuth, Supabase Auth, etc.).",
            "Use a permission guard pattern: middleware checks role/permission before handler.",
            "Implement tenant context as a request-scoped value, not a global.",
            "Generate API types: run `npx openapi-typescript spec.yaml -o packages/types/src/api.d.ts`. Use a typed fetch wrapper that accepts generated paths as generics.",
            "Use database transactions for operations that span multiple tables.",
            "Add structured logging with correlation IDs for request tracing.",
            "Seed script should create: 1 org, 3 users (admin/member/viewer), sample data.",
            "BFF pattern: create apps/web/app/api/[...path]/route.ts that proxies to the backend service. Use Next.js rewrites (next.config.mjs) or direct fetch with BACKEND_URL from env.",
            "Turborepo root: apps/web (Next.js), apps/api (Express/Hono), packages/ui (shadcn), packages/types (shared TS), packages/db (Prisma). Root package.json has `turbo` workspaces.",
            "SSO options — NextAuth.js (self-hosted, 50+ providers, free), Clerk (managed, built-in UI, pay-per-MAU), Supabase Auth (PostgreSQL-native, free tier). Choose NextAuth for full control, Clerk for fastest integration.",
        ],
        qa_focus=[
            "Unauthenticated requests are redirected to login (no data leakage).",
            "Role-based access: each role sees only permitted resources and actions.",
            "Multi-tenant isolation: org A cannot access org B's data via any API path.",
            "Invite flow: create invitation, accept invitation, assign correct role.",
            "Audit log captures mutations with user, timestamp, resource, and changes.",
            "Settings save/load correctly at org and user levels.",
            "API key authentication works alongside session authentication.",
        ],
        risk_checks=[
            "Permission checks can be bypassed by directly calling API endpoints.",
            "Tenant isolation breaks when queries forget the tenant_id filter.",
            "Audit logs can balloon in size and slow writes on high-traffic tables.",
            "Invitation tokens can be guessed or reused after acceptance.",
            "Soft-deleted data can still be accessed via direct ID lookups.",
        ],
        sample_data=[
            "org with 3 users (admin/member/viewer)",
            "permission matrix (4 roles × 8 resources)",
            "audit log entry (user updated setting)",
            "pending invitation with expiry",
        ],
    ),
)


def list_domain_packs(
    *,
    solution_type: str | None = None,
    domain: str | None = None,
    stage: str | None = None,
) -> list[DomainPack]:
    out = list(DOMAIN_PACKS)
    if solution_type:
        out = [pack for pack in out if solution_type in pack.solution_types]
    if domain:
        out = [pack for pack in out if pack.domain == domain]
    if stage:
        out = [pack for pack in out if stage in pack.stage_focus]
    return out


def get_domain_pack(pack_id: str) -> DomainPack | None:
    for pack in DOMAIN_PACKS:
        if pack.pack_id == pack_id:
            return pack
    return None


def match_domain_packs(seed: dict[str, Any]) -> list[dict[str, Any]]:
    """Rank domain packs from deterministic seed fields and text signals."""
    solution_type = str(seed.get("solution_type") or "").lower()
    domain = str(seed.get("domain") or seed.get("app_domain") or "").lower()
    text = _seed_text(seed)

    matches: list[dict[str, Any]] = []
    for pack in DOMAIN_PACKS:
        score = 0
        reasons: list[str] = []

        if solution_type and solution_type in pack.solution_types:
            score += 5
            reasons.append(f"solution_type:{solution_type}")
        if domain and domain == pack.domain:
            score += 4
            reasons.append(f"domain:{domain}")

        signal_hits = [signal for signal in pack.signals if signal.lower() in text]
        if signal_hits:
            score += min(5, len(signal_hits))
            reasons.append("signals:" + ",".join(signal_hits[:5]))

        entity_hits = [entity for entity in pack.core_entities if entity.lower() in text]
        if entity_hits:
            score += min(3, len(entity_hits))
            reasons.append("entities:" + ",".join(entity_hits[:3]))

        if score <= 0:
            continue
        matches.append({
            "pack_id": pack.pack_id,
            "name": pack.name,
            "domain": pack.domain,
            "score": score,
            "confidence": _confidence(score),
            "reasons": reasons,
        })

    return sorted(matches, key=lambda row: (-int(row["score"]), str(row["pack_id"])))


def render_domain_packs(packs: list[DomainPack], *, stage: str | None = None) -> str:
    lines = ["# Domain Packs", ""]
    for pack in packs:
        lines.append(f"## {pack.pack_id} — {pack.name}")
        lines.append(f"- Domain: {pack.domain}")
        lines.append(f"- Solution types: {', '.join(pack.solution_types)}")
        lines.append(f"- Stage focus: {', '.join(pack.stage_focus)}")
        if pack.audiences:
            lines.append(f"- Audiences: {', '.join(pack.audiences)}")
        if pack.core_entities:
            lines.append(f"- Core entities: {', '.join(pack.core_entities)}")
        if pack.key_workflows:
            lines.append("- Key workflows:")
            for item in pack.key_workflows:
                lines.append(f"  - {item}")
        if stage in (None, "interview") and pack.interview_probes:
            lines.append("- Interview probes:")
            for item in pack.interview_probes:
                lines.append(f"  - {item}")
        if stage in (None, "design") and pack.design_guidance:
            lines.append("- Design guidance:")
            for item in pack.design_guidance:
                lines.append(f"  - {item}")
        if stage in (None, "build") and pack.build_guidance:
            lines.append("- Build guidance:")
            for item in pack.build_guidance:
                lines.append(f"  - {item}")
        if stage in (None, "qa") and pack.qa_focus:
            lines.append("- QA focus:")
            for item in pack.qa_focus:
                lines.append(f"  - {item}")
        if pack.risk_checks:
            lines.append("- Risk checks:")
            for item in pack.risk_checks:
                lines.append(f"  - {item}")
        if pack.sample_data:
            lines.append(f"- Sample data: {', '.join(pack.sample_data)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _seed_text(seed: dict[str, Any]) -> str:
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(seed)
    return " ".join(parts).lower()


def _confidence(score: int) -> str:
    if score >= 7:
        return "high"
    if score >= 3:
        return "medium"
    return "low"
