#!/usr/bin/env python3
"""Talk to your agent from a browser tab.

    python deployment/browser/server.py

The API key stays in this process; the page only gets 60-second tokens.
"""

import asyncio
import copy
import json
import os
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from lib import (ApiError, aai, load_env, publish_agent, read_agent,  # noqa: E402
                 required, stored_agent_id)


def resolve_agent() -> dict:
    """A published id means the agent is managed elsewhere, so use it as it is."""
    name = os.environ.get("AGENT", "minimal")
    known = stored_agent_id(name)
    if known:
        try:
            agent = aai(f"/agents/{known}")
        except ApiError as err:
            sys.exit(f"Could not load agent {known}: {err}")
        return {"id": known, "name": agent.get("name") or "Your agent"}
    agent = read_agent(name)
    try:
        result = publish_agent(agent, name=name, reuse_by_name=True)
    except ApiError as err:
        sys.exit(f"Could not publish agents/{name}.jsonc: {err}")
    verb = "Created" if result["created"] else "Updated"
    print(f'{verb} "{agent["name"]}" from agents/{name}.jsonc')
    return {"id": result["id"], "name": agent["name"]}


def public_agent(agent: dict) -> dict:
    """Read-only view of the stored agent. The API keeps header values and llm
    keys write-only; these deletes hold even if that changes. The system prompt
    is in here, so a public deployment shows it to anyone who opens the page."""
    copied = copy.deepcopy(agent)
    for tool in copied.get("tools", []):
        for header in tool.get("http", {}).get("headers", []):
            header["value"] = "<hidden>"
    for llm in copied.get("llm", []):
        llm.pop("api_key", None)
    return copied


AGENT = None
PAGE = ""


async def transcribe_mobile_audio(audio: bytes, content_type: str) -> str:
    """Upload a short mobile recording to AssemblyAI and wait for its transcript."""
    import httpx

    api_key = os.environ.get("ASSEMBLYAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is not configured on the server")

    headers = {
        "authorization": api_key,
        "content-type": "application/octet-stream",
    }
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        uploaded = await client.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            content=audio,
        )
        uploaded.raise_for_status()
        audio_url = uploaded.json().get("upload_url")
        if not audio_url:
            raise RuntimeError("AssemblyAI did not return an upload_url")

        created = await client.post(
            "https://api.assemblyai.com/v2/transcript",
            headers={"authorization": api_key, "content-type": "application/json"},
            json={"audio_url": audio_url, "punctuate": True, "format_text": True},
        )
        created.raise_for_status()
        transcript_id = created.json()["id"]

        for _ in range(45):
            await asyncio.sleep(1.5)
            status_resp = await client.get(
                f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                headers={"authorization": api_key},
            )
            status_resp.raise_for_status()
            payload = status_resp.json()
            status = payload.get("status")
            if status == "completed":
                text = (payload.get("text") or "").strip()
                if not text:
                    raise RuntimeError("AssemblyAI could not detect speech in the audio. Please make sure to speak clearly for at least 2-3 seconds.")
                return text
            if status == "error":
                raise RuntimeError(payload.get("error") or "AssemblyAI transcription failed")

    raise RuntimeError("Timed out waiting for the mobile transcript")


async def process_mobile_recording(audio: bytes, content_type: str) -> dict:
    """Mobile path: audio -> transcript -> existing VoiceFlow routing pipeline."""
    transcript = await transcribe_mobile_audio(audio, content_type)
    from processor import classify, digest, segment
    from processor.pipeline import _file_item

    raw_items = segment.split(transcript)
    classified = classify.classify_all(raw_items)
    filed = [await _file_item(item) for item in classified]
    return digest.build("mobile-" + uuid.uuid4().hex[:12], transcript, filed)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/token":
            try:
                token = aai("/token?product=voice_agent&expires_in_seconds=60")
                self._send(200, json.dumps(token).encode(), "application/json")
            except ApiError as err:
                print(err)
                self._send(502, b'{"error":"token request failed"}', "application/json")
            return
        if path == "/agent":
            try:
                agent = aai(f"/agents/{AGENT['id']}")
                self._send(200, json.dumps(public_agent(agent)).encode(), "application/json")
            except ApiError as err:
                print(err)
                self._send(502, b'{"error":"could not load the agent"}', "application/json")
            return
        if path == "/process":
            query = parse_qs(urlparse(self.path).query)
            session_id = (query.get("session_id") or [""])[0]
            if not session_id:
                self._send(400, b'{"error":"session_id query param required"}', "application/json")
                return
            try:
                # ThreadingHTTPServer gives every request its own thread, so
                # blocking this one thread on asyncio.run() while the
                # pipeline runs does not affect any other in-flight request
                # (including someone else's live /token or WebSocket audio).
                from processor.pipeline import run as run_pipeline
                result = asyncio.run(run_pipeline(session_id))
                self._send(200, json.dumps(result).encode(), "application/json")
            except Exception as err:  # noqa: BLE001 - surface it to the page, don't crash the server
                print(f"Processing failed for session {session_id}: {err}")
                self._send(502, json.dumps({"error": str(err)}).encode(), "application/json")
            return
        if path == "/app.js":
            self._send(200, (HERE / "app.js").read_bytes(), "text/javascript")
            return
        self._send(200, PAGE.encode(), "text/html")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/mobile/process":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    self._send(400, b'{"error":"audio body is required"}', "application/json")
                    return
                if length > 25 * 1024 * 1024:
                    self._send(413, b'{"error":"recording is too large; keep it under 25 MB"}', "application/json")
                    return
                audio = self.rfile.read(length)
                content_type = self.headers.get("Content-Type", "audio/mp4").split(";", 1)[0]
                result = asyncio.run(process_mobile_recording(audio, content_type))
                self._send(200, json.dumps(result).encode(), "application/json")
            except Exception as err:  # noqa: BLE001
                print(f"Mobile processing failed: {err}")
                self._send(502, json.dumps({"error": str(err)}).encode(), "application/json")
            return
        self._send(404, b'{"error":"not found"}', "application/json")

    def log_message(self, *args) -> None:  # quiet; errors are printed above
        pass


def main() -> None:
    global AGENT, PAGE
    load_env()
    required("ASSEMBLYAI_API_KEY", "get one at https://www.assemblyai.com/dashboard/api-keys")

    AGENT = resolve_agent()
    print(f"Agent: {AGENT['id']}")
    PAGE = ((HERE / "index.html").read_text()
            .replace("{{AGENT_NAME}}", AGENT["name"])
            .replace("{{AGENT_JSON}}", json.dumps(AGENT).replace("<", "\\u003c")))

    # PORT when set, otherwise 3000 and up until one is free.
    fixed = os.environ.get("PORT")
    port = int(fixed) if fixed else 3000
    while True:
        try:
            server = ThreadingHTTPServer(("", port), Handler)
            break
        except OSError:
            if fixed or port >= 3010:
                raise
            port += 1

    print(f"Talk to it: http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
