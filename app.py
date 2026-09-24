"""Gibberish Anthropic-compatible API.

A faux Claude Opus 4.8 model that returns entirely fabricated agent output
(reasoning, bash tool calls, results, and lorem ipsum prose).

Nothing here connects to a real model. All output is gibberish by design.
"""

from __future__ import annotations

import json
import os
import time

from flask import Flask, Response, jsonify, request, stream_with_context

import anthropic_api
import timing

app = Flask(__name__, static_folder=None)

MODEL_NAME = "Claude Opus 4.8 (Gibberish Emulation)"

# Default model id reported to Anthropic API clients.
DEFAULT_MODEL_ID = os.environ.get(
    "GIBBERISH_MODEL_ID", "claude-opus-4-8-gibberish"
)

# Whether to emit fake Bash tool calls to Anthropic API clients. When enabled
# (default), the real Claude Code CLI will actually execute the harmless demo
# command (e.g. `echo "hello world"`). Set GIBBERISH_TOOLS=0 to disable.
ALLOW_TOOLS = os.environ.get("GIBBERISH_TOOLS", "1") not in ("0", "false", "no")


# ---------------------------------------------------------------------------
# Anthropic Messages API compatibility (for Claude Code and Copilot CLI).
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
    tool_choice = payload.get("tool_choice")
    allow_tools = ALLOW_TOOLS and not (
        isinstance(tool_choice, dict) and tool_choice.get("type") == "none"
    )

    clock = timing.RequestTiming(want_thinking=want_thinking)
    blocks = anthropic_api.plan_blocks(
        messages, tools, want_thinking, allow_tools,
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
