"""Small direct client for Slack's Web API.

Auth: SLACK_BOT_TOKEN with the chat:write scope.
Target: SLACK_CHANNEL_ID, configured to the #looplineai channel.
"""

from __future__ import annotations

import os

import httpx

SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


def post_message(text: str) -> dict:
    """Post one explicit VoiceFlow AI Slack action to #looplineai."""
    token = os.environ["SLACK_BOT_TOKEN"]
    channel = os.environ["SLACK_CHANNEL_ID"]

    response = httpx.post(
        SLACK_POST_MESSAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={"channel": channel, "text": text},
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack chat.postMessage failed: {data.get('error', data)}")

    return data


if __name__ == "__main__":
    import sys
    from lib import load_env, required  # noqa: E402

    sys.path.insert(0, ".")
    load_env()
    required("SLACK_BOT_TOKEN", "create a Slack app with the chat:write scope and install it")
    required("SLACK_CHANNEL_ID", "set the ID of #looplineai")

    message = " ".join(sys.argv[1:]).strip() or "VoiceFlow AI Slack client test - safe to delete"
    print(post_message(message))