# PM Seed Schema (v3.0.0, T4)

A higher-level spec used by the optional **PM Interview** mode. The PM seed captures vision, users, metrics, and an epic/task breakdown before we commit to engineering-level features. It **converts** to the standard `project.seed.json` before Build/QA run.

## Fields

```jsonc
{
  "name": "string",
  "vision": "string",
  "users": [
    {
      "segment": "string",
      "pain_points": ["string", ...]
    }
  ],
  "metrics": [
    {
      "name": "string",
      "target": "string"
    }
  ],
  "epics": [
    {
      "id": "E1",
      "title": "string",
      "tasks": [
        {
          "id": "T1.1",
          "description": "string",
          "acceptance_criteria": [
            {
              "id": "AC-1",
              "description": "string",
              "children": []
            }
          ]
        }
      ]
    }
  ]
}
```

## Required vs optional

- `name`, `vision`, `epics` are required
- Each epic needs `id`, `title`, `tasks[]`
- Each task needs `id`, `description`, `acceptance_criteria[]`
- `users`, `metrics` are optional but highly recommended

## Conversion to engineering seed

The MCP tool `pm_seed_to_eng_seed` flattens epics/tasks into `features[]`:

- Each task becomes one feature (`name = task.id`)
- `description` is `"{epic.title} / {task.description}"`
- `acceptance_criteria` moves over verbatim as a v3 AC tree
- `priority` defaults to 1
- Output always sets `schema_version: "3.0"`

Vision and metrics are preserved at the seed root so retrospective and evolve stages can reference them.

## Example

```json
{
  "name": "habit-tracker",
  "vision": "Daily habit accountability for remote workers",
  "users": [
    {"segment": "Remote knowledge workers", "pain_points": ["loses momentum", "no peer accountability"]}
  ],
  "metrics": [
    {"name": "D7 retention", "target": ">= 40%"}
  ],
  "epics": [
    {
      "id": "E1",
      "title": "Habit CRUD",
      "tasks": [
        {
          "id": "T1.1",
          "description": "Add a habit with name + frequency",
          "acceptance_criteria": [
            {"id": "AC-1.1.1", "description": "Form validates required fields", "children": []},
            {"id": "AC-1.1.2", "description": "Habit persists across refresh", "children": []}
          ]
        }
      ]
    }
  ]
}
```
