#!/usr/bin/env bash
# Shared lifecycle for the Claude Code and Copilot CLI launchers.

loremopus_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
loremopus_project_root="$(cd -- "$loremopus_script_dir/.." && pwd -P)"
loremopus_server_pid=
loremopus_cli_pid=
loremopus_log=

loremopus_require_command() {
    if ! type -P "$1" >/dev/null 2>&1; then
        printf 'LoremOpus: required command not found: %s\n' "$1" >&2
        return 127
    fi
}

loremopus_cleanup() {
    local status=$?
    trap - EXIT INT TERM HUP
    if [[ -n "$loremopus_server_pid" ]]; then
        kill "$loremopus_server_pid" 2>/dev/null || :
        wait "$loremopus_server_pid" 2>/dev/null || :
    fi
    if [[ -n "$loremopus_log" ]]; then
        rm -f -- "$loremopus_log"
    fi
    exit "$status"
}

loremopus_signal() {
    local status=$1
    if [[ -n "$loremopus_cli_pid" ]]; then
        kill "$loremopus_cli_pid" 2>/dev/null || :
    fi
    exit "$status"
}

loremopus_run_cli() {
    "$@" <&0 &
    loremopus_cli_pid=$!
    wait "$loremopus_cli_pid"
}

loremopus_start_server() {
    loremopus_require_command uv
    loremopus_require_command curl

    local port="${LOREMOPUS_PORT:-5000}"
    local timeout="${LOREMOPUS_STARTUP_TIMEOUT:-60}"
    local tools="${LOREMOPUS_TOOLS:-0}"
    loremopus_model="${LOREMOPUS_MODEL_ID:-claude-opus-4-8-loremopus}"

    if [[ ! "$port" =~ ^[1-9][0-9]{0,4}$ ]] || (( port > 65535 )); then
        printf 'LoremOpus: LOREMOPUS_PORT must be between 1 and 65535\n' >&2
        return 1
    fi
    if [[ ! "$timeout" =~ ^[1-9][0-9]{0,2}$ ]]; then
        printf 'LoremOpus: LOREMOPUS_STARTUP_TIMEOUT must be 1-999 seconds\n' >&2
        return 1
    fi
    if [[ "$tools" != 0 && "$tools" != 1 ]]; then
        printf 'LoremOpus: LOREMOPUS_TOOLS must be 0 or 1\n' >&2
        return 1
    fi

    loremopus_url="http://127.0.0.1:$port"
    if curl --silent --fail --noproxy '*' --max-time 1 "$loremopus_url/v1/models" >/dev/null; then
        printf 'LoremOpus: %s is already responding; choose another LOREMOPUS_PORT\n' "$loremopus_url" >&2
        return 1
    fi

    if ! loremopus_log=$(mktemp "${TMPDIR:-/tmp}/loremopus.XXXXXXXX.log"); then
        printf 'LoremOpus: cannot create temporary server log\n' >&2
        return 1
    fi

    trap loremopus_cleanup EXIT
    trap 'loremopus_signal 130' INT
    trap 'loremopus_signal 143' TERM
    trap 'loremopus_signal 129' HUP

    (
        cd -- "$loremopus_project_root" || exit 1
        exec env LOREMOPUS_HOST=127.0.0.1 LOREMOPUS_PORT="$port" \
            LOREMOPUS_DEBUG=0 LOREMOPUS_TOOLS="$tools" \
            LOREMOPUS_MODEL_ID="$loremopus_model" uv run --locked loremopus
    ) >"$loremopus_log" 2>&1 &
    loremopus_server_pid=$!

    local deadline=$((SECONDS + timeout))
    while (( SECONDS < deadline )); do
        if ! kill -0 "$loremopus_server_pid" 2>/dev/null; then
            printf 'LoremOpus: server exited before becoming ready\n' >&2
            tail -n 30 -- "$loremopus_log" >&2
            return 1
        fi
        if curl --silent --fail --noproxy '*' --max-time 1 "$loremopus_url/v1/models" >/dev/null &&
            kill -0 "$loremopus_server_pid" 2>/dev/null; then
            return 0
        fi
        sleep 0.25
    done
    printf 'LoremOpus: server did not become ready within %s seconds\n' "$timeout" >&2
    tail -n 30 -- "$loremopus_log" >&2
    return 1
}
