"""Pattern Registry — reusable framework/domain guidance for SAMVIL v3.4."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class PatternEntry:
    pattern_id: str
    name: str
    category: str
    solution_types: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    recommended_libraries: list[str] = field(default_factory=list)
    build_guidance: list[str] = field(default_factory=list)
    qa_focus: list[str] = field(default_factory=list)
    confidence: str = "high"

    def to_dict(self) -> dict:
        return asdict(self)


PATTERNS: tuple[PatternEntry, ...] = (
    PatternEntry(
        pattern_id="nextjs-app-router",
        name="Next.js App Router Web App",
        category="framework",
        solution_types=["web-app", "dashboard"],
        frameworks=["nextjs", "next"],
        signals=["app/", "next.config.ts", "server components", "api routes"],
        recommended_libraries=["lucide-react", "zustand"],
        build_guidance=[
            "Use app router file conventions and keep feature UI near app routes.",
            "Prefer server actions/API routes only when the seed needs backend behavior.",
        ],
        qa_focus=[
            "Route rendering",
            "Client/server boundary correctness",
            "Hydration-sensitive interactions",
        ],
    ),
    PatternEntry(
        pattern_id="vite-react",
        name="Vite React Single Page App",
        category="framework",
        solution_types=["web-app", "dashboard"],
        frameworks=["vite-react", "vite"],
        signals=["vite.config.ts", "src/App.tsx", "src/main.tsx"],
        recommended_libraries=["react", "react-dom", "lucide-react"],
        build_guidance=[
            "Keep the first version client-side unless the seed requires a backend.",
            "Represent small apps with src-level modules before splitting features.",
        ],
        qa_focus=[
            "Main interaction loop",
            "Empty/populated/error states",
            "Responsive layout at mobile and desktop widths",
        ],
    ),
    PatternEntry(
        pattern_id="phaser-game",
        name="Phaser Browser Game",
        category="domain",
        solution_types=["game"],
        frameworks=["phaser"],
        signals=["scenes", "arcade physics", "GameScene", "BootScene"],
        recommended_libraries=["phaser"],
        build_guidance=[
            "Use BootScene, MenuScene, GameScene, and GameOverScene as the base loop.",
            "Generate simple graphics in code unless explicit assets are provided.",
        ],
        qa_focus=[
            "Canvas is nonblank",
            "Main loop starts",
            "Input, collision, score, and restart behavior",
        ],
    ),
    PatternEntry(
        pattern_id="expo-mobile",
        name="Expo Mobile App",
        category="framework",
        solution_types=["mobile-app"],
        frameworks=["expo"],
        signals=["app.json", "expo-router", "native modules"],
        recommended_libraries=["expo-router", "zustand"],
        build_guidance=[
            "Map screens to Expo Router pages and keep navigation explicit.",
            "Add native modules only when the seed names a native capability.",
        ],
        qa_focus=[
            "Navigation paths",
            "Touch target sizing",
            "Native permission and offline states",
        ],
    ),
    PatternEntry(
        pattern_id="dashboard-recharts",
        name="Recharts Dashboard",
        category="domain",
        solution_types=["dashboard"],
        frameworks=["nextjs", "vite-react"],
        signals=["metrics", "charts", "filters", "KPI", "dashboard"],
        recommended_libraries=["recharts", "date-fns", "lucide-react"],
        build_guidance=[
            "Choose chart types from the data shape rather than adding all charts.",
            "Keep KPI, filter, chart, and table components independently testable.",
        ],
        qa_focus=[
            "Chart renders with empty and populated data",
            "Filters update all dependent widgets",
            "Numeric formatting and threshold states",
        ],
    ),
)


def list_patterns(
    *,
    solution_type: str | None = None,
    framework: str | None = None,
    category: str | None = None,
) -> list[PatternEntry]:
    out = list(PATTERNS)
    if solution_type:
        out = [p for p in out if solution_type in p.solution_types]
    if framework:
        out = [p for p in out if framework in p.frameworks]
    if category:
        out = [p for p in out if p.category == category]
    return out


def get_pattern(pattern_id: str) -> PatternEntry | None:
    for pattern in PATTERNS:
        if pattern.pattern_id == pattern_id:
            return pattern
    return None


def render_patterns(patterns: list[PatternEntry]) -> str:
    lines = ["# Pattern Registry", ""]
    for pattern in patterns:
        lines.append(f"## {pattern.pattern_id} — {pattern.name}")
        lines.append(f"- Category: {pattern.category}")
        lines.append(f"- Solution types: {', '.join(pattern.solution_types)}")
        lines.append(f"- Frameworks: {', '.join(pattern.frameworks)}")
        if pattern.recommended_libraries:
            lines.append(f"- Libraries: {', '.join(pattern.recommended_libraries)}")
        if pattern.build_guidance:
            lines.append("- Build guidance:")
            for item in pattern.build_guidance:
                lines.append(f"  - {item}")
        if pattern.qa_focus:
            lines.append("- QA focus:")
            for item in pattern.qa_focus:
                lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
