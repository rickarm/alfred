"""Format API response data into Telegram messages.

Uses HTML parse mode — much simpler than MarkdownV2 and less error-prone.
"""

import html
from datetime import date

_MAX_LEN = 4000  # Telegram limit is 4096; leave some buffer


def _esc(text: str) -> str:
    """Escape text for Telegram HTML mode."""
    return html.escape(str(text))


def _is_overdue(task: dict) -> bool:
    deadline = task.get("deadline") or task.get("start_date")
    if not deadline:
        return False
    try:
        d = date.fromisoformat(deadline[:10])
        return d < date.today()
    except (ValueError, TypeError):
        return False


def _task_line(task: dict) -> str:
    title = task.get("title") or "Untitled"
    status = task.get("status", "incomplete")

    if status == "completed":
        mark = "✓"
    else:
        mark = "⚠️" if _is_overdue(task) else "☐"

    line = f"{mark} {_esc(title)}"

    deadline = task.get("deadline")
    if deadline:
        line += f" <i>({_esc(deadline[:10])})</i>"

    project = task.get("project") or task.get("area")
    if project:
        line += f" · <i>{_esc(project)}</i>"

    return line


def format_task_list(tasks: list[dict], header: str = "") -> str:
    if not tasks:
        return "No tasks found."

    lines = []
    if header:
        lines.append(f"<b>{_esc(header)}</b>")

    shown = 0
    for task in tasks:
        lines.append(_task_line(task))
        shown += 1

    text = "\n".join(lines)
    return _truncate(text, total=len(tasks), shown=shown)


def format_project_list(projects: list[dict]) -> str:
    if not projects:
        return "No projects found."

    lines = ["<b>Projects</b>"]
    for p in projects:
        title = p.get("title") or "Untitled"
        area = p.get("area", "")
        line = f"📋 {_esc(title)}"
        if area:
            line += f" <i>({_esc(area)})</i>"
        lines.append(line)

    text = "\n".join(lines)
    return _truncate(text, total=len(projects), shown=len(projects))


def format_area_list(areas: list[dict]) -> str:
    if not areas:
        return "No areas found."
    lines = ["<b>Areas</b>"] + [f"• {_esc(a.get('title', 'Untitled'))}" for a in areas]
    return "\n".join(lines)


def format_search_results(tasks: list[dict], query: str) -> str:
    if not tasks:
        return f"No tasks found matching <i>{_esc(query)}</i>."
    header = f"Search: {query} ({len(tasks)} results)"
    return format_task_list(tasks, header=header)


def _truncate(text: str, total: int = 0, shown: int = 0) -> str:
    if len(text) <= _MAX_LEN:
        return text
    truncated = text[:_MAX_LEN]
    # Cut at last newline to avoid breaking a line
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline]
    actual_shown = truncated.count("\n")
    return truncated + f"\n<i>(showing first {actual_shown} of {total})</i>"
