#!/usr/bin/env bash
# Usage: scripts/run-claude.sh [claude arguments...]
set -euo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/_gibberishlm-server.sh"

gibberishlm_require_command claude
gibberishlm_start_server

claude_config_dir="${GIBBERISHLM_CLAUDE_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/gibberishlm/claude}"
if [[ ! -e "$claude_config_dir/.claude.json" ]]; then
    mkdir -p -- "$claude_config_dir"
    (
        umask 077
        printf '{\n  "hasCompletedOnboarding": true\n}\n' >"$claude_config_dir/.claude.json"
    )
fi

gibberishlm_run_cli env -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN \
    -u CLAUDE_CODE_USE_BEDROCK \
    -u CLAUDE_CODE_USE_VERTEX -u CLAUDE_CODE_USE_FOUNDRY \
    CLAUDE_CONFIG_DIR="$claude_config_dir" \
    ANTHROPIC_BASE_URL="$gibberishlm_url" \
    ANTHROPIC_API_KEY=local-gibberishlm \
    ANTHROPIC_MODEL="$gibberishlm_model" \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    claude "$@"
