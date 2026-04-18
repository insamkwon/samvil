"""PM Seed → Engineering Seed conversion (v3.0.0, T4)."""

from __future__ import annotations


def validate_pm_seed(pm_seed: dict) -> list[str]:
    """Return a list of error strings (empty = valid)."""
    errors: list[str] = []
    if not pm_seed.get("name"):
        errors.append("name is required")
    if not pm_seed.get("vision"):
        errors.append("vision is required")
    epics = pm_seed.get("epics")
    if not epics or not isinstance(epics, list):
        errors.append("epics must be a non-empty list")
        return errors
    seen_epic_ids: set[str] = set()
    seen_task_ids: set[str] = set()
    for i, epic in enumerate(epics, 1):
        if not isinstance(epic, dict):
            errors.append(f"epic #{i} must be an object")
            continue
        eid = epic.get("id")
        if not eid:
            errors.append(f"epic #{i} missing id")
        elif eid in seen_epic_ids:
            errors.append(f"duplicate epic id: {eid}")
        else:
            seen_epic_ids.add(eid)
        if not epic.get("title"):
            errors.append(f"epic {eid or i} missing title")
        tasks = epic.get("tasks")
        if not tasks or not isinstance(tasks, list):
            errors.append(f"epic {eid or i} must have tasks[]")
            continue
        for j, task in enumerate(tasks, 1):
            if not isinstance(task, dict):
                errors.append(f"epic {eid}.task#{j} must be an object")
                continue
            tid = task.get("id")
            if not tid:
                errors.append(f"epic {eid}.task#{j} missing id")
            elif tid in seen_task_ids:
                errors.append(f"duplicate task id: {tid}")
            else:
                seen_task_ids.add(tid)
            if not task.get("description"):
                errors.append(f"task {tid or j} missing description")
            acs = task.get("acceptance_criteria")
            if not isinstance(acs, list) or not acs:
                errors.append(f"task {tid or j} must have acceptance_criteria[]")
    return errors


def pm_seed_to_eng_seed(
    pm_seed: dict,
    defaults: dict | None = None,
) -> dict:
    """Flatten PM epics/tasks into an engineering seed that `validate_seed` accepts.

    Raises ValueError if the PM seed is invalid.

    `defaults` lets the caller (typically the PM interview skill) fill in the
    engineering-only fields (tech_stack, core_experience, solution_type, ...)
    that the PM phase does not collect. Anything missing from both the PM
    seed and defaults is filled with a conservative placeholder that still
    passes validate_seed, so downstream skills (Council, Design) can refine
    it before Build/QA.
    """
    errors = validate_pm_seed(pm_seed)
    if errors:
        raise ValueError("Invalid PM seed: " + "; ".join(errors))

    features: list[dict] = []
    for epic in pm_seed["epics"]:
        for task in epic["tasks"]:
            features.append({
                "name": task["id"],
                "description": f"{epic['title']} / {task['description']}",
                "priority": int(task.get("priority", 1)),
                "acceptance_criteria": task["acceptance_criteria"],
            })

    d = defaults or {}

    eng_seed: dict = {
        "name": pm_seed["name"],
        "description": d.get("description") or pm_seed.get("vision", ""),
        "vision": pm_seed["vision"],
        "solution_type": d.get("solution_type", "web-app"),
        "tech_stack": d.get("tech_stack") or {"framework": "nextjs"},
        "core_experience": d.get("core_experience") or {
            "primary_screen": _infer_primary_screen(pm_seed),
            "key_interactions": ["view", "create"],
        },
        "constraints": list(d.get("constraints") or pm_seed.get("constraints", []) or ["TBD — refined in Council"]),
        "out_of_scope": list(d.get("out_of_scope") or pm_seed.get("out_of_scope", []) or ["TBD — refined in Council"]),
        "version": d.get("version", "3.0"),
        "schema_version": "3.0",
        "features": features,
    }
    if "users" in pm_seed:
        eng_seed["users"] = pm_seed["users"]
    if "metrics" in pm_seed:
        eng_seed["metrics"] = pm_seed["metrics"]
    # Preserve optional fields from PM seed without clobbering derived ones
    for k, v in pm_seed.items():
        if k not in eng_seed and k != "epics":
            eng_seed[k] = v
    return eng_seed


def _infer_primary_screen(pm_seed: dict) -> str:
    """Best-effort PascalCase screen name from the first epic."""
    import re
    title = (pm_seed.get("epics") or [{}])[0].get("title", "")
    words = re.findall(r"[A-Za-z]+", title)
    if not words:
        return "HomeScreen"
    pascal = "".join(w.capitalize() for w in words)
    if not pascal.endswith("Screen"):
        pascal += "Screen"
    return pascal
