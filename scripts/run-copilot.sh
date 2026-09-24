#!/usr/bin/env bash
# Usage: scripts/run-copilot.sh [copilot arguments...]
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/_gibberishlm-server.sh"

gibberishlm_require_command copilot
gibberishlm_start_server

gibberishlm_run_cli env -u COPILOT_PROVIDER_API_KEY_COMMAND \
    -u COPILOT_PROVIDER_BEARER_TOKEN -u COPILOT_PROVIDER_HEADERS \
    -u COPILOT_PROVIDER_MODEL_ID -u COPILOT_PROVIDER_WIRE_API \
    -u COPILOT_PROVIDER_TRANSPORT \
    COPILOT_PROVIDER_TYPE=anthropic \
    COPILOT_PROVIDER_BASE_URL="$gibberishlm_url" \
    COPILOT_PROVIDER_API_KEY=gibberishlm-fake-key \
    COPILOT_MODEL=claude-sonnet-4 \
    COPILOT_PROVIDER_WIRE_MODEL="$gibberishlm_model" \
    COPILOT_OFFLINE="${COPILOT_OFFLINE:-true}" \
    copilot "$@"
