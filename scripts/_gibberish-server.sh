#!/usr/bin/env bash
# Shared lifecycle for the Claude Code and Copilot CLI launchers.

gibberish_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
gibberish_project_root="$(cd -- "$gibberish_script_dir/.." && pwd -P)"
gibberish_server_pid=
gibberish_cli_pid=
gibberish_log=

gibberish_require_command() {
    if ! type -P "$1" >/dev/null 2>&1; then
        printf 'Gibberish: required command not found: %s\n' "$1" >&2
        return 127
    fi
}

gibberish_cleanup() {
    local status=$?
    trap - EXIT INT TERM HUP
    if [[ -n "$gibberish_server_pid" ]]; then
        kill "$gibberish_server_pid" 2>/dev/null || :
        wait "$gibberish_server_pid" 2>/dev/null || :
    fi
    if [[ -n "$gibberish_log" ]]; then
        rm -f -- "$gibberish_log"
    fi
    exit "$status"
}

gibberish_signal() {
    local status=$1
    if [[ -n "$gibberish_cli_pid" ]]; then
        kill "$gibberish_cli_pid" 2>/dev/null || :
    fi
    exit "$status"
}

gibberish_run_cli() {
    "$@" <&0 &
    gibberish_cli_pid=$!
    wait "$gibberish_cli_pid"
}

gibberish_start_server() {
    gibberish_require_command uv
    gibberish_require_command curl

    local port="${GIBBERISH_PORT:-5000}"
    local timeout="${GIBBERISH_STARTUP_TIMEOUT:-60}"
    local tools="${GIBBERISH_TOOLS:-0}"
    gibberish_model="${GIBBERISH_MODEL_ID:-claude-opus-4-8-gibberish}"

    if [[ ! "$port" =~ ^[1-9][0-9]{0,4}$ ]] || (( port > 65535 )); then
        printf 'Gibberish: GIBBERISH_PORT must be between 1 and 65535\n' >&2
        return 1
    fi
    if [[ ! "$timeout" =~ ^[1-9][0-9]{0,2}$ ]]; then
        printf 'Gibberish: GIBBERISH_STARTUP_TIMEOUT must be 1-999 seconds\n' >&2
        return 1
    fi
    if [[ "$tools" != 0 && "$tools" != 1 ]]; then
        printf 'Gibberish: GIBBERISH_TOOLS must be 0 or 1\n' >&2
        return 1
    fi

    gibberish_url="http://127.0.0.1:$port"
    if curl --silent --fail --noproxy '*' --max-time 1 "$gibberish_url/v1/models" >/dev/null; then
        printf 'Gibberish: %s is already responding; choose another GIBBERISH_PORT\n' "$gibberish_url" >&2
        return 1
    fi

    if ! gibberish_log=$(mktemp "${TMPDIR:-/tmp}/gibberish.XXXXXXXX.log"); then
        printf 'Gibberish: cannot create temporary server log\n' >&2
        return 1
    fi

    trap gibberish_cleanup EXIT
    trap 'gibberish_signal 130' INT
    trap 'gibberish_signal 143' TERM
    trap 'gibberish_signal 129' HUP

    (
        cd -- "$gibberish_project_root" || exit 1
        exec env GIBBERISH_HOST=127.0.0.1 GIBBERISH_PORT="$port" \
            GIBBERISH_DEBUG=0 GIBBERISH_TOOLS="$tools" \
            GIBBERISH_MODEL_ID="$gibberish_model" uv run --locked gibberish
    ) >"$gibberish_log" 2>&1 &
    gibberish_server_pid=$!

    local deadline=$((SECONDS + timeout))
    while (( SECONDS < deadline )); do
        if ! kill -0 "$gibberish_server_pid" 2>/dev/null; then
            printf 'Gibberish: server exited before becoming ready\n' >&2
            tail -n 30 -- "$gibberish_log" >&2
            return 1
        fi
        if curl --silent --fail --noproxy '*' --max-time 1 "$gibberish_url/v1/models" >/dev/null &&
            kill -0 "$gibberish_server_pid" 2>/dev/null; then
            return 0
        fi
        sleep 0.25
    done
    printf 'Gibberish: server did not become ready within %s seconds\n' "$timeout" >&2
    tail -n 30 -- "$gibberish_log" >&2
    return 1
}
