# Codex Repair Prompt

Mode: `{{MODE}}`

Repair only the objective issues returned by Claude for the selected task. Do
not widen scope. Keep all edits within `allowed_paths`, preserve the single-main
policy, and rerun the targeted tests plus machine gates.

Return a JSON result matching `scripts/agent_loop/schemas/codex_result.schema.json`.

## Task

```json
{{TASK_JSON}}
```

## Selected Context

{{SELECTED_CONTEXT}}
