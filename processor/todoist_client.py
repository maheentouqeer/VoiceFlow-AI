"""Small direct client for Todoist's REST API v1.

Auth: TODOIST_TOKEN from Todoist Settings -> Integrations -> Developer.
Endpoint: https://api.todoist.com/api/v1/tasks
"""

from __future__ import annotations

import os

import httpx

TODOIST_API_URL = "https://api.todoist.com/api/v1/tasks"


def create_task(title: str) -> dict:
    """Create a Todoist task in the authenticated user's Inbox.

    Returns {"url": ..., "raw": ...}. The URL is constructed from the task id
    because Todoist API v1 no longer returns the old v2-style URL field.
    """
    token = os.environ["TODOIST_TOKEN"]
    response = httpx.post(
        TODOIST_API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"content": title},
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    task_id = data.get("id")
    if not task_id:
        raise RuntimeError(f"Todoist did not return a task id. Response: {data}")

    return {
        "url": f"https://app.todoist.com/app/task/{task_id}",
        "raw": data,
    }


if __name__ == "__main__":
    import sys
    from lib import load_env, required  # noqa: E402

    sys.path.insert(0, ".")
    load_env()
    required("TODOIST_TOKEN", "get your personal API token from Todoist Settings -> Integrations -> Developer")

    title = " ".join(sys.argv[1:]).strip() or "VoiceFlow AI test task - safe to delete"
    print(create_task(title))