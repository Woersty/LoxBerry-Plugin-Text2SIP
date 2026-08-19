#!/usr/bin/env bash
set -u

# Text2SIP Pocket-TTS resident server controller.
# Exactly one Pocket-TTS language model is kept resident at a time.

DATA_BASE="REPLACELBHOMEDIR/data/plugins/text2sip/pockettts"
VENV="$DATA_BASE/venv"
CLI="$VENV/bin/pocket-tts"
CACHE="$DATA_BASE/cache"
STATE="$DATA_BASE/languages"
RUNDIR="/run/shm/text2sip-pockettts"
PIDFILE="$RUNDIR/server.pid"
MODELFILE="$RUNDIR/server.model"
REQUESTFILE="$RUNDIR/server.requested"
STARTFILE="$RUNDIR/server.started"
SERVER_LOG="$RUNDIR/server.log"
HOST="127.0.0.1"
PORT="8765"
URL="http://$HOST:$PORT"
DEFAULT_MODEL="german"

mkdir -p "$RUNDIR" 2>/dev/null || true

export HF_HOME="$CACHE/huggingface"
export HUGGINGFACE_HUB_CACHE="$CACHE/huggingface/hub"
export XDG_CACHE_HOME="$CACHE/xdg"
export TORCH_HOME="$CACHE/torch"
export TMPDIR="$RUNDIR"
export LC_ALL="C.UTF-8"
export LANG="C.UTF-8"

normalize_model() {
    case "${1:-}" in
        de|de-de|german) echo "german" ;;
        gb|us|en|en-gb|en-us|english) echo "english" ;;
        es|es-es|spanish) echo "spanish" ;;
        it|it-it|italian) echo "italian" ;;
        pt|pt-pt|portuguese) echo "portuguese" ;;
        fr|fr-fr|french|french_24l) echo "french_24l" ;;
        *) return 1 ;;
    esac
}

model_marker() {
    case "$1" in
        german) echo "$STATE/de.ready" ;;
        english) echo "$STATE/en.ready" ;;
        spanish) echo "$STATE/es.ready" ;;
        italian) echo "$STATE/it.ready" ;;
        portuguese) echo "$STATE/pt.ready" ;;
        french_24l) echo "$STATE/fr.ready" ;;
        *) return 1 ;;
    esac
}

resolve_model() {
    local requested current
    if requested="$(normalize_model "${1:-}" 2>/dev/null)"; then
        printf '%s\n' "$requested"
        return 0
    fi
    if [ -r "$REQUESTFILE" ]; then
        requested="$(cat "$REQUESTFILE" 2>/dev/null || true)"
        if requested="$(normalize_model "$requested" 2>/dev/null)"; then
            printf '%s\n' "$requested"
            return 0
        fi
    fi
    if [ -r "$MODELFILE" ]; then
        current="$(cat "$MODELFILE" 2>/dev/null || true)"
        if current="$(normalize_model "$current" 2>/dev/null)"; then
            printf '%s\n' "$current"
            return 0
        fi
    fi
    printf '%s\n' "$DEFAULT_MODEL"
}

current_model() {
    [ -r "$MODELFILE" ] || return 1
    local current
    current="$(cat "$MODELFILE" 2>/dev/null || true)"
    normalize_model "$current"
}

health() {
    /usr/bin/wget -q -T 1 -O /dev/null "$URL/health" 2>/dev/null
}

read_pid() {
    [ -r "$PIDFILE" ] || return 1
    PID="$(cat "$PIDFILE" 2>/dev/null || true)"
    case "$PID" in
        ''|*[!0-9]*) return 1 ;;
    esac
    return 0
}

pid_alive() {
    read_pid || return 1
    kill -0 "$PID" 2>/dev/null || return 1
    [ -r "/proc/$PID/stat" ] || return 1
    PROC_STATE="$(awk '{print $3}' "/proc/$PID/stat" 2>/dev/null || true)"
    [ "$PROC_STATE" != "Z" ] || return 1
    [ -r "/proc/$PID/cmdline" ] || return 1
    CMDLINE="$(tr '\000' ' ' < "/proc/$PID/cmdline" 2>/dev/null || true)"
    case "$CMDLINE" in
        *pocket-tts*serve*) return 0 ;;
    esac
    return 1
}

stop_server() {
    if read_pid && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        i=0
        while kill -0 "$PID" 2>/dev/null && [ "$i" -lt 25 ]; do
            sleep 0.2
            i=$((i + 1))
        done
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
    rm -f "$PIDFILE" "$MODELFILE" "$STARTFILE"
    return 0
}

start_server() {
    local desired marker now started running
    desired="$(resolve_model "${1:-}")"
    printf '%s\n' "$desired" > "$REQUESTFILE"

    if health; then
        running="$(current_model 2>/dev/null || true)"
        if [ "$running" = "$desired" ]; then
            return 0
        fi
        # Healthy, but the caller requested another language model.
        stop_server
    fi

    if pid_alive; then
        running="$(current_model 2>/dev/null || true)"
        if [ "$running" != "$desired" ]; then
            stop_server
        else
            now="$(date +%s)"
            started="$(cat "$STARTFILE" 2>/dev/null || echo "$now")"
            case "$started" in ''|*[!0-9]*) started="$now" ;; esac
            if [ $((now - started)) -lt 90 ]; then
                return 0
            fi
            stop_server
        fi
    fi

    rm -f "$PIDFILE" "$MODELFILE" "$STARTFILE" "$SERVER_LOG"

    if [ ! -x "$CLI" ]; then
        echo "Pocket-TTS CLI missing: $CLI" >&2
        return 2
    fi
    marker="$(model_marker "$desired" 2>/dev/null || true)"
    if [ -z "$marker" ] || [ ! -f "$marker" ]; then
        echo "Pocket-TTS model is not prepared: $desired" >&2
        return 3
    fi

    nohup "$CLI" serve \
        --host "$HOST" \
        --port "$PORT" \
        --language "$desired" \
        --quantize \
        >"$SERVER_LOG" 2>&1 </dev/null &
    PID=$!
    printf '%s\n' "$PID" > "$PIDFILE"
    printf '%s\n' "$desired" > "$MODELFILE"
    date +%s > "$STARTFILE"

    sleep 0.2
    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$PIDFILE" "$MODELFILE" "$STARTFILE"
        echo "Pocket-TTS server terminated during startup ($desired)" >&2
        [ -f "$SERVER_LOG" ] && tail -n 20 "$SERVER_LOG" >&2
        return 4
    fi
    return 0
}

case "${1:-status}" in
    start|ensure)
        start_server "${2:-}"
        exit $?
        ;;
    stop)
        stop_server
        exit 0
        ;;
    restart)
        desired="$(resolve_model "${2:-}")"
        printf '%s\n' "$desired" > "$REQUESTFILE"
        stop_server
        start_server "$desired"
        exit $?
        ;;
    status)
        desired="$(resolve_model "${2:-}")"
        if health; then
            running="$(current_model 2>/dev/null || true)"
            if [ -n "$running" ]; then
                echo "running $running"
            else
                echo "running"
            fi
            [ -z "${2:-}" ] || [ "$running" = "$desired" ]
            exit $?
        fi
        if pid_alive; then
            running="$(current_model 2>/dev/null || true)"
            echo "starting${running:+ $running}"
            exit 3
        fi
        echo "stopped"
        exit 1
        ;;
    model)
        current_model
        exit $?
        ;;
    health)
        health
        exit $?
        ;;
    *)
        echo "Usage: $0 {start|ensure|stop|restart|status|model|health} [language|model]" >&2
        exit 64
        ;;
esac
