import unittest
from unittest.mock import patch

import anthropic_api


class ContinuationPlanningTests(unittest.TestCase):
    def plan(self, messages):
        with patch("anthropic_api.random.random", return_value=0), \
                patch("anthropic_api.random.choice", return_value="echo hello"):
            return anthropic_api.plan_blocks(
                messages, [{"name": "Bash"}],
                want_thinking=True, allow_tools=True, think_words=4,
            )

    def assert_fresh_turn(self, blocks):
        self.assertEqual([block["type"] for block in blocks],
                         ["thinking", "text", "tool_use"])
        self.assertEqual(blocks[-1]["name"], "Bash")
        self.assertEqual(blocks[-1]["input"]["command"], "echo hello")

    def test_historical_tool_result_does_not_suppress_fresh_user_turn(self):
        history = [
            {"role": "user", "content": "Run a command"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "toolu_1",
                 "input": {"command": "echo hello"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1",
                 "content": "hello"},
            ]},
            {"role": "assistant", "content": "Done"},
        ]
        for prompt in ("What next?", [{"type": "text", "text": "What next?"}]):
            with self.subTest(prompt=prompt):
                self.assert_fresh_turn(self.plan(
                    history + [{"role": "user", "content": prompt}]
                ))

    def test_latest_user_tool_result_suppresses_thinking_and_tool_use(self):
        messages = [
            {"role": "user", "content": "Run a command"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "id": "toolu_1",
                 "input": {"command": "echo hello"}},
            ]},
            {"role": "user", "content": [
                {"type": "text", "text": "Result:"},
                {"type": "tool_result", "tool_use_id": "toolu_1",
                 "content": "hello"},
            ]},
        ]
        self.assertEqual([block["type"] for block in self.plan(messages)],
                         ["text"])

    def test_regular_prompt_allows_thinking_and_tool_use(self):
        self.assert_fresh_turn(self.plan([
            {"role": "user", "content": "Say hello"},
        ]))

    def test_tool_result_in_non_user_message_is_not_a_continuation(self):
        self.assert_fresh_turn(self.plan([
            {"role": "user", "content": "Say hello"},
            {"role": "assistant", "content": [{"type": "tool_result"}]},
        ]))

    def test_empty_messages_allow_thinking_and_tool_use(self):
        self.assert_fresh_turn(self.plan([]))


if __name__ == "__main__":
    unittest.main()
