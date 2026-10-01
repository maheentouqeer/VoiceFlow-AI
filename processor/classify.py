"""Classify every segmented item - type, destination, confidence, and a
ready-to-file title/body for each.

Tries ONE batched call first (fast, lower rate-limit risk). If the model
ever returns the wrong number of results for that batch,  it falls back to
classifying each item individually.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from processor import llm_gateway

BATCH_PROMPT = """You triage a numbered list of items from someone's spoken notes and decide where each one belongs.

Valid "type" values: "bug", "idea", "reminder", "decision", "note".
Valid "destination" values: "github", "notion", "todoist", "slack", "skip".
- "github": a bug or a concrete idea that is ready to become an implementation issue.
- "notion": a decision or note worth keeping but not actionable as a task.
- "todoist": a reminder or personal task that should become a Todoist task.
- "slack": ONLY when the speaker explicitly asks VoiceFlow AI to post, send, share, announce, or message something on Slack.
- "skip": too vague to be a real item, or anything that looks like a password/secret/token - never file credentials anywhere.

Routing rules:
- reminder -> todoist
- bug -> github
- concrete, implementable ideas (for example, "add a dark mode toggle") -> github
- broad or tentative product/design ideas (for example, "the UI needs a better color theme someday") -> notion
- decision -> notion
- note -> notion
- explicit Slack action ("post this on Slack", "send this to Slack", "announce this in Slack", etc.) -> slack

IMPORTANT: Slack is an action destination, not a copy of the whole session.
Only route an item to Slack when that item itself contains an explicit request
to post/send/share/announce a message on Slack. Do not route bugs, reminders,
ideas, decisions, or notes to Slack just because Slack is available.

For "slack", use "body" as the exact concise message that should be posted.
Do not include the user's surrounding routing instruction if it is not part
of the intended message. For example:
"Post on Slack that Ali has to improve the UI" -> body "Ali has to improve the UI".
For "github", include "title" (short, imperative) and "body" (1-2 sentences).
For "notion", include "title" (short) and "body" (the content, cleaned up).
For "todoist", include "title" (a concise task/reminder title).
For "skip", omit title/body.

Give each item a "confidence" from 0 to 1 - lower it if genuinely ambiguous.

CRITICAL: you MUST return exactly as many objects as there are numbered items below,
one each, in the SAME ORDER. Never merge two items into one object. Never omit an item.

Respond with ONLY a JSON array, nothing else:
[{"type": "...", "destination": "...", "confidence": 0.0, "title": "...", "body": "..."}, ...]
"""

SINGLE_PROMPT = """You triage ONE item from someone's spoken notes and decide where it belongs.

Valid "type": "bug", "idea", "reminder", "decision", "note".
Valid "destination": "github", "notion", "todoist", "slack", or "skip".
Route reminder -> todoist; bug -> github; decision/note -> notion.
Route concrete, implementation-ready ideas -> github; broad or tentative
product/design ideas -> notion.
Route to slack ONLY when the speaker explicitly asks to post, send, share, or announce something on Slack.
Slack is an action destination, not a digest destination.
For Slack, put the intended message in "body" and remove only the routing phrase.
Use skip for anything too vague or anything that looks like a credential - never file secrets.

Include "confidence" (0-1), and for github/notion a "title" and "body"; for todoist include a concise "title"; for slack include a concise "body".

Respond with ONLY a JSON object, nothing else:
{"type": "...", "destination": "...", "confidence": 0.0, "title": "...", "body": "..."}
"""


@dataclass
class ClassifiedItem:
    text: str
    type: str
    destination: str
    confidence: float
    title: str = ""
    body: str = ""
    error: str = ""


def _build_item(text: str, data: dict) -> ClassifiedItem:
    item_type = data.get("type", "note")
    destination = data.get("destination", "skip")

    # Slack is an explicit user action. Enforce this deterministically so the
    # model cannot misclassify "Post on Slack..." as a reminder/idea/etc.
    import re
    explicit_slack = bool(re.search(
        r"\b(post|send|share|announce|message)\b.*\b(on|to|in)\s+slack\b",
        text,
        re.IGNORECASE,
    )) or bool(re.search(
        r"\bslack\b.*\b(post|send|share|announce|message)\b",
        text,
        re.IGNORECASE,
    ))
    if explicit_slack:
        destination = "slack"
        # Slack actions are messages, not reminders/tasks in the digest.
        if item_type == "reminder":
            item_type = "note"

    # Keep skip intact. Slack is special: it is an explicit action destination
    # and must not be overwritten by the normal type -> destination mapping.
    if destination != "skip" and destination != "slack" and item_type != "idea":
        destination = {
            "reminder": "todoist",
            "bug": "github",
            "decision": "notion",
            "note": "notion",
        }.get(item_type, destination)

    return ClassifiedItem(
        text=text,
        type=item_type,
        destination=destination,
        confidence=float(data.get("confidence") or 0),
        title=data.get("title", ""),
        body=data.get("body", ""),
    )


def _classify_one(text: str) -> ClassifiedItem:
    content = llm_gateway.chat(SINGLE_PROMPT, text, max_tokens=300)
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return _build_item(text, data)
    except json.JSONDecodeError:
        pass
    return ClassifiedItem(
        text=text,
        type="note",
        destination="skip",
        confidence=0.0,
        error=f"classification failed. Raw: {content[:200]}",
    )


def classify_all(items: list[str]) -> list[ClassifiedItem]:
    if not items:
        return []

    numbered = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(items))
    content = llm_gateway.chat(
        BATCH_PROMPT, numbered, max_tokens=250 * len(items) + 200
    )

    try:
        results = json.loads(content)
    except json.JSONDecodeError:
        results = None

    if isinstance(results, list) and len(results) == len(items):
        return [
            _build_item(text, data) if isinstance(data, dict) else _classify_one(text)
            for text, data in zip(items, results)
        ]

    got = len(results) if isinstance(results, list) else "invalid JSON"
    print(
        f"[classify] batch returned {got} results for {len(items)} items - "
        f"falling back to one call per item"
    )
    return [_classify_one(text) for text in items]


if __name__ == "__main__":
    import sys
    from lib import load_env, required  # noqa: E402

    sys.path.insert(0, ".")
    load_env()
    required("ASSEMBLYAI_API_KEY")

    samples = [
        "Bug: the login button doesn't work on Safari",
        "Remind me to email Sara about the contract renewal before Friday",
        "What if we added a dark mode toggle, could be a nice quick win",
        "Post on Slack that Ali has to improve the UI",
    ]
    for item in classify_all(samples):
        print(item)