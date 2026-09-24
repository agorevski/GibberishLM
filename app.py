"""Gibberish web application.

A faux Claude Opus 4.8 / Claude Code CLI experience. Serves a terminal-style
UI and streams entirely fabricated agent output (reasoning, bash tool calls,
results, and lorem ipsum prose) over Server-Sent Events.

Nothing here connects to a real model. All output is gibberish by design.
"""

from __future__ import annotations

import json
import os
import time

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import anthropic_api
import gibberish
import timing

app = Flask(__name__)

MODEL_NAME = "Claude Opus 4.8 (Gibberish Emulation)"

# Default model id reported to Anthropic API clients (e.g. the Claude Code CLI).
DEFAULT_MODEL_ID = os.environ.get(
    "GIBBERISH_MODEL_ID", "claude-opus-4-8-gibberish"
)

# Whether to emit fake Bash tool calls to Anthropic API clients. When enabled
# (default), the real Claude Code CLI will actually execute the harmless demo
# command (e.g. `echo "hello world"`). Set GIBBERISH_TOOLS=0 to disable.
ALLOW_TOOLS = os.environ.get("GIBBERISH_TOOLS", "1") not in ("0", "false", "no")


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Events message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.route("/")
def index() -> str:
    return render_template("index.html", model_name=MODEL_NAME)


@app.route("/api/stream", methods=["POST"])
def stream() -> Response:
    payload = request.get_json(silent=True) or {}
    prompt = str(payload.get("prompt", "")).strip()

    @stream_with_context
    def generate():
        clock = timing.RequestTiming(want_thinking=True)
        yield _sse("session_start", {"model": MODEL_NAME, "prompt": prompt})

        first_token = True
        for token in gibberish.build_session(prompt, think_words=clock.think_words()):
            if token.type == "status":
                yield _sse("status", {"label": token.content})
                continue

            if token.type == "done":
                yield _sse("done", {})
                continue

            if token.type == "tool_call":
                yield _sse(
                    "tool_call",
                    {"tool": (token.meta or {}).get("tool", "bash"),
                     "command": token.content},
                )
                # Simulate the command actually executing.
                time.sleep(clock.tool_exec_latency())
                continue

            if token.type == "tool_result":
                yield _sse("block_start", {"type": "tool_result"})
                for chunk in gibberish.stream_tokens(token):
                    yield _sse("delta", {"type": "tool_result", "text": chunk})
                    time.sleep(clock.tool_delay(max(1, len(chunk.split()))))
                yield _sse("block_end", {"type": "tool_result"})
                continue

            # thinking / text blocks stream chunk by chunk.
            yield _sse("block_start", {"type": token.type})
            for chunk in gibberish.stream_tokens(token):
                wc = max(1, len(chunk.split()))
                if first_token:
                    delay = clock.initial_delay(visible_thinking=token.type == "thinking")
                    first_token = False
                elif token.type == "thinking":
                    delay = clock.think_delay(wc)
                else:
                    delay = clock.text_delay(wc)
                time.sleep(delay)
                yield _sse("delta", {"type": token.type, "text": chunk})
            yield _sse("block_end", {"type": token.type})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Anthropic Messages API compatibility (for the Claude Code CLI).
#
# These endpoints make Gibberish look like an Anthropic-compatible model
# provider. Point the CLI at Gibberish with:
#     ANTHROPIC_BASE_URL=http://127.0.0.1:5000
# Authentication is intentionally NOT enforced — any API key is accepted.
# ---------------------------------------------------------------------------

def _wants_thinking(payload: dict) -> bool:
    thinking = payload.get("thinking")
    return isinstance(thinking, dict) and thinking.get("type") == "enabled"


@app.route("/v1/messages", methods=["POST"])
def v1_messages() -> Response:
    payload = request.get_json(silent=True) or {}
    model = payload.get("model") or DEFAULT_MODEL_ID
    messages = payload.get("messages") or []
    tools = payload.get("tools") or []
    want_thinking = _wants_thinking(payload)

    clock = timing.RequestTiming(want_thinking=want_thinking)
    blocks = anthropic_api.plan_blocks(
        messages, tools, want_thinking, ALLOW_TOOLS,
        think_words=clock.think_words(),
    )

    if not payload.get("stream"):
        # Non-streaming clients still wait a realistic, variable amount of time.
        time.sleep(clock.initial_delay(visible_thinking=want_thinking))
        return jsonify(anthropic_api.build_nonstreaming_response(model, blocks))

    @stream_with_context
    def generate():
        for delay, sse in anthropic_api.stream_messages(model, blocks, clock):
            if delay > 0:
                time.sleep(delay)
            yield sse

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/v1/messages/count_tokens", methods=["POST"])
def v1_count_tokens() -> Response:
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages") or []
    # A deliberately rough, fake token estimate.
    chars = len(json.dumps(messages))
    return jsonify({"input_tokens": max(1, chars // 4)})


@app.route("/v1/models", methods=["GET"])
def v1_models() -> Response:
    return jsonify({
        "data": [
            {"type": "model", "id": DEFAULT_MODEL_ID,
             "display_name": MODEL_NAME,
             "created_at": "2024-01-01T00:00:00Z"},
        ],
        "has_more": False,
        "first_id": DEFAULT_MODEL_ID,
        "last_id": DEFAULT_MODEL_ID,
    })


@app.route("/v1/models/<model_id>", methods=["GET"])
def v1_model(model_id: str) -> Response:
    return jsonify({"type": "model", "id": model_id,
                    "display_name": MODEL_NAME,
                    "created_at": "2024-01-01T00:00:00Z"})


def main() -> None:
    """Console-script entry point (``gibberish``) used by uv."""
    host = os.environ.get("GIBBERISH_HOST", "127.0.0.1")
    port = int(os.environ.get("GIBBERISH_PORT", "5000"))
    debug = os.environ.get("GIBBERISH_DEBUG", "0") in ("1", "true", "yes")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
