import json
import unittest
from unittest.mock import patch

import app as api_app


class MessagesApiTests(unittest.TestCase):
    def setUp(self):
        self.client = api_app.app.test_client()
        self.sleep = patch.object(api_app.time, "sleep", return_value=None)
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def request_body(self, **overrides):
        body = {
            "model": api_app.DEFAULT_MODEL_ID,
            "max_tokens": 128,
            "messages": [{"role": "user", "content": "Say hello"}],
            "tool_choice": {"type": "none"},
        }
        body.update(overrides)
        return body

    def stream_events(self, response):
        events = []
        for frame in response.get_data(as_text=True).split("\n\n"):
            if not frame:
                continue
            event, data = frame.split("\n", 1)
            self.assertTrue(event.startswith("event: "))
            self.assertTrue(data.startswith("data: "))
            events.append((event[7:], json.loads(data[6:])))
        return events

    def test_nonstreaming_message(self):
        response = self.client.post("/v1/messages", json=self.request_body())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        message = response.get_json()
        self.assertEqual(message["type"], "message")
        self.assertEqual(message["role"], "assistant")
        self.assertEqual(message["model"], api_app.DEFAULT_MODEL_ID)
        self.assertEqual(message["stop_reason"], "end_turn")
        self.assertTrue(any(block["type"] == "text" and block["text"]
                            for block in message["content"]))
        self.assertFalse(any(block["type"] == "tool_use"
                             for block in message["content"]))

    def test_streaming_message(self):
        response = self.client.post(
            "/v1/messages", json=self.request_body(stream=True)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        events = self.stream_events(response)
        self.assertEqual(events[0][0], "message_start")
        self.assertEqual(events[0][1]["message"]["model"],
                         api_app.DEFAULT_MODEL_ID)
        self.assertEqual(events[-1][0], "message_stop")
        self.assertIn("content_block_start", [event for event, _ in events])
        self.assertIn("content_block_delta", [event for event, _ in events])
        self.assertEqual(
            next(data["delta"]["stop_reason"] for event, data in events
                 if event == "message_delta"), "end_turn"
        )

    def test_tool_choice_none_suppresses_offered_bash_tool(self):
        tools = [{"name": "Bash", "description": "Run a shell command",
                  "input_schema": {"type": "object"}}]
        with patch.object(api_app, "ALLOW_TOOLS", True), \
                patch("anthropic_api.random.random", return_value=0):
            response = self.client.post(
                "/v1/messages", json=self.request_body(tools=tools)
            )
            stream = self.client.post(
                "/v1/messages",
                json=self.request_body(tools=tools, stream=True),
            )

        self.assertEqual(response.get_json()["stop_reason"], "end_turn")
        self.assertFalse(any(block["type"] == "tool_use"
                             for block in response.get_json()["content"]))
        events = self.stream_events(stream)
        self.assertFalse(any(
            data.get("content_block", {}).get("type") == "tool_use"
            for event, data in events if event == "content_block_start"
        ))
        self.assertEqual(
            next(data["delta"]["stop_reason"] for event, data in events
                 if event == "message_delta"), "end_turn"
        )

    def test_offered_bash_tool_can_be_emitted_when_allowed(self):
        tools = [{"name": "Bash", "description": "Run a shell command",
                  "input_schema": {"type": "object"}}]
        with patch.object(api_app, "ALLOW_TOOLS", True), \
                patch("anthropic_api.random.random", return_value=0):
            response = self.client.post(
                "/v1/messages",
                json=self.request_body(tools=tools, tool_choice=None),
            )

        self.assertEqual(response.status_code, 200)
        message = response.get_json()
        self.assertEqual(message["stop_reason"], "tool_use")
        self.assertEqual(
            next(block["name"] for block in message["content"]
                 if block["type"] == "tool_use"), "Bash"
        )

    def test_model_listing_and_token_count(self):
        listing = self.client.get("/v1/models")
        model = self.client.get(f"/v1/models/{api_app.DEFAULT_MODEL_ID}")
        tokens = self.client.post(
            "/v1/messages/count_tokens",
            json={"messages": self.request_body()["messages"]},
        )

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.get_json()["data"][0]["id"],
                         api_app.DEFAULT_MODEL_ID)
        self.assertEqual(model.status_code, 200)
        self.assertEqual(model.get_json()["id"], api_app.DEFAULT_MODEL_ID)
        self.assertEqual(tokens.status_code, 200)
        self.assertGreater(tokens.get_json()["input_tokens"], 0)

    def test_browser_routes_are_not_served(self):
        for path in ("/", "/static/app.js"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(
            self.client.post("/api/stream", json={"prompt": "hello"}).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
