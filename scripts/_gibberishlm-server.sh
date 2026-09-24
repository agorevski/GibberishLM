#!/usr/bin/env bash
# Shared lifecycle for the Claude Code and Copilot CLI launchers.

gibberishlm_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
gibberishlm_project_root="$(cd -- "$gibberishlm_script_dir/.." && pwd -P)"
gibberishlm_server_pid=
gibberishlm_cli_pid=
gibberishlm_log=

gibberishlm_require_command() {
    if ! type -P "$1" >/dev/null 2>&1; then
        printf 'GibberishLM: required command not found: %s\n' "$1" >&2
        return 127
    fi
}

gibberishlm_cleanup() {
    local status=$?
    trap - EXIT INT TERM HUP
    if [[ -n "$gibberishlm_server_pid" ]]; then
        kill "$gibberishlm_server_pid" 2>/dev/null || :
        wait "$gibberishlm_server_pid" 2>/dev/null || :
    fi
    if [[ -n "$gibberishlm_log" ]]; then
        rm -f -- "$gibberishlm_log"
    fi
    exit "$status"
}

gibberishlm_signal() {
    local status=$1
    if [[ -n "$gibberishlm_cli_pid" ]]; then
        kill "$gibberishlm_cli_pid" 2>/dev/null || :
    fi
    exit "$status"
}

gibberishlm_run_cli() {
    "$@" <&0 &
    gibberishlm_cli_pid=$!
    wait "$gibberishlm_cli_pid"
}

gibberishlm_start_server() {
    gibberishlm_require_command uv
    gibberishlm_require_command curl

    local port="${GIBBERISHLM_PORT:-5000}"
    local timeout="${GIBBERISHLM_STARTUP_TIMEOUT:-60}"
    local tools="${GIBBERISHLM_TOOLS:-1}"
    gibberishlm_model="${GIBBERISHLM_MODEL_ID:-claude-opus-4-8-gibberishlm}"

    if [[ ! "$port" =~ ^[1-9][0-9]{0,4}$ ]] || (( port > 65535 )); then
        printf 'GibberishLM: GIBBERISHLM_PORT must be between 1 and 65535\n' >&2
        return 1
    fi
    if [[ ! "$timeout" =~ ^[1-9][0-9]{0,2}$ ]]; then
        printf 'GibberishLM: GIBBERISHLM_STARTUP_TIMEOUT must be 1-999 seconds\n' >&2
        return 1
    fi
    if [[ "$tools" != 0 && "$tools" != 1 ]]; then
        printf 'GibberishLM: GIBBERISHLM_TOOLS must be 0 or 1\n' >&2
        return 1
    fi

    gibberishlm_url="http://127.0.0.1:$port"
    if curl --silent --fail --noproxy '*' --max-time 1 "$gibberishlm_url/v1/models" >/dev/null; then
        printf 'GibberishLM: %s is already responding; choose another GIBBERISHLM_PORT\n' "$gibberishlm_url" >&2
        return 1
    fi

    if ! gibberishlm_log=$(mktemp "${TMPDIR:-/tmp}/gibberishlm.XXXXXXXX.log"); then
        printf 'GibberishLM: cannot create temporary server log\n' >&2
        return 1
    fi

    trap gibberishlm_cleanup EXIT
    trap 'gibberishlm_signal 130' INT
    trap 'gibberishlm_signal 143' TERM
    trap 'gibberishlm_signal 129' HUP

    (
        cd -- "$gibberishlm_project_root" || exit 1
        exec env GIBBERISHLM_HOST=127.0.0.1 GIBBERISHLM_PORT="$port" \
            GIBBERISHLM_DEBUG=0 GIBBERISHLM_TOOLS="$tools" \
            GIBBERISHLM_MODEL_ID="$gibberishlm_model" uv run --locked gibberishlm
    ) >"$gibberishlm_log" 2>&1 &
    gibberishlm_server_pid=$!

    local deadline=$((SECONDS + timeout))
    while (( SECONDS < deadline )); do
        if ! kill -0 "$gibberishlm_server_pid" 2>/dev/null; then
            printf 'GibberishLM: server exited before becoming ready\n' >&2
            tail -n 30 -- "$gibberishlm_log" >&2
            return 1
        fi
        if curl --silent --fail --noproxy '*' --max-time 1 "$gibberishlm_url/v1/models" >/dev/null &&
            kill -0 "$gibberishlm_server_pid" 2>/dev/null; then
            return 0
        fi
        sleep 0.25
    done
    printf 'GibberishLM: server did not become ready within %s seconds\n' "$timeout" >&2
    tail -n 30 -- "$gibberishlm_log" >&2
    return 1
}
