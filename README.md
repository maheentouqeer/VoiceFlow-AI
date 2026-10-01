# VoiceFlow AI

Ambient voice triage. Open a tab, talk — a bug, a reminder, a stray idea, all
in one breath — stop, and VoiceFlow AI splits what you said into discrete items,
classifies each one, and actually acts on it: a real GitHub issue, a real
Todoist task, a real Notion page, or an explicit Slack message to #looplineai.

Slack is **action-only**: VoiceFlow AI does not mirror the whole session into Slack.
It posts to #looplineai only when you explicitly ask it to post/send/share/announce
something there.

## How it works

Two things happen, and they are deliberately separate:

1. **Live**: you open the page, talk, and the Voice Agent API transcribes it
   in real time. The agent is designed to listen rather than hold a conversation.
2. **After you stop**: the backend fetches the full transcript, splits it into
   discrete items, classifies each one, and — only then — executes the requested
   actions. GitHub, Todoist, Notion, and Slack are never touched while you're
   actually talking.

```
Browser mic → Voice Agent → session ends → fetch transcript
  → segment into items → classify each (type + destination + confidence)
  → execute only the requested destination → digest with real links
```

## What's in here

```
VoiceFlow-AI/
├── agents/ambient.jsonc
├── deployment/browser/
│   ├── server.py
│   ├── index.html
│   └── app.js
├── processor/
│   ├── fetch_session.py
│   ├── segment.py
│   ├── classify.py
│   ├── digest.py
│   ├── pipeline.py
│   ├── todoist_client.py
│   ├── slack_client.py
│   └── mcp_clients/
│       ├── github_client.py
│       └── notion_client.py
├── lib.py, publish.py
├── requirements.txt
├── .env.example
└── render.yaml
```

## Setup

Open `.env` and fill in:
- `ASSEMBLYAI_API_KEY`
- `GITHUB_PAT`
- `GITHUB_REPO`
- `TODOIST_TOKEN`
- `SLACK_BOT_TOKEN` — Slack bot token with `chat:write`
- `SLACK_CHANNEL_ID` — channel ID for **#looplineai**
- `NOTION_TOKEN` / `NOTION_PARENT_PAGE_ID` — optional

Keep all tokens in `.env`; never commit that file.

## Run it

```bash
python publish.py
python deployment/browser/server.py
```

Open the printed `http://localhost:3000` URL. Click **Start call**, speak several
unrelated actions, click **End call**, then click **Process this capture**.

## Test in this order

**1. GitHub**
```bash
python -m processor.mcp_clients.github_client <owner> <repo>
```

**2. Todoist**
```bash
python -m processor.todoist_client "VoiceFlow AI test task - safe to delete"
```

**3. Slack explicit action**
```bash
python -m processor.slack_client "VoiceFlow AI Slack client test - safe to delete"
```
This posts only that explicit test message to **#looplineai**.

**4. Segmentation**
```bash
python -m processor.segment
```

**5. Classification**
```bash
python -m processor.classify
```
The canned classification includes an explicit Slack request; confirm that
the Slack item is classified as `destination="slack"`.

**6. Real session transcript**
```bash
python processor/fetch_session.py <session_id>
```
Get `<session_id>` from the browser Events tab at `session.ready`.

**7. Full pipeline**
```bash
python -m processor.pipeline <session_id>
```

### Recommended end-to-end voice test

Say something like:

"Create a GitHub issue for the dashboard dark theme. Remind me tomorrow
at 10 AM to check the demo API key. We decided that email verification is
required for onboarding. Post on Slack that Ali has to improve the UI."

Expected result:
- GitHub: one issue for the dark theme.
- Todoist: one reminder.
- Notion: one decision.
- Slack **#looplineai**: only the message **"Ali has to improve the UI."**
- Slack does **not** receive a copy of the GitHub, Todoist, or Notion results.

## Deploy

Render should have:
- `ASSEMBLYAI_API_KEY`
- `GITHUB_PAT`
- `GITHUB_REPO`
- `TODOIST_TOKEN`
- `SLACK_BOT_TOKEN`
- `SLACK_CHANNEL_ID` pointing to **#looplineai**

Notion remains optional and uses the existing local/runtime setup.

## Governance

- Processing happens only after capture ends and you click Process.
- Anything below `CONFIDENCE_THRESHOLD` is filed nowhere and flagged for review.
- Credentials/secrets are explicitly routed to `skip`.
- Slack is never a session-wide broadcast. It is invoked only by an explicit
  Slack request and posts only the intended message.