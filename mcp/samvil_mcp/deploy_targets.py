"""SAMVIL deploy-target evaluator (T3.4).

Centralizes the inputs the `samvil-deploy` skill needs that are best
produced from inside the MCP process — single source of truth for the
five `solution_type` × multiple-platform branches that previously lived
inline in the skill body:

- QA gate decision (must read `qa_status` from `project.state.json`).
- Per-`solution_type` deploy-target catalog (web-app, dashboard, game,
  mobile-app, automation) with command templates per platform.
- Required env-var inventory parsed from `.env.example` plus
  identification of placeholder/empty values that need filling.
- Build-artifact existence check (`.next/`, `dist/`) so the skill can
  decide whether to run `npm run build` first.
- The post-deploy `deploy-info.json` schema and the per-`solution_type`
  output-report template the skill renders to the user.

What stays in the skill body:

- Actually shelling out to `vercel`, `railway`, `coolify`, `eas`,
  `npx gh-pages`, `crontab`, etc. Those are intentionally CC-bound
  (host-bound, P8 graceful degradation).
- AskUserQuestion prompts for missing env vars and platform choice.
- Writing `deploy-info.json` and updating `project.state.json`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Catalog: per-solution_type deploy targets ──────────────────────────


# Each platform entry deliberately keeps the command as a *template* string
# with `<seed.name>` placeholders. The skill substitutes `seed.name` at
# render time. Keeping templates here (vs. f-strings in the skill body)
# is the T3.1 single-source-of-truth pattern: changing a deploy command
# is a one-file edit, not a 5-section grep across SKILL.md.
DEPLOY_CATALOG: dict[str, list[dict[str, Any]]] = {
    "web-app": [
        {
            "id": "vercel",
            "label": "Vercel",
            "command": "npx vercel --prod --yes",
            "config_files": ["vercel.json"],
            "notes": "Next.js 기본. Edge/Serverless. CDN.",
            "recommended": True,
        },
        {
            "id": "railway",
            "label": "Railway",
            "command": "railway up",
            "config_files": ["railway.toml", "nixpacks.toml"],
            "notes": "Full-stack. DB 옆에 둘 때 좋음.",
        },
        {
            "id": "coolify",
            "label": "Coolify",
            "command": "coolify deploy",
            "config_files": ["Dockerfile"],
            "notes": "셀프호스팅. Dockerfile 필요.",
        },
        {
            "id": "manual",
            "label": "수동",
            "command": "ls .next/",
            "config_files": [],
            "notes": "산출물 경로만 안내.",
        },
    ],
    "dashboard": [
        {
            "id": "vercel",
            "label": "Vercel",
            "command": "npx vercel --prod --yes",
            "config_files": ["vercel.json"],
            "notes": "recharts tree-shaking 자동 적용 (Next.js production build).",
            "recommended": True,
        },
        {
            "id": "railway",
            "label": "Railway",
            "command": "railway up",
            "config_files": ["railway.toml"],
            "notes": "Full-stack 대시보드.",
        },
        {
            "id": "coolify",
            "label": "Coolify",
            "command": "coolify deploy",
            "config_files": ["Dockerfile"],
            "notes": "셀프호스팅.",
        },
        {
            "id": "manual",
            "label": "수동",
            "command": "ls .next/",
            "config_files": [],
            "notes": "산출물 경로만 안내.",
        },
    ],
    "game": [
        {
            "id": "vercel",
            "label": "Vercel",
            "command": "npm run build && npx vercel --prod --yes",
            "config_files": [],
            "notes": "정적 호스팅. dist/ 자동 감지.",
            "recommended": True,
        },
        {
            "id": "gh-pages",
            "label": "GitHub Pages",
            "command": "npm run build && npx gh-pages -d dist",
            "config_files": [],
            "notes": "무료 정적 호스팅. gh-pages 브랜치.",
        },
        {
            "id": "manual",
            "label": "수동",
            "command": "ls dist/",
            "config_files": [],
            "notes": "dist/ 폴더를 웹 서버에 직접 배포.",
        },
    ],
    "mobile-app": [
        {
            "id": "eas-preview",
            "label": "EAS Build (APK preview)",
            "command": "eas build --platform android --profile preview",
            "config_files": ["eas.json", "app.json"],
            "notes": "스토어 등록 없이 APK 테스트.",
            "recommended": True,
        },
        {
            "id": "eas-production",
            "label": "EAS Build (production)",
            "command": "eas build --platform ios --profile production && eas build --platform android --profile production",
            "config_files": ["eas.json", "app.json"],
            "notes": "App Store / Play Store 제출. 인증서 필요.",
        },
        {
            "id": "eas-update",
            "label": "Expo Update (OTA)",
            "command": "eas update --branch production --message 'bug fix'",
            "config_files": ["eas.json"],
            "notes": "스토어 심사 없이 코드 업데이트.",
        },
        {
            "id": "manual",
            "label": "수동",
            "command": "expo start",
            "config_files": [],
            "notes": "개발 서버 실행 안내.",
        },
    ],
    "automation": [
        {
            "id": "cc-skill",
            "label": "CC skill (CronCreate)",
            "command": "CronCreate(cron='<seed.core_flow.trigger>', prompt='Run /<seed.name>', recurring=true, durable=true)",
            "config_files": [],
            "notes": "CC 내장 cron으로 등록.",
            "recommended": True,
        },
        {
            "id": "cron",
            "label": "Cron (system)",
            "command": "crontab .samvil/crontab-template",
            "config_files": [".samvil/crontab-template"],
            "notes": "시스템 crontab. 템플릿 자동 생성.",
        },
        {
            "id": "serverless",
            "label": "Serverless",
            "command": "serverless deploy",
            "config_files": ["serverless.yml", "vercel.json"],
            "notes": "AWS Lambda (Python) 또는 Vercel cron (Node).",
        },
        {
            "id": "manual",
            "label": "수동",
            "command": "python src/main.py --config .env",
            "config_files": [".env"],
            "notes": "수동 실행. dry-run 가능.",
        },
    ],
}


# Per-solution_type build-artifact paths the skill checks before deploy.
# web-app and dashboard default to .next (Next.js), but are overridden
# by _artifact_paths_for_framework() when the seed declares a Vite/Astro stack.
ARTIFACT_PATHS: dict[str, list[str]] = {
    "web-app": [".next"],
    "dashboard": [".next"],
    "game": ["dist"],
    "mobile-app": [],  # EAS handles its own build artifacts
    "automation": [],  # No web build artifact
}

# Frameworks that produce dist/ instead of .next/
_VITE_LIKE_FRAMEWORKS = frozenset({
    "vite", "vite-react", "vite-vue", "vite-svelte",
    "astro", "sveltekit", "remix",
})


def _artifact_paths_for_framework(
    solution_type: str,
    tech_stack: dict[str, object] | None,
) -> list[str]:
    """Return artifact paths, taking framework into account.

    Vite/Astro-family frameworks produce `dist/` not `.next/`.
    Falls back to ARTIFACT_PATHS when framework is absent or unknown.
    """
    framework = ""
    if isinstance(tech_stack, dict):
        fw = tech_stack.get("framework") or ""
        framework = str(fw).lower().split("@")[0].strip()

    if framework in _VITE_LIKE_FRAMEWORKS:
        return ["dist"]
    return ARTIFACT_PATHS.get(solution_type, [])


# Placeholder strings that count as "not filled in yet" for env vars.
# `.env.example` typically contains `KEY=` or `KEY=YOUR_KEY_HERE` etc.
# We treat empty values and any of these tokens as missing.
_EMPTY_PLACEHOLDERS = {
    "",
    "your_key_here",
    "your-key-here",
    "your_api_key",
    "your-api-key",
    "changeme",
    "todo",
    "xxx",
    "<your-key>",
}

# A loose env-line parser: KEY=VALUE with optional surrounding quotes.
# Comments and blank lines are skipped.
_ENV_LINE_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


def parse_env_example(env_path: Path) -> dict[str, Any]:
    """Parse a `.env.example`-style file into structured info.

    Returns:
        {
          "exists": bool,
          "path": str,
          "required_keys": [list of KEY names declared],
          "placeholder_keys": [keys whose value is empty / a known placeholder],
        }

    Missing files are reported as `exists: False` with empty lists rather
    than raising — INV-5 / P8: deploy must still be able to run when there
    are no env vars at all (e.g., a static game).
    """
    out: dict[str, Any] = {
        "exists": env_path.exists(),
        "path": str(env_path),
        "required_keys": [],
        "placeholder_keys": [],
    }
    if not out["exists"]:
        return out

    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        out["exists"] = False
        return out

    required: list[str] = []
    placeholders: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _ENV_LINE_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        # Strip matching surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        required.append(key)
        if value.strip().lower() in _EMPTY_PLACEHOLDERS:
            placeholders.append(key)

    out["required_keys"] = required
    out["placeholder_keys"] = placeholders
    return out


# ── QA gate ────────────────────────────────────────────────────────────


def evaluate_qa_gate(state: dict[str, Any]) -> dict[str, Any]:
    """Return the QA-gate verdict for deploy.

    Reads `qa_status` (or nested `qa.status`) from the project state and
    returns a structured pass/blocked decision the skill can branch on
    without re-implementing the lookup. Anything other than `PASS` (case
    insensitive) blocks deploy — matches the legacy skill's contract:
    "QA status가 PASS가 아니면 배포 중단".
    """
    qa_status = state.get("qa_status")
    if qa_status is None:
        qa = state.get("qa") or {}
        if isinstance(qa, dict):
            qa_status = qa.get("status") or qa.get("verdict")

    raw = str(qa_status or "").strip().upper()
    passed = raw == "PASS"
    return {
        "verdict": "pass" if passed else "blocked",
        "qa_status": raw or None,
        "reason": (
            "QA verdict is PASS"
            if passed
            else f"QA verdict must be PASS to deploy (current: {raw or 'missing'})"
        ),
        "next_action": (
            "proceed to platform selection"
            if passed
            else "run /samvil:samvil-qa until verdict is PASS, then re-invoke deploy"
        ),
    }


# ── Aggregator ─────────────────────────────────────────────────────────


@dataclass
class DeployTargetReport:
    """Aggregated deploy-readiness view the thin skill renders from."""

    schema_version: str = "1.0"
    project_root: str = ""
    solution_type: str = ""
    qa_gate: dict[str, Any] = field(default_factory=dict)
    platforms: list[dict[str, Any]] = field(default_factory=list)
    selected_platform: dict[str, Any] | None = None
    env_vars: dict[str, Any] = field(default_factory=dict)
    build_artifact: dict[str, Any] = field(default_factory=dict)
    ready: bool = False
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_root": self.project_root,
            "solution_type": self.solution_type,
            "qa_gate": self.qa_gate,
            "platforms": self.platforms,
            "selected_platform": self.selected_platform,
            "env_vars": self.env_vars,
            "build_artifact": self.build_artifact,
            "ready": self.ready,
            "blockers": self.blockers,
        }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def evaluate_deploy_target(
    project_root: str | Path,
    *,
    platform: str | None = None,
) -> dict[str, Any]:
    """Aggregate every fact the samvil-deploy skill needs in one call.

    Args:
        project_root: Directory containing `project.state.json`,
            `project.seed.json`, and (optionally) `.env.example`.
        platform: Optional platform `id` from the catalog. If omitted, the
            recommended platform for the seed's `solution_type` is chosen.
            If the seed pins `tech_stack.deploy`, that wins over both.

    Returns:
        A dict shaped per `DeployTargetReport.to_dict()`. Errors are
        surfaced as a top-level `error` key (INV-5 / P8): the skill must
        not crash on a missing seed/state.
    """
    root = Path(project_root)

    state = _read_json(root / "project.state.json") or {}
    seed = _read_json(root / "project.seed.json") or {}

    solution_type = str(seed.get("solution_type") or "web-app")
    if solution_type not in DEPLOY_CATALOG:
        # Unknown solution_type — fall through to web-app catalog so the
        # skill can still render *something* and surface the mismatch.
        solution_type_used = "web-app"
    else:
        solution_type_used = solution_type

    catalog = DEPLOY_CATALOG[solution_type_used]

    # Platform precedence:
    #   1. Caller-provided `platform` argument (user choice from skill).
    #   2. seed.tech_stack.deploy (project-pinned).
    #   3. Catalog entry with `recommended: true`.
    seed_pinned = (
        (seed.get("tech_stack") or {}).get("deploy")
        if isinstance(seed.get("tech_stack"), dict)
        else None
    )
    chosen_id = platform or seed_pinned

    selected: dict[str, Any] | None = None
    if chosen_id:
        for entry in catalog:
            if entry["id"] == chosen_id:
                selected = entry
                break
    if selected is None:
        for entry in catalog:
            if entry.get("recommended"):
                selected = entry
                break
    if selected is None and catalog:
        selected = catalog[0]

    qa_gate = evaluate_qa_gate(state)
    env_info = parse_env_example(root / ".env.example")

    artifact_paths = _artifact_paths_for_framework(
        solution_type_used, seed.get("tech_stack")
    )
    artifact_present = any((root / p).exists() for p in artifact_paths)
    build_artifact = {
        "checked_paths": artifact_paths,
        "present": artifact_present if artifact_paths else None,
    }

    blockers: list[str] = []
    if qa_gate["verdict"] != "pass":
        blockers.append(qa_gate["reason"])
    if env_info["placeholder_keys"]:
        blockers.append(
            "missing env values: " + ", ".join(env_info["placeholder_keys"])
        )
    if (
        artifact_paths
        and not artifact_present
        and selected
        and selected["id"] != "manual"
    ):
        blockers.append(
            f"build artifact missing in {artifact_paths!r}; run `npm run build`"
        )

    report = DeployTargetReport(
        project_root=str(root),
        solution_type=solution_type,
        qa_gate=qa_gate,
        platforms=catalog,
        selected_platform=selected,
        env_vars=env_info,
        build_artifact=build_artifact,
        ready=not blockers,
        blockers=blockers,
    )
    return report.to_dict()
