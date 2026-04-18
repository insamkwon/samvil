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


def pm_seed_to_eng_seed(pm_seed: dict) -> dict:
    """Flatten PM epics/tasks into engineering seed features[].

    Raises ValueError if the PM seed is invalid.
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

    eng_seed: dict = {
        "name": pm_seed["name"],
        "vision": pm_seed["vision"],
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
