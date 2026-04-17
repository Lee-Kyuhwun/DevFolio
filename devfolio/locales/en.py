"""English string catalog."""

STRINGS: dict[str, str] = {
    # Common
    "not_initialized": "DevFolio is not initialized.",
    "not_initialized_hint": "Run `devfolio init` first.",
    "cancelled": "Cancelled.",
    "success": "Done!",

    # Projects
    "project.not_found": "Project not found: {name}",
    "project.not_found_hint": "Use `devfolio project list` to see available projects.",
    "project.duplicate": "A project with this name already exists: '{name}'",
    "project.duplicate_hint": "Use `devfolio project list` to check existing projects.",
    "project.created": "Project created! ID: {id}",
    "project.deleted": "'{name}' has been deleted.",
    "project.updated": "Updated successfully.",
    "project.none": "No projects found.",
    "project.none_hint": "Use `devfolio project add` to add your first project.",

    # Tasks
    "task.not_found": "Task not found: {name} (project: {project})",
    "task.not_found_hint": "Use `devfolio task list <project>` to see available tasks.",
    "task.created": "Task created! ID: {id}",
    "task.deleted": "'{name}' has been deleted.",
    "task.updated": "Updated successfully.",
    "task.none": "No tasks found.",
    "task.ai_cache_cleared": "Content changed — AI cache cleared. Run `devfolio ai generate task` to regenerate.",

    # Export
    "export.done": "Export complete: {path}",
    "export.sync_hint": "Next: run `devfolio sync run` to update your GitHub backup.",
    "export.invalid_format": "Unsupported format: {fmt}",
    "export.invalid_format_hint": "Supported formats: {formats}",
    "export.no_projects": "No projects found.",
    "export.no_projects_hint": "Use `devfolio project add` to add your first project.",
    "export.project_not_found": "Specified project(s) not found.",
    "export.project_not_found_hint": "Use `devfolio project list` to check project names and IDs.",
    "export.generating": "Generating document...",
    "export.path_error": "Output path is outside the allowed range: {path}",
    "export.path_error_hint": "Specify a path under your home directory or current working directory.",

    # AI
    "ai.not_configured": "No AI provider configured.",
    "ai.not_configured_hint": "Use `devfolio config ai set` to configure a provider.",
    "ai.auth_error": "API authentication failed: {provider}",
    "ai.rate_limit": "API rate limit exceeded: {provider}",
    "ai.error": "AI call failed: {message}",
    "ai.generating": "Generating text with {provider}...",
    "ai.done": "AI generation complete.",

    # Sync
    "sync.not_configured": "GitHub sync is not configured.",
    "sync.not_configured_hint": "Use `devfolio sync setup` to configure a repository.",
    "sync.done": "GitHub sync complete.",
    "sync.no_changes": "No changes — GitHub sync skipped.",
    "sync.connected": "GitHub sync repository connected: {url}",

    # Config
    "config.saved": "Defaults updated.",
    "config.no_changes": "Specify a change with --format, --lang, or --provider.",
    "config.invalid_format": "Invalid format: {fmt}",
    "config.invalid_lang": "Invalid language: {lang}",

    # Validation
    "validate.team_size_invalid": "'{value}' is not a valid number. Defaulting to 1.",
    "validate.team_size_negative": "Team size must be 1 or more. Defaulting to 1.",
    "validate.email_invalid": "Invalid email format: {value}",
    "validate.url_invalid": "URL must start with http:// or https://: {value}",
    "validate.branch_invalid": "Invalid branch name: {value}",
}
