"""Validated YAML response scripts for Anthropic Messages requests."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from anthropic_api import _tool_id


def load_template(path: str) -> tuple[tuple[dict, ...], ...]:
    """Load zero-based user turns, each containing one or more response steps."""
    try:
        with Path(path).open(encoding="utf-8") as source:
            document = yaml.safe_load(source)
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot load response template {path}: {exc}") from exc

    if not isinstance(document, dict) or set(document) != {"messages"}:
        raise ValueError("Response template must contain only a 'messages' list.")
    messages = document["messages"]
    if not isinstance(messages, list) or not messages:
        raise ValueError("Response template 'messages' must be a non-empty list.")

    result = []
    for turn_index, turn in enumerate(messages):
        label = f"messages[{turn_index}]"
        if not isinstance(turn, dict) or set(turn) != {"steps"}:
            raise ValueError(f"{label} must contain only a 'steps' list.")
        steps = turn["steps"]
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"{label}.steps must be a non-empty list.")
        checked_steps = []
        for step_index, step in enumerate(steps):
            where = f"{label}.steps[{step_index}]"
            if not isinstance(step, dict) or not step or set(step) - {
                "thinking", "text", "tool_calls"
            }:
                raise ValueError(f"{where} must contain thinking, text, or tool_calls.")
            for field in ("thinking", "text"):
                if field in step and not isinstance(step[field], str):
                    raise ValueError(f"{where}.{field} must be a string.")
            if "tool_calls" in step:
                calls = step["tool_calls"]
                if not isinstance(calls, list) or not calls:
                    raise ValueError(f"{where}.tool_calls must be a non-empty list.")
                for call_index, call in enumerate(calls):
                    call_where = f"{where}.tool_calls[{call_index}]"
                    if (
                        not isinstance(call, dict)
                        or set(call) != {"name", "input"}
                        or not isinstance(call["name"], str)
                        or not call["name"]
                        or not isinstance(call["input"], dict)
                    ):
                        raise ValueError(
                            f"{call_where} must contain a tool name and object input."
                        )
                    try:
                        json.dumps(call["input"], allow_nan=False)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            f"{call_where}.input must contain JSON-compatible values."
                        ) from exc
            if step_index < len(steps) - 1 and not step.get("tool_calls"):
                raise ValueError(f"{where} must have tool_calls before another step.")
            checked_steps.append(step)
        result.append(tuple(checked_steps))
    return tuple(result)


def select_step(
    template: tuple[tuple[dict, ...], ...], messages: list[dict]
) -> dict | None:
    """Select a step from conversation history, not process-global request state."""
    turn_index = -1
    step_index = 0
    for message in messages:
        if message["role"] == "user":
            content = message["content"]
            is_tool_result = isinstance(content, list) and any(
                block["type"] == "tool_result" for block in content
            )
            if not is_tool_result:
                turn_index += 1
                step_index = 0
        elif message["role"] == "assistant" and turn_index >= 0:
            step_index += 1
    if 0 <= turn_index < len(template) and step_index < len(template[turn_index]):
        return template[turn_index][step_index]
    return None


def plan_step(
    step: dict, tools: list[dict], want_thinking: bool, allow_tools: bool
) -> list[dict]:
    """Convert a validated step to the existing response-planning block format."""
    blocks = []
    if want_thinking and "thinking" in step:
        blocks.append({"type": "thinking", "text": step["thinking"]})
    if "text" in step:
        blocks.append({"type": "text", "text": step["text"]})
    if allow_tools:
        offered = {tool["name"] for tool in tools}
        for call in step.get("tool_calls", []):
            if call["name"] not in offered:
                raise ValueError(f"Template tool '{call['name']}' was not offered by the client.")
            blocks.append({
                "type": "tool_use", "id": _tool_id(),
                "name": call["name"], "input": call["input"].copy(),
            })
    if not blocks:
        raise ValueError("Template step has no content under the current request settings.")
    return blocks
