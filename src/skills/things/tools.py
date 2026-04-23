"""Claude tool definitions for Things 3 operations."""

THINGS_TOOLS: list[dict] = [
    {
        "name": "get_list",
        "description": "Get tasks from a Things 3 list. Use for: 'what's on my plate today', 'show inbox', 'what's upcoming'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "list_name": {
                    "type": "string",
                    "enum": ["inbox", "today", "upcoming", "anytime", "someday", "logbook"],
                    "description": "Which list to retrieve",
                }
            },
            "required": ["list_name"],
        },
    },
    {
        "name": "get_projects",
        "description": "Get all projects, optionally with their tasks. Use for: 'list my projects', 'show projects in Work area'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_items": {
                    "type": "boolean",
                    "description": "Include tasks within each project",
                }
            },
        },
    },
    {
        "name": "get_areas",
        "description": "Get all areas. Use for: 'show my areas', 'what areas do I have'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_tasks",
        "description": "Search tasks by keyword in title or notes. Use for: 'find tasks about X', 'do I have a task for Y'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_advanced",
        "description": "Advanced search with filters. Use for: 'what's overdue', 'tasks tagged deepwork', 'tasks due this week'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["incomplete", "completed", "canceled"],
                },
                "deadline": {
                    "type": "string",
                    "description": "Deadline date YYYY-MM-DD or 'today'",
                },
                "tag": {"type": "string", "description": "Filter by tag name"},
                "area": {"type": "string", "description": "Filter by area UUID"},
                "last": {
                    "type": "string",
                    "description": "Recently created, e.g. '3d', '1w', '2m'",
                },
            },
        },
    },
    {
        "name": "get_recent",
        "description": "Get recently created items. Use for: 'what did I add recently', 'new tasks this week'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period like '3d', '1w', '2m'",
                }
            },
        },
    },
    {
        "name": "create_todo",
        "description": "Create a new task. Use for: 'add a task to...', 'remind me to...', 'create a todo for...'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "notes": {"type": "string", "description": "Task notes/details"},
                "when": {
                    "type": "string",
                    "description": "Schedule: 'today', 'tomorrow', 'evening', 'anytime', 'someday', or YYYY-MM-DD",
                },
                "deadline": {"type": "string", "description": "Due date YYYY-MM-DD"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to apply",
                },
                "list_id": {
                    "type": "string",
                    "description": "Project UUID to add task to",
                },
                "checklist_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subtask checklist items",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_todo",
        "description": "Update an existing task — complete, reschedule, rename, cancel. IMPORTANT: search for the task first to get its UUID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Task UUID (find via search_tasks first)",
                },
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "when": {
                    "type": "string",
                    "description": "Schedule: 'today', 'tomorrow', 'evening', 'anytime', 'someday', or YYYY-MM-DD",
                },
                "deadline": {"type": "string", "description": "Due date YYYY-MM-DD"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "completed": {
                    "type": "boolean",
                    "description": "Set to true to mark as complete",
                },
                "canceled": {
                    "type": "boolean",
                    "description": "Set to true to cancel",
                },
                "list_id": {
                    "type": "string",
                    "description": "Move to a different project",
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "create_project",
        "description": "Create a new project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Project title"},
                "notes": {"type": "string"},
                "when": {"type": "string"},
                "deadline": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "area_id": {
                    "type": "string",
                    "description": "Area UUID to place project in",
                },
            },
            "required": ["title"],
        },
    },
]
