import json
import unittest
from unittest.mock import patch

import anthropic_api
import app as api_app


_OMITTED = object()


class TokenBudgetTests(unittest.TestCase):
    def setUp(self):
        self.client = api_app.app.test_client()
        sleep = patch.object(api_app.time, "sleep", return_value=None)
        sleep.start()
        self.addCleanup(sleep.stop)
        self.messages = [{"role": "user", "content": "A predictable prompt"}]

    def body(self, max_tokens=_OMITTED, **overrides):
        body = {"messages": self.messages, "tool_choice": {"type": "none"}}
        if max_tokens is not _OMITTED:
            body["max_tokens"] = max_tokens
        body.update(overrides)
        return body

    def events(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/event-stream")
        events = []
        for frame in response.get_data(as_text=True).split("\n\n"):
            if frame:
                event, data = frame.split("\n", 1)
                events.append((event.removeprefix("event: "),
                               json.loads(data.removeprefix("data: "))))
        return events

    def streamed_content(self, events):
        content = []
        pending = {}
        for event, data in events:
            if event == "content_block_start":
                index = data["index"]
                self.assertEqual(index, len(content))
                block = data["content_block"].copy()
                pending[index] = (block, [])
            elif event == "content_block_delta":
                block, json_parts = pending[data["index"]]
                delta = data["delta"]
                if delta["type"] == "text_delta":
                    block["text"] += delta["text"]
                elif delta["type"] == "thinking_delta":
                    block["thinking"] += delta["thinking"]
                elif delta["type"] == "signature_delta":
                    block["signature"] = delta["signature"]
                elif delta["type"] == "input_json_delta":
                    json_parts.append(delta["partial_json"])
                else:
                    self.fail(f"Unknown delta: {delta}")
            elif event == "content_block_stop":
                block, json_parts = pending.pop(data["index"])
                if block["type"] == "tool_use":
                    block["input"] = json.loads("".join(json_parts))
                content.append(block)
        self.assertFalse(pending)
        return content

    def assert_pair(self, blocks, max_tokens=_OMITTED, **overrides):
        body = self.body(max_tokens, **overrides)
        with patch.object(anthropic_api, "plan_blocks", return_value=blocks), \
                patch.object(anthropic_api, "_fake_signature",
                             return_value="fixture-signature"):
            response = self.client.post("/v1/messages", json=body)
            stream = self.client.post(
                "/v1/messages", json={**body, "stream": True}
            )
        self.assertEqual(response.status_code, 200)
        message = response.get_json()
        events = self.events(stream)
        self.assertEqual(events[0][0], "message_start")
        self.assertEqual(events[-1][0], "message_stop")
        start = events[0][1]["message"]
        delta = next(data for event, data in events if event == "message_delta")
        self.assertEqual(self.streamed_content(events), message["content"])
        self.assertEqual(delta["delta"]["stop_reason"], message["stop_reason"])
        self.assertEqual(start["usage"]["input_tokens"],
                         message["usage"]["input_tokens"])
        self.assertEqual(start["usage"]["output_tokens"], 0)
        self.assertEqual(delta["usage"]["output_tokens"],
                         message["usage"]["output_tokens"])
        if max_tokens is not _OMITTED:
            self.assertLessEqual(message["usage"]["output_tokens"], max_tokens)
        return message

    def test_one_token_truncates_text_in_both_formats(self):
        message = self.assert_pair([{"type": "text", "text": "abcdefghijk"}], 1)
        self.assertEqual(message["content"], [{"type": "text", "text": "abcd"}])
        self.assertEqual(message["usage"]["output_tokens"], 1)
        self.assertEqual(message["stop_reason"], "max_tokens")

    def test_exact_boundary_does_not_claim_truncation(self):
        blocks = [{"type": "text", "text": "abcdefgh"},
                  {"type": "text", "text": "ijkl"}]
        complete = self.assert_pair(blocks, 3)
        self.assertEqual(complete["content"], blocks)
        self.assertEqual(complete["usage"]["output_tokens"], 3)
        self.assertEqual(complete["stop_reason"], "end_turn")

        omitted = self.assert_pair(blocks, 2)
        self.assertEqual(omitted["content"], blocks[:1])
        self.assertEqual(omitted["usage"]["output_tokens"], 2)
        self.assertEqual(omitted["stop_reason"], "max_tokens")

    def test_omitted_budget_keeps_all_blocks_and_counts_emitted_content(self):
        blocks = [{"type": "text", "text": "hello world"},
                  {"type": "text", "text": "another response"}]
        message = self.assert_pair(blocks)
        expected_tokens = sum((len(block["text"]) + 3) // 4 for block in blocks)
        self.assertEqual(message["content"], blocks)
        self.assertEqual(message["usage"]["output_tokens"], expected_tokens)
        self.assertEqual(message["stop_reason"], "end_turn")

    def test_tool_call_is_all_or_nothing(self):
        tool = {"type": "tool_use", "id": "toolu_test", "name": "Bash",
                "input": {"command": "echo " + "lots of text " * 20}}
        blocks = [{"type": "text", "text": "abcd"}, tool]
        excluded = self.assert_pair(blocks, 2)
        self.assertEqual(excluded["content"], blocks[:1])
        self.assertEqual(excluded["stop_reason"], "max_tokens")
        self.assertEqual(excluded["usage"]["output_tokens"], 1)

        tool_tokens = (len(json.dumps(tool, sort_keys=True)) + 3) // 4
        included = self.assert_pair(blocks, 1 + tool_tokens)
        self.assertEqual(included["content"], blocks)
        self.assertEqual(included["stop_reason"], "tool_use")
        self.assertEqual(included["usage"]["output_tokens"], 1 + tool_tokens)

        unbounded = self.assert_pair(blocks)
        self.assertEqual(unbounded["content"], blocks)
        self.assertEqual(unbounded["stop_reason"], "tool_use")
        self.assertEqual(unbounded["usage"]["output_tokens"], 1 + tool_tokens)

    def test_thinking_is_truncated_before_later_text(self):
        blocks = [{"type": "thinking", "text": "reasoning takes time"},
                  {"type": "text", "text": "Not emitted"}]
        message = self.assert_pair(blocks, 1, thinking={"type": "enabled"})
        self.assertEqual(message["content"], [
            {"type": "thinking", "thinking": "reas",
             "signature": "fixture-signature"},
        ])
        self.assertEqual(message["usage"]["output_tokens"], 1)
        self.assertEqual(message["stop_reason"], "max_tokens")

        complete = self.assert_pair(blocks, thinking={"type": "enabled"})
        self.assertEqual(complete["content"][0]["thinking"], blocks[0]["text"])
        self.assertEqual(complete["content"][1]["text"], blocks[1]["text"])
        self.assertEqual(complete["usage"]["output_tokens"],
                         (len(blocks[0]["text"]) + 3) // 4
                         + (len(blocks[1]["text"]) + 3) // 4)

    def test_unicode_text_truncates_at_character_boundary(self):
        message = self.assert_pair([{"type": "text", "text": "🍀🙂é中abc"}], 1)
        self.assertEqual(message["content"], [{"type": "text", "text": "🍀🙂é中"}])
        self.assertEqual(message["usage"]["output_tokens"], 1)

    def test_missing_and_invalid_max_tokens(self):
        for stream in (False, True):
            for value in (None, 0, -1, True, False, 1.5, "1", [], {}):
                with self.subTest(stream=stream, value=value):
                    with patch.object(anthropic_api, "plan_blocks") as planner:
                        response = self.client.post(
                            "/v1/messages", json=self.body(value, stream=stream)
                        )
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.mimetype, "application/json")
                    self.assertEqual(response.get_json()["type"], "error")
                    self.assertEqual(response.get_json()["error"]["type"],
                                     "invalid_request_error")
                    self.assertIn("max_tokens",
                                  response.get_json()["error"]["message"])
                    planner.assert_not_called()

        self.assert_pair([{"type": "text", "text": "hello"}])

    def test_message_input_usage_matches_count_tokens(self):
        messages = [
            {"role": "user", "content": "a longer first prompt"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "a previous reply"},
            ]},
            {"role": "user", "content": "a follow-up"},
        ]
        body = self.body(1, messages=messages)
        tokens = self.client.post("/v1/messages/count_tokens", json=body)
        self.assertEqual(tokens.status_code, 200)
        expected = max(1, len(json.dumps(messages)) // 4)
        self.assertEqual(tokens.get_json()["input_tokens"], expected)
        message = self.assert_pair(
            [{"type": "text", "text": "more than four characters"}],
            1, messages=messages,
        )
        self.assertEqual(message["usage"]["input_tokens"], expected)


if __name__ == "__main__":
    unittest.main()
