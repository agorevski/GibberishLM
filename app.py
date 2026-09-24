"""GibberishLM Anthropic-compatible API.

A faux Claude Opus 4.8 model that returns entirely fabricated agent output
(reasoning, bash tool calls, results, and lorem ipsum prose).

Nothing here connects to a real model. All output is fabricated nonsense.
"""

from __future__ import annotations

import os
import time

from flask import Flask, Response, jsonify, request, stream_with_context
from werkzeug.exceptions import BadRequest

import anthropic_api
import timing

app = Flask(__name__, static_folder=None)

MODEL_NAME = "Claude Opus 4.8 (GibberishLM Emulation)"

# Default model id reported to Anthropic API clients.
DEFAULT_MODEL_ID = os.environ.get(
    "GIBBERISHLM_MODEL_ID", "claude-opus-4-8-gibberishlm"
)

# Whether to emit fake Bash tool calls to Anthropic API clients. When enabled
# (default), the real Claude Code CLI will actually execute the harmless demo
# command (e.g. `echo "hello world"`). Set GIBBERISHLM_TOOLS=0 to disable.
ALLOW_TOOLS = os.environ.get("GIBBERISHLM_TOOLS", "1") not in ("0", "false", "no")


# ---------------------------------------------------------------------------
# Anthropic Messages API compatibility (for Claude Code and Copilot CLI).
#
# These endpoints make GibberishLM look like an Anthropic-compatible model
# provider. Point the CLI at GibberishLM with:
#     ANTHROPIC_BASE_URL=http://127.0.0.1:5000
# Authentication is intentionally NOT enforced — any API key is accepted.
# ---------------------------------------------------------------------------

def _wants_thinking(payload: dict) -> bool:
    thinking = payload.get("thinking")
    return isinstance(thinking, dict) and thinking.get("type") == "enabled"


def _invalid_request(message: str) -> Response:
    response = jsonify({
        "type": "error",
        "error": {"type": "invalid_request_error", "message": message},
    })
    response.status_code = 400
    return response


def _validate_blocks(content: object, field: str) -> str | None:
    if isinstance(content, str):
        return None
    if not isinstance(content, list):
        return f"{field} must be a string or an array of content blocks."
    for index, block in enumerate(content):
        if (
            not isinstance(block, dict)
            or not isinstance(block.get("type"), str)
            or not block["type"]
        ):
            return f"{field}[{index}] must be an object with a non-empty type."
    return None


def _validate_payload(payload: dict, *, allow_empty_messages: bool) -> str | None:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return "messages must be an array."
    if not messages and not allow_empty_messages:
        return "messages must be a non-empty array."
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            return f"messages[{index}] must be an object."
        if message.get("role") not in ("user", "assistant", "system"):
            return (
                f"messages[{index}].role must be 'user', 'assistant', or "
                "'system'."
            )
        error = _validate_blocks(message.get("content"), f"messages[{index}].content")
        if error:
            return error

    if "system" in payload:
        error = _validate_blocks(payload["system"], "system")
        if error:
            return error

    if "tools" in payload:
        tools = payload["tools"]
        if not isinstance(tools, list):
            return "tools must be an array."
        for index, tool in enumerate(tools):
            if (
                not isinstance(tool, dict)
                or not isinstance(tool.get("name"), str)
                or not tool["name"]
            ):
                return f"tools[{index}] must be an object with a non-empty name."

    if "model" in payload and (
        not isinstance(payload["model"], str) or not payload["model"]
    ):
        return "model must be a non-empty string."
    if "stream" in payload and not isinstance(payload["stream"], bool):
        return "stream must be a boolean."

    if "thinking" in payload:
        thinking = payload["thinking"]
        if not isinstance(thinking, dict) or thinking.get("type") not in (
            "enabled", "disabled", "adaptive"
        ):
            return "thinking must be an object with type 'enabled', 'disabled', or 'adaptive'."
        if "budget_tokens" in thinking and (
            type(thinking["budget_tokens"]) is not int or thinking["budget_tokens"] <= 0
        ):
            return "thinking.budget_tokens must be a positive integer."

    if "tool_choice" in payload and payload["tool_choice"] is not None:
        choice = payload["tool_choice"]
        if not isinstance(choice, dict) or choice.get("type") not in (
            "auto", "any", "tool", "none"
        ):
            return "tool_choice must be an object with type 'auto', 'any', 'tool', or 'none'."
        if choice["type"] == "tool" and (
            not isinstance(choice.get("name"), str) or not choice["name"]
        ):
            return "tool_choice.name must be a non-empty string for type 'tool'."
    return None


def _request_payload(
    *, allow_empty_messages: bool
) -> tuple[dict | None, Response | None]:
    if not request.is_json:
        return None, _invalid_request("Content-Type must be application/json.")
    try:
        payload = request.get_json()
    except BadRequest:
        return None, _invalid_request("Malformed JSON request body.")
    if not isinstance(payload, dict):
        return None, _invalid_request("Request body must be a JSON object.")
    error = _validate_payload(payload, allow_empty_messages=allow_empty_messages)
    if error:
        return None, _invalid_request(error)
    return payload, None


@app.route("/v1/messages", methods=["POST"])
def v1_messages() -> Response:
    payload, error = _request_payload(allow_empty_messages=False)
    if error is not None:
        return error
    if "max_tokens" in payload and (
        type(payload["max_tokens"]) is not int or payload["max_tokens"] <= 0
    ):
        return _invalid_request("max_tokens must be a positive integer.")
    model = payload.get("model") or DEFAULT_MODEL_ID
    messages = payload["messages"]
    tools = payload.get("tools", [])
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
    response_plan = anthropic_api.prepare_response(
        messages, blocks, payload.get("max_tokens")
    )

    if not payload.get("stream"):
        # Non-streaming clients still wait a realistic, variable amount of time.
        time.sleep(clock.initial_delay(visible_thinking=want_thinking))
        return jsonify(anthropic_api.build_nonstreaming_response(model, response_plan))

    @stream_with_context
    def generate():
        for delay, sse in anthropic_api.stream_messages(model, response_plan, clock):
            if delay > 0:
                time.sleep(delay)
            yield sse

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/v1/messages/count_tokens", methods=["POST"])
def v1_count_tokens() -> Response:
    payload, error = _request_payload(allow_empty_messages=True)
    if error is not None:
        return error
    return jsonify({
        "input_tokens": anthropic_api.estimate_input_tokens(payload["messages"])
    })


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
    """Console-script entry point (``gibberishlm``) used by uv."""
    host = os.environ.get("GIBBERISHLM_HOST", "127.0.0.1")
    port = int(os.environ.get("GIBBERISHLM_PORT", "5000"))
    debug = os.environ.get("GIBBERISHLM_DEBUG", "0") in ("1", "true", "yes")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
