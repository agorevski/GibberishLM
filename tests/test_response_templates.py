import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as api_app
import response_templates


ROOT = Path(__file__).resolve().parent.parent


class ResponseTemplateTests(unittest.TestCase):
    def setUp(self):
        self.client = api_app.app.test_client()
        sleep = patch.object(api_app.time, "sleep", return_value=None)
        sleep.start()
        self.addCleanup(sleep.stop)

    def post(self, messages, tool, **overrides):
        body = {
            "messages": messages,
            "tools": [{"name": tool}],
            "thinking": {"type": "enabled"},
        }
        body.update(overrides)
        return self.client.post("/v1/messages", json=body)

    def test_example_templates_cover_three_user_prompts_and_continuations(self):
        for file, tool in (("copilot.yaml", "bash"), ("claude-code.yaml", "Bash")):
            with self.subTest(file=file), patch.object(
                api_app, "RESPONSE_TEMPLATE",
                response_templates.load_template(str(ROOT / "templates" / file))
            ):
                history = [{"role": "user", "content": "First prompt"}]
                first = self.post(history, tool).get_json()
                self.assertEqual(first["stop_reason"], "tool_use")
                self.assertIn("working tree", first["content"][0]["thinking"])
                calls = [block for block in first["content"]
                         if block["type"] == "tool_use"]
                self.assertEqual(len(calls), 2)
                self.assertEqual([block["name"] for block in calls],
                                 [tool, tool])
                self.assertNotEqual(calls[0]["id"], calls[1]["id"])
                self.assertEqual(
                    [call["input"]["command"] for call in calls],
                    ["git status --short", "ls -la"],
                )
                history.extend([
                    {"role": "assistant", "content": first["content"]},
                    {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": call["id"],
                         "content": "ok"} for call in calls
                    ]},
                ])
                final = self.post(history, tool).get_json()
                self.assertEqual([block["type"] for block in final["content"]],
                                 ["text"])
                self.assertIn("status", final["content"][0]["text"])
                self.assertEqual(final["stop_reason"], "end_turn")
                history.extend([
                    {"role": "assistant", "content": final["content"]},
                    {"role": "user", "content": "Second prompt"},
                ])
                second = self.post(history, tool).get_json()
                self.assertIn("test", second["content"][1]["text"])
                self.assertEqual(
                    [block["input"]["command"] for block in second["content"][2:]],
                    ["sed -n '1,160p' pyproject.toml",
                     "find tests -maxdepth 2 -type f"],
                )
                history.extend([
                    {"role": "assistant", "content": second["content"]},
                    {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": block["id"],
                         "content": "ok"}
                        for block in second["content"][2:]
                    ]},
                ])
                second_final = self.post(history, tool).get_json()
                self.assertIn("test", second_final["content"][0]["text"])
                history.extend([
                    {"role": "assistant", "content": second_final["content"]},
                    {"role": "user", "content": "Third prompt"},
                ])
                third = self.post(history, tool).get_json()
                self.assertIn("whitespace", third["content"][1]["text"])
                self.assertEqual(
                    [block["input"]["command"] for block in third["content"][2:]],
                    ["git diff --check", "git status --short"],
                )
                history.extend([
                    {"role": "assistant", "content": third["content"]},
                    {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": block["id"],
                         "content": "ok"}
                        for block in third["content"][2:]
                    ]},
                ])
                third_final = self.post(history, tool).get_json()
                self.assertEqual(third_final["stop_reason"], "end_turn")
                self.assertIn("whitespace", third_final["content"][0]["text"])
                history.extend([
                    {"role": "assistant", "content": third_final["content"]},
                    {"role": "user", "content": "Fourth prompt"},
                ])
                fourth = self.post(history, tool).get_json()
                self.assertNotIn("whitespace problems it checks",
                                 json.dumps(fourth["content"]))

    def test_streamed_template_and_token_budget(self):
        template = response_templates.load_template(
            str(ROOT / "templates" / "copilot.yaml")
        )
        with patch.object(api_app, "RESPONSE_TEMPLATE", template):
            response = self.post(
                [{"role": "user", "content": "Hello"}], "bash",
                thinking={"type": "disabled"}, tool_choice={"type": "none"},
                max_tokens=4, stream=True,
            )
        events = [json.loads(frame.split("\n", 1)[1][6:])
                  for frame in response.get_data(as_text=True).split("\n\n")
                  if frame]
        self.assertEqual(response.status_code, 200)
        deltas = [event["delta"] for event in events
                  if event["type"] == "content_block_delta"]
        self.assertEqual("".join(delta["text"] for delta in deltas
                                 if delta["type"] == "text_delta"),
                         "I'll first check")
        self.assertEqual(next(event["delta"]["stop_reason"] for event in events
                              if event["type"] == "message_delta"), "max_tokens")
        self.assertFalse(any(event.get("content_block", {}).get("type") == "tool_use"
                             for event in events))

    def test_unoffered_tool_is_explicit_error(self):
        template = response_templates.load_template(
            str(ROOT / "templates" / "claude-code.yaml")
        )
        with patch.object(api_app, "RESPONSE_TEMPLATE", template):
            response = self.post([{"role": "user", "content": "Hello"}], "bash")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Bash", response.get_json()["error"]["message"])

    def test_template_validation_rejects_invalid_or_missing_files(self):
        for source in (
            "messages: []",
            "messages: [{steps: [{text: hello, tool_calls: []}]}]",
            "messages: [{steps: [{text: hello}, {text: next}]}]",
            "messages: [{steps: [{tool_calls: [{name: Bash, input: []}]}]}]",
            "messages: [{steps: [{tool_calls: [{name: Bash, input: {a: .nan}}]}]}]",
            "messages: [{steps: [{text: 123}]}]",
            "messages: [",
        ):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "template.yaml"
                path.write_text(source, encoding="utf-8")
                with self.assertRaises(ValueError):
                    response_templates.load_template(str(path))
        with self.assertRaisesRegex(ValueError, "Cannot load"):
            response_templates.load_template("/nonexistent/template.yaml")

    def test_main_loads_configured_template_before_starting_server(self):
        path = str(ROOT / "templates" / "copilot.yaml")
        with patch.dict(api_app.os.environ, {"GIBBERISHLM_TEMPLATE": path}), \
                patch.object(api_app, "RESPONSE_TEMPLATE", None), \
                patch.object(api_app.app, "run") as run:
            api_app.main()
            self.assertEqual(len(api_app.RESPONSE_TEMPLATE), 3)
            run.assert_called_once()

    def test_turn_selection_is_per_conversation_and_ignores_system(self):
        template = response_templates.load_template(
            str(ROOT / "templates" / "copilot.yaml")
        )
        messages = [
            {"role": "system", "content": "instructions"},
            {"role": "user", "content": "first"},
        ]
        self.assertEqual(response_templates.select_step(template, messages),
                         template[0][0])
        self.assertEqual(response_templates.select_step(template, messages),
                         template[0][0])
        messages.extend([
            {"role": "assistant", "content": "tool call"},
            {"role": "user", "content": [
                {"type": "tool_result", "content": "done"}]},
        ])
        self.assertEqual(response_templates.select_step(template, messages),
                         template[0][1])
        messages.append({"role": "user", "content": "next"})
        self.assertEqual(response_templates.select_step(template, messages),
                         template[1][0])


if __name__ == "__main__":
    unittest.main()
