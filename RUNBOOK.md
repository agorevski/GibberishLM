# Gibberish Runbook

Operational guide to run the Gibberish service and drive it with the **official
Claude Code CLI**. When wired up, the CLI behaves exactly like a real
Opus session — streaming text, "thinking", and executing Bash tool calls —
except **every response is fake gibberish** generated locally. No real model,
no network calls to Anthropic, no API costs.

---

## 0. Prerequisites

| Tool   | Why                          | Check                |
|--------|------------------------------|----------------------|
| `uv`   | Runs the Gibberish service   | `uv --version`       |
| `node` + `npm` | Installs the Claude Code CLI | `node --version` / `npm --version` |

---

## 1. Start the Gibberish service (with `uv`)

From the project root:

```bash
# Install dependencies into a project-local virtualenv (.venv)
uv sync

# Run the service (defaults to http://127.0.0.1:5000)
uv run gibberish
```

You should see Flask serving on `http://127.0.0.1:5000`. Open that URL in a
browser for the standalone terminal UI, or leave it running for the CLI.

### Configuration (environment variables)

| Variable           | Default                      | Purpose                                            |
|--------------------|------------------------------|----------------------------------------------------|
| `GIBBERISH_HOST`   | `127.0.0.1`                  | Bind address                                       |
| `GIBBERISH_PORT`   | `5000`                       | Bind port                                          |
| `GIBBERISH_MODEL_ID` | `claude-opus-4-8-gibberish` | Model id reported to API clients                  |
| `GIBBERISH_TOOLS`  | `1`                          | `0` disables fake Bash tool calls to the CLI       |
| `GIBBERISH_DEBUG`  | `0`                          | `1` enables Flask debug/reloader                   |

#### Response-timing knobs (emulate an expensive frontier model)

Gibberish deliberately streams slowly, with a variable time-to-first-token and a
variable "thinking" phase, so each request takes a realistic, non-uniform amount
of time. Tune it with:

| Variable                  | Default | Purpose                                             |
|---------------------------|---------|-----------------------------------------------------|
| `GIBBERISH_SPEED`         | `1.0`   | Global multiplier on every delay (`0.2` = fast demo)|
| `GIBBERISH_TEXT_TPS`      | `38`    | Answer streaming rate (tokens/sec)                  |
| `GIBBERISH_THINK_TPS`     | `48`    | Thinking streaming rate (tokens/sec)                |
| `GIBBERISH_TTFT_MIN/MAX`  | `1.0`/`4.0` | Time-to-first-token range (seconds)             |
| `GIBBERISH_THINK_MIN/MAX` | `2.5`/`12.0` | Thinking-phase budget range (seconds)          |
| `GIBBERISH_HIDDEN_THINK_CAP` | `6.0` | Max silent deliberation when thinking isn't shown  |
| `GIBBERISH_TOOL_EXEC_MIN/MAX` | `0.4`/`2.5` | Simulated bash-command run time (seconds)   |

Typical durations with defaults: a non-thinking request ≈ 5–9s; a
thinking-enabled request ≈ 8–25s (median ~14s), varying per call.

For a snappier demo:

```bash
GIBBERISH_SPEED=0.25 uv run gibberish
```

Example on a custom port:

```bash
GIBBERISH_PORT=5050 uv run gibberish
```

### Verify it's up

```bash
curl -s http://127.0.0.1:5000/v1/models | python3 -m json.tool
```

You should get a JSON model list containing `claude-opus-4-8-gibberish`.

---

## 2. Install the official Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code

# confirm
claude --version
```

> The CLI talks to whatever `ANTHROPIC_BASE_URL` points at, using the standard
> Anthropic Messages API. Gibberish implements that API, so the CLI cannot tell
> the difference — but the answers are nonsense.

---

## 3. Point the CLI at Gibberish (environment variables)

Set these in the shell where you'll run `claude`:

```bash
# Send all CLI traffic to Gibberish instead of api.anthropic.com
export ANTHROPIC_BASE_URL="http://127.0.0.1:5000"

# Any non-empty key works — Gibberish does not validate credentials
export ANTHROPIC_API_KEY="gibberish-fake-key"

# Use the fake model id Gibberish advertises
export ANTHROPIC_MODEL="claude-opus-4-8-gibberish"
```

> If you started Gibberish on a custom port, match it here, e.g.
> `export ANTHROPIC_BASE_URL="http://127.0.0.1:5050"`.

To make it permanent, add those `export` lines to `~/.bashrc` / `~/.zshrc`.

### Windows (Command Prompt)

```bat
set ANTHROPIC_BASE_URL=http://127.0.0.1:5000
set ANTHROPIC_API_KEY=gibberish-fake-key
set ANTHROPIC_MODEL=claude-opus-4-8-gibberish
```

---

## 4. Run it

**Interactive session:**

```bash
claude
```

**One-shot (print) mode:**

```bash
claude -p "write a hello world bash script"
```

You'll get streamed lorem ipsum, and — when Gibberish emits a Bash tool call —
the CLI will ask to run a harmless demo command (e.g. `echo "hello world"`,
`date`, `ls -la`). Approve it to watch the fake agent "loop".

To let it run those demo commands without prompting (safe — they are read-only
echo/ls/date/whoami style commands):

```bash
claude -p "run a command" --dangerously-skip-permissions
```

Disable tool calls entirely by starting Gibberish with `GIBBERISH_TOOLS=0`.

---

## 5. Quick end-to-end smoke test

```bash
# Terminal A
GIBBERISH_PORT=5050 uv run gibberish

# Terminal B
export ANTHROPIC_BASE_URL=http://127.0.0.1:5050
export ANTHROPIC_API_KEY=gibberish-fake-key
export ANTHROPIC_MODEL=claude-opus-4-8-gibberish
claude -p "say hello" --dangerously-skip-permissions
```

Expected: a paragraph of nonsense streams back; some runs additionally execute
a fake Bash command and continue.

---

## 6. Shut down

- Stop the CLI: `Ctrl-C` (or `/exit` in interactive mode).
- Stop Gibberish: `Ctrl-C` in its terminal, or `kill <pid>` for the
  `gibberish` process.
- Unset the redirection so the CLI talks to the real Anthropic API again:

  ```bash
  unset ANTHROPIC_BASE_URL ANTHROPIC_API_KEY ANTHROPIC_MODEL
  ```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| CLI hangs or "connection refused" | Gibberish not running / wrong port | Start it; ensure `ANTHROPIC_BASE_URL` port matches `GIBBERISH_PORT` |
| CLI errors about auth | Some setups require a token form | Also try `export ANTHROPIC_AUTH_TOKEN="gibberish-fake-key"` |
| No Bash commands ever run | Tools disabled, or unlucky randomness | Ensure `GIBBERISH_TOOLS=1`; tool calls are emitted ~70% of fresh turns |
| Real model answers appear | `ANTHROPIC_BASE_URL` not exported in this shell | Re-export in the **same** shell running `claude` |
| Want to confirm traffic hits Gibberish | — | Run with `GIBBERISH_DEBUG=1` and watch the request log |

---

## What Gibberish implements

The CLI relies on these Anthropic-compatible endpoints (all fake):

- `POST /v1/messages` — streaming **and** non-streaming; emits `message_start`,
  `content_block_*` (text, thinking, tool_use), `message_delta`, `message_stop`.
- `POST /v1/messages/count_tokens` — rough fake token count.
- `GET /v1/models`, `GET /v1/models/<id>` — advertises the fake model.

Authentication is intentionally **not** enforced.
