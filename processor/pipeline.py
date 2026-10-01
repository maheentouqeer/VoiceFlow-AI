"""Orchestrates the whole batch pipeline: fetch -> segment -> classify -> file -> digest.

Run it directly for a full local test without touching the browser at all:
    python -m processor.pipeline <session_id>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import load_env  # noqa: E402
from processor import classify, digest, fetch_session, segment  # noqa: E402
from processor import slack_client, todoist_client  # noqa: E402
from processor.mcp_clients import github_client  # noqa: E402

CONFIDENCE_THRESHOLD = 0.4


def _describe_error(err: BaseException) -> str:
    """Unwrap ExceptionGroup so the useful underlying error is shown."""
    found: list[str] = []

    def walk(e: BaseException) -> None:
        if isinstance(e, BaseExceptionGroup):
            for sub in e.exceptions:
                walk(sub)
        else:
            found.append(f"{type(e).__name__}: {e}")

    walk(err)
    return " | ".join(found) if found else str(err)


async def _file_item(item: classify.ClassifiedItem) -> digest.FiledItem:
    if item.destination == "skip" or item.error:
        return digest.FiledItem(
            text=item.text, type=item.type, destination=item.destination,
            confidence=item.confidence, status="skipped",
            detail=item.error or "classified as not actionable",
        )

    if item.confidence < CONFIDENCE_THRESHOLD:
        return digest.FiledItem(
            text=item.text, type=item.type, destination=item.destination,
            confidence=item.confidence, status="low_confidence",
            detail="confidence below threshold - filed nowhere, review manually",
        )

    if item.destination == "github":
        repo = os.environ.get("GITHUB_REPO", "")
        if "GITHUB_PAT" not in os.environ or "/" not in repo:
            return digest.FiledItem(
                text=item.text, type=item.type, destination="github",
                confidence=item.confidence, status="error",
                detail="GITHUB_PAT and GITHUB_REPO (as owner/repo) must be set in .env",
            )
        owner, repo_name = repo.split("/", 1)
        try:
            result = await github_client.create_issue(owner, repo_name, item.title, item.body)
            return digest.FiledItem(
                text=item.text, type=item.type, destination="github",
                confidence=item.confidence, status="filed", url=result.get("url"),
                detail="\n".join(result.get("raw", [])),
            )
        except Exception as err:  # noqa: BLE001
            return digest.FiledItem(
                text=item.text, type=item.type, destination="github",
                confidence=item.confidence, status="error", detail=_describe_error(err),
            )

    if item.destination == "todoist":
        if not os.environ.get("TODOIST_TOKEN"):
            return digest.FiledItem(
                text=item.text, type=item.type, destination="todoist",
                confidence=item.confidence, status="error",
                detail="TODOIST_TOKEN is not set in .env; cannot create the Todoist task.",
            )
        try:
            result = todoist_client.create_task(item.title or item.text)
            return digest.FiledItem(
                text=item.text, type=item.type, destination="todoist",
                confidence=item.confidence, status="filed", url=result.get("url"),
                detail="Todoist task created successfully.",
            )
        except Exception as err:  # noqa: BLE001
            return digest.FiledItem(
                text=item.text, type=item.type, destination="todoist",
                confidence=item.confidence, status="error", detail=_describe_error(err),
            )

    if item.destination == "notion":
        parent_id = os.environ.get("NOTION_PARENT_PAGE_ID", "")
        if "NOTION_TOKEN" not in os.environ or not parent_id:
            return digest.FiledItem(
                text=item.text, type=item.type, destination="notion",
                confidence=item.confidence, status="error",
                detail="Notion is a stretch goal - set NOTION_TOKEN and "
                       "NOTION_PARENT_PAGE_ID in .env to enable it, or leave "
                       "them unset and Notion items just won't file.",
            )
        try:
            from processor.mcp_clients import notion_client
            result = await notion_client.create_page(parent_id, item.title, item.body)
            return digest.FiledItem(
                text=item.text, type=item.type, destination="notion",
                confidence=item.confidence, status="filed", url=result.get("url"),
                detail="\n".join(result.get("raw", [])),
            )
        except Exception as err:  # noqa: BLE001
            return digest.FiledItem(
                text=item.text, type=item.type, destination="notion",
                confidence=item.confidence, status="error", detail=_describe_error(err),
            )

    if item.destination == "slack":
        if not os.environ.get("SLACK_BOT_TOKEN") or not os.environ.get("SLACK_CHANNEL_ID"):
            return digest.FiledItem(
                text=item.text, type=item.type, destination="slack",
                confidence=item.confidence, status="error",
                detail="SLACK_BOT_TOKEN and SLACK_CHANNEL_ID must be set. "
                       "SLACK_CHANNEL_ID should point to #looplineai.",
            )
        message = (item.body or item.title or item.text).strip()
        if not message:
            return digest.FiledItem(
                text=item.text, type=item.type, destination="slack",
                confidence=item.confidence, status="error",
                detail="Slack action did not contain a message to post.",
            )
        try:
            result = slack_client.post_message(message)
            return digest.FiledItem(
                text=item.text, type=item.type, destination="slack",
                confidence=item.confidence, status="filed",
                url=result.get("response_metadata", {}).get("url"),
                detail="Posted to #looplineai.",
            )
        except Exception as err:  # noqa: BLE001
            return digest.FiledItem(
                text=item.text, type=item.type, destination="slack",
                confidence=item.confidence, status="error", detail=_describe_error(err),
            )

    return digest.FiledItem(
        text=item.text, type=item.type, destination=item.destination,
        confidence=item.confidence, status="error",
        detail=f"unknown destination: {item.destination}",
    )


async def run(session_id: str) -> dict:
    transcript = fetch_session.get_transcript(session_id)
    raw_items = segment.split(transcript)
    classified = classify.classify_all(raw_items)
    filed = [await _file_item(item) for item in classified]
    return digest.build(session_id, transcript, filed)


if __name__ == "__main__":
    import asyncio
    import json

    load_env()
    if len(sys.argv) < 2:
        sys.exit("Usage: python -m processor.pipeline <session_id>")
    result = asyncio.run(run(sys.argv[1]))
    print(json.dumps(result, indent=2))