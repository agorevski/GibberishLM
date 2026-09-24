# LoremOpus API runbook

LoremOpus serves locally generated nonsense through a subset of the Anthropic
Messages API. Use the launchers for a temporary server connected to Claude Code
or GitHub Copilot CLI, or start the service manually for direct API calls. The
backend has no real model or hosted inference dependency; installing third-party
CLIs and packages may require network access.

## 0. Prerequisites

| Tool | Why | Check |
|------|-----|-------|
| Python 3.10+ | Project runtime | `python3 --version` |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Installs/runs the locked project | `uv --version` |
| Bash + `curl` | Needed by the CLI launchers | `bash --version` / `curl --version` |
| Node.js + npm | Needed to install the CLIs, not to serve the API | `node --version` / `npm --version` |

---

## 1. Start the service manually (optional)

From the project root:

```bash
# Install dependencies into a project-local virtualenv (.venv)
uv sync --locked

# Run on http://127.0.0.1:5000 without offering tool calls
LOREMOPUS_TOOLS=0 uv run --locked loremopus
```

You should see Flask serving on `http://127.0.0.1:5000`. There is no browser
page: call the `/v1` API (section 3) or use a launcher (section 2), which
starts and stops its **own** server. Do not start a manual server on the same
port as a launcher.

### Configuration (environment variables)

| Variable           | Default                      | Purpose                                            |
|--------------------|------------------------------|----------------------------------------------------|
| `LOREMOPUS_HOST`   | `127.0.0.1`                  | Bind address                                       |
| `LOREMOPUS_PORT`   | `5000`                       | Bind port (launcher accepts 1–65535)              |
| `LOREMOPUS_MODEL_ID` | `claude-opus-4-8-loremopus` | Model id reported to API clients                  |
| `LOREMOPUS_TOOLS`  | `1` standalone, `0` in launchers | `0` disables Bash tool-use requests; `1` allows them when a client offers `Bash` |
| `LOREMOPUS_DEBUG`  | `0`                          | `1` enables Flask debug/reloader                   |

The launchers force `LOREMOPUS_HOST=127.0.0.1` and `LOREMOPUS_DEBUG=0`.
`LOREMOPUS_PORT`, `LOREMOPUS_MODEL_ID`, and `LOREMOPUS_TOOLS` can be set for
either launcher. `LOREMOPUS_STARTUP_TIMEOUT` controls how long a launcher waits
for the API to respond (default: 60 seconds; allowed range: 1–999).

#### Response-timing knobs

LoremOpus deliberately streams slowly, with a variable time-to-first-token and a
variable "thinking" phase. Tune it with:

| Variable                  | Default | Purpose                                             |
|---------------------------|---------|-----------------------------------------------------|
| `LOREMOPUS_SPEED`         | `1.0`   | Global multiplier on every delay (`0.2` = fast demo)|
| `LOREMOPUS_TEXT_TPS`      | `38`    | Answer streaming rate (tokens/sec)                  |
| `LOREMOPUS_THINK_TPS`     | `48`    | Thinking streaming rate (tokens/sec)                |
| `LOREMOPUS_TOOL_TPS`      | `85`    | Tool-request streaming rate (tokens/sec)            |
| `LOREMOPUS_TTFT_MIN/MAX`  | `1.0`/`4.0` | Time-to-first-token range (seconds)             |
| `LOREMOPUS_THINK_MIN/MAX` | `2.5`/`12.0` | Thinking-phase budget range (seconds)          |
| `LOREMOPUS_HIDDEN_THINK_CAP` | `6.0` | Max silent deliberation when thinking isn't shown  |

Durations vary with the sampled pauses and amount of generated content.

For a snappier demo:

```bash
LOREMOPUS_SPEED=0.25 ./scripts/run-claude.sh -p "Say hello"
```

Example on a custom port:

```bash
LOREMOPUS_PORT=5050 ./scripts/run-copilot.sh -p "Say hello"
```

### Verify it's up

```bash
curl -fsS http://127.0.0.1:5000/v1/models | python3 -m json.tool
```

Use the configured port (e.g. `5050`) instead of `5000` if it was changed.
You should get a JSON model list containing `claude-opus-4-8-loremopus`.

---

## 2. Launch a CLI and a temporary server

You do not need to export API variables or leave a separate server running.
Install the CLI(s) you want and run the corresponding executable script from
the project root:

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @github/copilot
uv sync --locked

