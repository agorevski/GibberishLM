import unittest
from unittest.mock import patch

import anthropic_api


class ContinuationPlanningTests(unittest.TestCase):
    def plan(self, messages, tools=None):
        with patch("anthropic_api.random.random", return_value=0), \
                patch("anthropic_api.random.choice", return_value="echo hello"):
            return anthropic_api.plan_blocks(
                messages, tools or [{"name": "Bash"}],
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

    def test_copilot_tools_use_offered_names_and_valid_inputs(self):
        for name, expected_input in (
            ("bash", {"command": "echo hello",
                      "description": "Run a safe GibberishLM demo command"}),
            ("glob", {"pattern": "*"}),
            ("sql", {"description": "Run demo query", "query": "SELECT 1"}),
        ):
            with self.subTest(name=name):
                block = self.plan(
                    [{"role": "user", "content": "Use a tool"}],
                    tools=[{"name": name}],
                )[-1]
                self.assertEqual(block["type"], "tool_use")
                self.assertEqual(block["name"], name)
                self.assertEqual(block["input"], expected_input)

    def test_generated_content_is_half_length(self):
        with patch("anthropic_api.gibberishlm.thinking_text",
                   return_value="thought") as thinking, \
                patch("anthropic_api.gibberishlm._paragraph",
                      return_value="answer") as paragraph:
            anthropic_api.plan_blocks(
                [{"role": "user", "content": "Say hello"}], [],
                want_thinking=True, allow_tools=False, think_words=100,
            )

        thinking.assert_called_once_with(50)
        paragraph.assert_called_once_with(1, 2)

    def test_tool_result_in_non_user_message_is_not_a_continuation(self):
        self.assert_fresh_turn(self.plan([
            {"role": "user", "content": "Say hello"},
            {"role": "assistant", "content": [{"type": "tool_result"}]},
        ]))

    def test_empty_messages_allow_thinking_and_tool_use(self):
        self.assert_fresh_turn(self.plan([]))


if __name__ == "__main__":
    unittest.main()
