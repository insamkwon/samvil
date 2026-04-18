"""PATH Routing for SAMVIL interviews (v2.4.0, Ouroboros #01 흡수).

Routes each interview question to one of 5 paths:
  - PATH 1a: auto_confirm  — AI auto-answers from manifest/config (high-confidence)
  - PATH 1b: code_confirm  — AI proposes answer, user confirms Y/N
  - PATH 2:  user          — direct user judgment required
  - PATH 3:  hybrid        — code + user decision
  - PATH 4:  research      — AI searches web, user confirms (future, v2.4.1)

Core principle (v3 P2): Description (facts) = AI, Prescription (decisions) = user.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

# ── Keyword sets for routing heuristics ────────────────────────

# Questions answerable from manifest files
MANIFEST_KEYWORDS = {
    "framework": ["framework", "프레임워크", "react", "vue", "next", "svelte"],
    "language": ["python version", "node version", "typescript", "파이썬 버전"],
    "package_manager": ["npm", "pnpm", "yarn", "uv", "pipx", "package manager", "패키지 매니저"],
    "database": ["database", "db", "postgresql", "mysql", "sqlite", "mongodb", "데이터베이스"],
    "auth_existing": ["기존 auth", "기존 인증", "existing auth", "auth method used"],
}

# Decision keywords — require user judgment
DECISION_KEYWORDS = [
    "should we", "which should", "prefer",
    "결정", "선택", "원하는", "해야", "어떤 걸", "뭐로",
    "goal", "목표", "비전", "우선순위", "why",
    "acceptance criteria", "수락 기준", "AC",
    "business", "비즈니스", "전략",
]

# Research keywords — external world
RESEARCH_KEYWORDS = [
    "rate limit", "pricing", "가격", "최신 버전", "latest version",
    "support", "호환", "compatible", "보안 권고",
    "업계 표준", "industry standard", "best practice",
    "stripe", "aws", "google cloud", "openai api",  # external services
]


# ── Manifest scanning ──────────────────────────────────────────


def scan_manifest(project_path: str) -> dict:
    """Scan common manifest files to extract facts.

    Args:
        project_path: Absolute path to project root.

    Returns:
        Dict of {fact_name: value}. Empty if not brownfield.
    """
    facts: dict = {"detected": False, "source_files": []}
    root = Path(project_path)
    if not root.exists():
        return facts

    # package.json — Node.js / JavaScript
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            facts["detected"] = True
            facts["source_files"].append("package.json")
            facts["name"] = data.get("name", "")

            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            # Framework detection
            if "next" in deps:
                facts["framework"] = "Next.js"
                facts["framework_version"] = deps["next"]
            elif "react" in deps:
                facts["framework"] = "React"
                facts["framework_version"] = deps["react"]
            elif "vue" in deps:
                facts["framework"] = "Vue"
                facts["framework_version"] = deps["vue"]
            elif "svelte" in deps:
                facts["framework"] = "Svelte"
                facts["framework_version"] = deps["svelte"]
            elif "astro" in deps:
                facts["framework"] = "Astro"
                facts["framework_version"] = deps["astro"]
            elif "expo" in deps:
                facts["framework"] = "Expo (React Native)"
                facts["framework_version"] = deps["expo"]

            # Styling
            if "tailwindcss" in deps:
                facts["styling"] = "Tailwind CSS"
            if "@shadcn/ui" in deps or "shadcn" in str(deps):
                facts["ui_lib"] = "shadcn/ui"

            # ORM / DB
            if "prisma" in deps or "@prisma/client" in deps:
                facts["orm"] = "Prisma"
            if "drizzle-orm" in deps:
                facts["orm"] = "Drizzle"

            # Type system
            if "typescript" in deps:
                facts["language"] = "TypeScript"
            else:
                facts["language"] = "JavaScript"

            # Package manager
            if (root / "pnpm-lock.yaml").exists():
                facts["package_manager"] = "pnpm"
            elif (root / "yarn.lock").exists():
                facts["package_manager"] = "yarn"
            elif (root / "package-lock.json").exists():
                facts["package_manager"] = "npm"

        except (json.JSONDecodeError, OSError):
            pass

    # pyproject.toml — Python
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            facts["detected"] = True
            facts["source_files"].append("pyproject.toml")

            # Very simple toml parse (Python version + framework hints)
            match = re.search(r'python\s*=\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
            if match:
                facts["python_version"] = match.group(1)

            if "fastapi" in content.lower():
                facts["framework"] = "FastAPI"
            elif "django" in content.lower():
                facts["framework"] = "Django"
            elif "flask" in content.lower():
                facts["framework"] = "Flask"

            facts["language"] = "Python"

            if (root / "uv.lock").exists():
                facts["package_manager"] = "uv"
            elif (root / "poetry.lock").exists():
                facts["package_manager"] = "poetry"

        except OSError:
            pass

    # Prisma schema — DB detection
    prisma_schema = root / "prisma" / "schema.prisma"
    if prisma_schema.exists():
        try:
            content = prisma_schema.read_text()
            facts["source_files"].append("prisma/schema.prisma")
            if "postgresql" in content:
                facts["database"] = "PostgreSQL"
            elif "mysql" in content:
                facts["database"] = "MySQL"
            elif "sqlite" in content:
                facts["database"] = "SQLite"
            elif "mongodb" in content:
                facts["database"] = "MongoDB"
        except OSError:
            pass

    # Auth hints — check for common auth files
    for auth_path in ["src/auth", "src/lib/auth.ts", "app/api/auth", "pages/api/auth"]:
        if (root / auth_path).exists():
            facts["source_files"].append(f"{auth_path}")
            if "next-auth" in str(facts.get("framework", "")).lower() or "NextAuth" in (root / "package.json").read_text() if (root / "package.json").exists() else False:
                facts["auth"] = "NextAuth.js"
            else:
                facts["auth"] = "custom (found auth files)"
            break

    return facts


# ── Routing logic ──────────────────────────────────────────────


RoutingPath = Literal[
    "auto_confirm",
    "code_confirm",
    "user",
    "hybrid",
    "research",
    "forced_user",  # Rhythm Guard forced
]


def detect_routing_path(
    question: str,
    manifest_facts: dict | None = None,
    force_user: bool = False,
) -> dict:
    """Detect which path a question should route to.

    Args:
        question: The interview question text.
        manifest_facts: Facts from scan_manifest() (None = greenfield).
        force_user: If True (Rhythm Guard active), always route to user.

    Returns:
        Dict with path, rationale, and optional auto_answer fields.
    """
    manifest_facts = manifest_facts or {}
    q_lower = question.lower()

    # ── Rhythm Guard override (highest priority) ──────────────
    if force_user:
        return {
            "path": "forced_user",
            "rationale": "Rhythm Guard: 3 consecutive AI answers → force user input",
            "auto_answer": None,
            "icon": "💬",
        }

    # ── Decision keywords → PATH 2 (user) ──────────────────────
    if any(kw in q_lower for kw in DECISION_KEYWORDS):
        return {
            "path": "user",
            "rationale": "Decision language detected — requires user judgment",
            "auto_answer": None,
            "icon": "💬",
        }

    # ── Research keywords → PATH 4 (research) ──────────────────
    if any(kw in q_lower for kw in RESEARCH_KEYWORDS):
        return {
            "path": "research",
            "rationale": "External knowledge (rate limits, pricing, versions) — web search recommended",
            "auto_answer": None,
            "icon": "🔍",
        }

    # ── Manifest-answerable → PATH 1a (auto_confirm) ──────────
    if manifest_facts.get("detected"):
        # Framework question
        if any(kw in q_lower for kw in MANIFEST_KEYWORDS["framework"]):
            if manifest_facts.get("framework"):
                return {
                    "path": "auto_confirm",
                    "rationale": f"Framework from manifest",
                    "auto_answer": (
                        f"[from-code][auto-confirmed] {manifest_facts['framework']} "
                        f"{manifest_facts.get('framework_version', '')} "
                        f"({', '.join(manifest_facts.get('source_files', []))})"
                    ).strip(),
                    "icon": "ℹ️",
                }

        # Language question
        if any(kw in q_lower for kw in MANIFEST_KEYWORDS["language"]):
            if manifest_facts.get("language"):
                answer_parts = [manifest_facts["language"]]
                if manifest_facts.get("python_version"):
                    answer_parts.append(f"Python {manifest_facts['python_version']}")
                return {
                    "path": "auto_confirm",
                    "rationale": "Language from manifest",
                    "auto_answer": (
                        f"[from-code][auto-confirmed] {', '.join(answer_parts)} "
                        f"({', '.join(manifest_facts.get('source_files', []))})"
                    ),
                    "icon": "ℹ️",
                }

        # Package manager
        if any(kw in q_lower for kw in MANIFEST_KEYWORDS["package_manager"]):
            if manifest_facts.get("package_manager"):
                return {
                    "path": "auto_confirm",
                    "rationale": "Package manager from lockfile",
                    "auto_answer": (
                        f"[from-code][auto-confirmed] {manifest_facts['package_manager']} "
                        f"(lockfile present)"
                    ),
                    "icon": "ℹ️",
                }

        # Database
        if any(kw in q_lower for kw in MANIFEST_KEYWORDS["database"]):
            if manifest_facts.get("database"):
                return {
                    "path": "code_confirm",
                    "rationale": "Database inferred from Prisma schema — confirm with user",
                    "auto_answer": (
                        f"[from-code] {manifest_facts['database']} "
                        f"(prisma/schema.prisma)"
                    ),
                    "icon": "ℹ️",
                }

        # Existing auth
        if any(kw in q_lower for kw in MANIFEST_KEYWORDS["auth_existing"]):
            if manifest_facts.get("auth"):
                return {
                    "path": "code_confirm",
                    "rationale": "Auth inferred from code — confirm with user",
                    "auto_answer": f"[from-code] {manifest_facts['auth']}",
                    "icon": "ℹ️",
                }

    # ── Default: PATH 2 (user) ─────────────────────────────────
    # Conservative — when in doubt, ask user
    return {
        "path": "user",
        "rationale": "No manifest match — defaulting to user judgment",
        "auto_answer": None,
        "icon": "💬",
    }


# ── Answer prefix helper ───────────────────────────────────────


def extract_answer_source(answer: str) -> str:
    """Extract the source prefix from a prefixed answer string.

    Recognized prefixes (in order):
      [from-code][auto-confirmed] → 'from-code-auto'
      [from-code] → 'from-code'
      [from-user][correction] → 'from-user-correction'
      [from-user] → 'from-user'
      [from-research] → 'from-research'

    Unprefixed answers default to 'from-user' (safe).
    """
    a = answer.strip()
    if a.startswith("[from-code][auto-confirmed]"):
        return "from-code-auto"
    if a.startswith("[from-code]"):
        return "from-code"
    if a.startswith("[from-user][correction]"):
        return "from-user-correction"
    if a.startswith("[from-user]"):
        return "from-user"
    if a.startswith("[from-research]"):
        return "from-research"
    return "from-user"
