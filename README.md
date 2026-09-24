# Gibberish

A faux **Claude Opus 4.8 / Claude Code CLI** experience for the browser.

Gibberish reproduces the *look and feel* of a streaming coding-agent session —
reasoning ("thinking") blocks, bash tool calls, command output, and a final
assistant reply — except **every byte of output is fabricated nonsense**
(lorem ipsum and canned command results). Nothing connects to a real model.

It is a demo / parody / UI sandbox, not a functional assistant.

## Features

- **Terminal-style web UI** mimicking the Claude Code CLI.
- **Token-by-token streaming** over Server-Sent Events (SSE) with realistic
  pacing and a blinking cursor.
- **Realistic, variable latency** — a premium-model timing profile with a
  variable time-to-first-token and a per-request "thinking" duration, so no two
  responses take the same amount of time (fully configurable).
- **Simulated "thinking"** blocks rendered in dimmed italics.
- **Fake bash tool calls** (e.g. `echo "hello world"`, `ls -la`, `pwd`) with
  canned, plausible-looking output.
- **Lorem ipsum prose** for the assistant's final answer.
- **Claude Code CLI compatible** — implements the Anthropic Messages API so the
  real CLI can drive it (see `RUNBOOK.md`).
- Pure Python backend (Flask) + vanilla JS frontend. No build step, no
  external services.

## Project layout

```
Gibberish/
├── app.py              # Flask app: web UI + SSE + Anthropic-compatible API
├── gibberish.py        # Fake-content engine (sessions, lorem ipsum, commands)
├── anthropic_api.py    # Anthropic /v1/messages wire-format emulation
├── timing.py           # Per-request latency model (premium-model pacing)
├── pyproject.toml      # uv / packaging metadata
├── requirements.txt    # (pip fallback)
├── RUNBOOK.md          # Operate the service + wire up Claude Code CLI
├── templates/
│   └── index.html      # Terminal UI shell
└── static/
    ├── style.css       # Dark terminal theme
    └── app.js          # SSE client + DOM rendering
```

## Quick start

```bash
# 1. install dependencies into a local .venv
uv sync

# 2. run the service (http://127.0.0.1:5000)
uv run gibberish
```

Then open <http://127.0.0.1:5000> in your browser, type a prompt, and press
**Enter**. Use **Shift+Enter** for a newline.

> Prefer plain pip? `pip install -r requirements.txt && python3 app.py` also
> works.

## Use it with the real Claude Code CLI

Gibberish also speaks the **Anthropic Messages API**, so you can point the
official Claude Code CLI at it and get a full (fake) agent session in your
terminal — streaming, "thinking", and executed Bash commands. See
[`RUNBOOK.md`](RUNBOOK.md) for the step-by-step guide. The short version:

```bash
npm install -g @anthropic-ai/claude-code
export ANTHROPIC_BASE_URL="http://127.0.0.1:5000"
export ANTHROPIC_API_KEY="gibberish-fake-key"
export ANTHROPIC_MODEL="claude-opus-4-8-gibberish"
claude -p "write a hello world bash script"
```

## How it works

1. The browser POSTs your prompt to `/api/stream`.
2. `gibberish.build_session()` assembles a random sequence of events:
   status → thinking → intro text → one or more bash tool calls (with results)
   → final lorem ipsum message → done.
3. `app.py` serializes each event as an SSE message, streaming text in small
   chunks with randomized delays to imitate a live model.
4. `static/app.js` consumes the stream with a small fetch-based SSE client
   (the native `EventSource` only supports GET) and renders blocks, tool cards,
   and a status spinner.

## Customizing the gibberish

Edit `gibberish.py`:

- `FAKE_COMMANDS` / `FAKE_COMMAND_OUTPUTS` — the pool of bash commands and their
  pretend output.
- `THINKING_OPENERS` — opening lines for reasoning blocks.
- `LOREM_WORDS` — the word pool for generated prose.
- `build_session()` — the overall shape/order of a session.

Streaming speed lives in `DELAY_BY_TYPE` in `app.py`.

## Disclaimer

Gibberish is a UI emulation for demonstration and entertainment. It does **not**
use, contain, or communicate with any AI model, and its output is meaningless by
design.
