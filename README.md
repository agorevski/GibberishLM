# GibberishLM

A **local, Anthropic-compatible API** that returns fabricated coding-assistant
output. Point Claude Code or GitHub Copilot CLI at it for a fake model demo:
lorem ipsum answers, optional simulated thinking, and optional Bash tool-use
requests. There is **no browser UI, real model, or external service behind the
API**. GibberishLM is not a functional assistant.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and use
Python 3.10 or newer. The launchers also require Bash and `curl`. Install
whichever CLI you want to try (Node.js/npm is needed for these install commands):

```bash
npm install -g @anthropic-ai/claude-code  # for Claude Code
npm install -g @github/copilot             # for GitHub Copilot CLI
uv sync --locked                           # installs GibberishLM into .venv
```

From the project root, run **one** of:

```bash
./scripts/run-claude.sh -p "Say hello"
./scripts/run-copilot.sh -p "Say hello"
```

Omit `-p "Say hello"` for an interactive CLI session. The scripts accept and
forward additional arguments to their respective CLIs. Each starts GibberishLM on
`127.0.0.1:5000` in the background, connects the CLI to its fake API, and stops
the server when the CLI exits or the launcher is interrupted. They scope the
connection settings to the CLI process; no shell-profile edits or permanent
API-key changes are needed. Choose another port with, for example,
`GIBBERISHLM_PORT=5050 ./scripts/run-copilot.sh -p "Say hello"`.

Copilot defaults to `COPILOT_OFFLINE=true`. To allow Copilot's GitHub, MCP,
web, and other network capabilities while still sending **model inference to
the local GibberishLM API**, run
`COPILOT_OFFLINE=false ./scripts/run-copilot.sh -p "Say hello"`. This is no
longer an offline CLI session.

The launchers enable tool calls by default. GibberishLM runs one safe tool offered
by Claude Code or Copilot CLI on each fresh turn. Set `GIBBERISHLM_TOOLS=0` to
disable tool calls. **A CLI may actually execute tools it accepts from the
API**; keep permission prompts enabled and review each request.

See the [runbook](RUNBOOK.md) for CLI connection details, manual server startup,
request examples, configuration, and troubleshooting.

## API

- `POST /v1/messages`: Anthropic-style JSON messages or streaming SSE events;
  optionally emits a thinking block and a supported tool request when enabled.
  A positive `max_tokens` caps the fabricated output; truncated responses use
  `stop_reason: "max_tokens"`.
- `POST /v1/messages/count_tokens`: rough, fabricated token estimate.
- `GET /v1/models` and `GET /v1/models/<id>`: model metadata.

Both response formats report usage estimated from the content actually emitted,
not real model tokens. Malformed JSON or invalid request fields receive an
Anthropic-style JSON error with HTTP 400.

The default wire model ID is `claude-opus-4-8-gibberishlm`. Request processing is
local and generated output is meaningless. The API does **not** enforce
authentication; the launchers bind to loopback and this demo should not be
exposed to an untrusted network. Installation of the CLIs and dependencies can
require network access.

## Project layout

```text
app.py                    Flask API endpoints and service entry point
anthropic_api.py          Fake Anthropic Messages response and SSE formatting
gibberishlm.py              Generated prose, thinking, and demo commands
timing.py                 Per-request response pacing
scripts/run-claude.sh     Start server and run Claude Code
scripts/run-copilot.sh    Start server and run GitHub Copilot CLI
scripts/_gibberishlm-server.sh  Shared launcher lifecycle
tests/                    API contract and regression tests
pyproject.toml, uv.lock   Python project metadata and uv dependency lock
requirements.txt         Unpinned pip fallback for manual service use
RUNBOOK.md                Manual operation and CLI details
```

Run the focused tests with
`uv run --locked python -m unittest discover -s tests -v`.
