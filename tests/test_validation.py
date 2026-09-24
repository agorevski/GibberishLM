import unittest
from unittest.mock import patch

import app as api_app


class RequestValidationTests(unittest.TestCase):
    endpoints = ("/v1/messages", "/v1/messages/count_tokens")

    def setUp(self):
        self.client = api_app.app.test_client()
        sleep = patch.object(api_app.time, "sleep", return_value=None)
        sleep.start()
        self.addCleanup(sleep.stop)

    def body(self, **overrides):
        body = {"messages": [{"role": "user", "content": "Hello"}]}
        body.update(overrides)
        return body

    def assert_invalid(self, response, field):
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.is_json)
        self.assertEqual(response.get_json()["type"], "error")
        error = response.get_json()["error"]
        self.assertEqual(error["type"], "invalid_request_error")
        self.assertIn(field, error["message"])

    def test_malformed_json_and_wrong_content_type(self):
        for endpoint in self.endpoints:
            with self.subTest(endpoint=endpoint, case="malformed"):
                self.assert_invalid(
                    self.client.post(
                        endpoint, data='{"messages": [', content_type="application/json"
                    ),
                    "Malformed JSON",
                )
            with self.subTest(endpoint=endpoint, case="wrong content type"):
                self.assert_invalid(
                    self.client.post(
                        endpoint, data='{"messages": []}', content_type="text/plain"
                    ),
                    "Content-Type",
                )

    def test_body_must_be_an_object(self):
        for endpoint in self.endpoints:
            for body in ("null", "[]", '"hello"', "123", "false"):
                with self.subTest(endpoint=endpoint, body=body):
                    self.assert_invalid(
                        self.client.post(
                            endpoint, data=body, content_type="application/json"
                        ),
                        "JSON object",
                    )

    def test_invalid_messages(self):
        invalid = (
            ({}, "messages"),
            ({"messages": None}, "messages"),
            ({"messages": "hello"}, "messages"),
            ({"messages": [None]}, "messages[0]"),
            ({"messages": [{"role": "tool", "content": "hello"}]}, "role"),
            ({"messages": [{"role": "user"}]}, "content"),
            ({"messages": [{"role": "user", "content": 42}]}, "content"),
            ({"messages": [{"role": "user", "content": ["hello"]}]}, "content[0]"),
            ({"messages": [{"role": "user", "content": [{}]}]}, "content[0]"),
            ({"messages": [{"role": "user", "content": [{"type": 1}]}]}, "content[0]"),
        )
        for endpoint in self.endpoints:
            for body, field in invalid:
                with self.subTest(endpoint=endpoint, body=body):
                    self.assert_invalid(self.client.post(endpoint, json=body), field)

    def test_empty_messages_only_allowed_for_count_tokens(self):
        self.assert_invalid(
            self.client.post("/v1/messages", json={"messages": []}), "non-empty"
        )
        response = self.client.post(
            "/v1/messages/count_tokens", json={"messages": []}
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.get_json()["input_tokens"], 0)

    def test_invalid_tools(self):
        for endpoint in self.endpoints:
            for tools in (None, {}, "Bash", [None], [{}], [{"name": ""}],
                          [{"name": 123}], [{"name": "Bash"}, []]):
                with self.subTest(endpoint=endpoint, tools=tools):
                    self.assert_invalid(
                        self.client.post(endpoint, json=self.body(tools=tools)),
                        "tools",
                    )

    def test_invalid_optional_fields(self):
        invalid = (
            ({"model": []}, "model"),
            ({"model": ""}, "model"),
            ({"stream": "false"}, "stream"),
            ({"thinking": []}, "thinking"),
            ({"thinking": {"type": "unknown"}}, "thinking"),
            ({"thinking": {"type": "enabled", "budget_tokens": True}}, "budget_tokens"),
            ({"tool_choice": "none"}, "tool_choice"),
            ({"tool_choice": {"type": "unknown"}}, "tool_choice"),
            ({"tool_choice": {"type": "tool"}}, "tool_choice.name"),
            ({"system": [None]}, "system"),
        )
        for endpoint in self.endpoints:
            for overrides, field in invalid:
                with self.subTest(endpoint=endpoint, overrides=overrides):
                    self.assert_invalid(
                        self.client.post(endpoint, json=self.body(**overrides)), field
                    )

    def test_valid_tool_result_continuation(self):
        messages = [
            {"role": "user", "content": "Run a command"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "toolu_123", "name": "Bash",
                 "input": {"command": "echo ok"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_123",
                 "content": [{"type": "text", "text": "ok"}]},
            ]},
        ]
        body = self.body(
            messages=messages,
            tools=[{"name": "Bash", "input_schema": {"type": "object"}}],
            thinking={"type": "enabled", "budget_tokens": 1024},
            system=[{"type": "text", "text": "Be concise",
                     "cache_control": {"type": "ephemeral"}}],
            tool_choice={"type": "auto"},
            model=api_app.DEFAULT_MODEL_ID,
        )
        for endpoint in self.endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, json=body)
                self.assertEqual(response.status_code, 200)
                if endpoint == "/v1/messages":
                    self.assertEqual(response.get_json()["stop_reason"], "end_turn")
                else:
                    self.assertGreater(response.get_json()["input_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
