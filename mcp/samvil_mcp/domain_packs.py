"""Domain Packs — reusable product-domain context for SAMVIL v3.6."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


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