./scripts/run-claude.sh -p "Say hello"
# Or:
./scripts/run-copilot.sh -p "Say hello"
```

Install only the CLI you plan to use. Omit `-p "Say hello"` to run it
interactively; pass any other CLI arguments after the script name. On Windows,
run these Bash launchers in an environment with Bash, `curl`, and `uv` (for
example, WSL). For a different port:

```bash
LOREMOPUS_PORT=5050 ./scripts/run-copilot.sh -p "Say hello"
```

Each script launches LoremOpus bound to loopback, waits for `/v1/models` to
respond, then runs the chosen CLI. The server runs in the background **only
while that CLI session is running**; on exit or interruption the script stops
its server. If a service already answers on the chosen port, use another port
instead of reusing it. Launcher settings are passed to child processes and do
not overwrite your persistent Claude/Copilot configuration. The server starts
with `uv run --locked` from the project root; its temporary startup log lives
under `TMPDIR` (or the system default) rather than in the checkout and is
removed on exit. A first run still needs a writable uv environment/cache, even
if the checkout itself is read-only.

The Claude launcher sets `ANTHROPIC_BASE_URL`, a dummy `ANTHROPIC_API_KEY`, the
fake `ANTHROPIC_MODEL`, and
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`; it removes potentially
conflicting Anthropic-token and cloud-provider settings for that invocation.

The Copilot launcher configures Anthropic BYOK via `COPILOT_PROVIDER_TYPE`,
`COPILOT_PROVIDER_BASE_URL`, and a dummy `COPILOT_PROVIDER_API_KEY`. It defaults
`COPILOT_OFFLINE` to `true` and routes the actual request model via
`COPILOT_PROVIDER_WIRE_MODEL` to LoremOpus's model ID. Its
`COPILOT_MODEL=claude-sonnet-4` is a CLI-facing model selection, **not** a real
model served by LoremOpus. Both launchers use `LOREMOPUS_MODEL_ID` if you
override the default wire model ID.

To re-enable Copilot's GitHub, MCP, web, and other network capabilities, run:

```bash
COPILOT_OFFLINE=false ./scripts/run-copilot.sh -p "Say hello"
```

The BYOK provider and wire model remain pointed at the local LoremOpus server
for inference, but the **CLI session is not offline** when this is set to
`false`. Leave the default in place if you do not want those additional
network capabilities.

Tool-use requests are **off by default in both launchers**. To opt in:

```bash
LOREMOPUS_TOOLS=1 ./scripts/run-claude.sh -p "Run a demo command"
```

When enabled, the API may emit a `Bash` tool-use request if the client offers
that tool; the CLI can actually execute a command if you approve it. LoremOpus
does not execute the command itself. Read the command and keep normal CLI
permission prompts in place. You can also send `"tool_choice":{"type":"none"}`
in an API request to suppress tool calls regardless of the server setting.

---

## 3. Make direct API requests

Start the service manually as in section 1. For a non-streaming response:

```bash
curl -fsS http://127.0.0.1:5000/v1/messages \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: local-loremopus' \
  -d '{"model":"claude-opus-4-8-loremopus","max_tokens":128,"messages":[{"role":"user","content":"Say hello"}],"tool_choice":{"type":"none"}}'
```

For Anthropic-style Server-Sent Events (SSE), add `"stream":true`:

```bash
curl -NfsS http://127.0.0.1:5000/v1/messages \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: local-loremopus' \
  -d '{"model":"claude-opus-4-8-loremopus","max_tokens":128,"messages":[{"role":"user","content":"Say hello"}],"tool_choice":{"type":"none"},"stream":true}'
```

The `x-api-key` shown here is a dummy value: the demo accepts requests
without authentication. Response timing is deliberately variable, so streaming
may pause before the first content event. If you chose a custom port, replace
`5000` in the URL.

Implemented endpoints:

- `POST /v1/messages` — JSON response or SSE
  (`message_start`, `content_block_*`, `message_delta`, `message_stop`).
- `POST /v1/messages/count_tokens` — approximate, fabricated token count.
- `GET /v1/models`, `GET /v1/models/<id>` — fake model metadata.

There is no homepage, frontend, or `/api/stream` browser endpoint. This is a
subset of the Anthropic API for a local demo, not a complete model provider.

## 4. Test and shut down

Run the local API contract tests without launching an external CLI:

```bash
uv run --locked python -m unittest discover -s tests -v
```

Exit an interactive CLI (`/exit` or `Ctrl-C`) to stop its launcher-managed
server. A manually started server runs until `Ctrl-C` in its terminal.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Launcher reports a missing command | `uv`, `curl`, `claude`, or `copilot` is not on `PATH` | Install the prerequisite and verify `<command> --version` |
| Launcher reports an already-responding port | Another service is using that port | Set `LOREMOPUS_PORT=5050` (or another free port) |
| CLI cannot connect | Server did not become ready or wrong port in a manual setup | Prefer a launcher; for manual setup, check `curl -fsS http://127.0.0.1:5000/v1/models` |
| No Bash calls occur | Launchers disable them by default; the client may not offer `Bash`, or randomness skips them | If wanted, set `LOREMOPUS_TOOLS=1` and keep permissions enabled |
| Real model output appears | CLI was run outside the launcher or is using a different provider | Run the matching script, not `claude` or `copilot` directly |

LoremOpus does **not** enforce authentication. Keep it bound to
`127.0.0.1`, leave debug mode off, and do not expose the API to untrusted
networks. The launchers enforce the loopback bind; manual use should do the
same. Neither a production web server nor hosted infrastructure is required
for this intentionally local demo.
