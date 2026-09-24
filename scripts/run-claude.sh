#!/usr/bin/env bash
# Usage: scripts/run-claude.sh [claude arguments...]
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/_gibberish-server.sh"

gibberish_require_command claude
gibberish_start_server

gibberish_run_cli env -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_USE_BEDROCK \
    -u CLAUDE_CODE_USE_VERTEX -u CLAUDE_CODE_USE_FOUNDRY \
    ANTHROPIC_BASE_URL="$gibberish_url" \
    ANTHROPIC_API_KEY=local-gibberish \
    ANTHROPIC_MODEL="$gibberish_model" \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    claude "$@"
