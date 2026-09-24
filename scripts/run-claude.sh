#!/usr/bin/env bash
# Usage: scripts/run-claude.sh [claude arguments...]
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/_gibberishlm-server.sh"

gibberishlm_require_command claude
gibberishlm_start_server

gibberishlm_run_cli env -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_USE_BEDROCK \
    -u CLAUDE_CODE_USE_VERTEX -u CLAUDE_CODE_USE_FOUNDRY \
    ANTHROPIC_BASE_URL="$gibberishlm_url" \
    ANTHROPIC_API_KEY=local-gibberishlm \
    ANTHROPIC_MODEL="$gibberishlm_model" \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    claude "$@"
