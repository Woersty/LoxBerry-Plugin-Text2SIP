#!/usr/bin/env bash
set -u

# Text2SIP Pocket-TTS resident server controller.
# Keeps the German Pocket-TTS model loaded in RAM between announcements.

DATA_BASE="REPLACELBHOMEDIR/data/plugins/text2sip/pockettts"
VENV="$DATA_BASE/venv"
CLI="$VENV/bin/pocket-tts"
CACHE="$DATA_BASE/cache"
STATE="$DATA_BASE/languages"
RUNDIR="/run/shm/text2sip-pockettts"
PIDFILE="$RUNDIR/server.pid"
MODELFILE="$RUNDIR/server.model"
STARTFILE="$RUNDIR/server.started"
SERVER_LOG="$RUNDIR/server.log"
HOST="127.0.0.1"
PORT="8765"
URL="http://$HOST:$PORT"
MODEL="german"

mkdir -p "$RUNDIR" 2>/dev/null || true

export HF_HOME="$CACHE/huggingface"
export HUGGINGFACE_HUB_CACHE="$CACHE/huggingface/hub"
export XDG_CACHE_HOME="$CACHE/xdg"
export TORCH_HOME="$CACHE/torch"
export TMPDIR="$RUNDIR"
export LC_ALL="C.UTF-8"
export LANG="C.UTF-8"

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
    kill -0 "$PID" 2>/dev/null
}

start_server() {
    if health; then
        exit 0
    fi

    if pid_alive; then
        # Model may still be loading. Do not start a second copy for 90s.
        # After that, a process without /health is considered stuck.
        NOW="$(date +%s)"
        STARTED="$(cat "$STARTFILE" 2>/dev/null || echo "$NOW")"
        case "$STARTED" in ''|*[!0-9]*) STARTED="$NOW" ;; esac
        if [ $((NOW - STARTED)) -lt 90 ]; then
            exit 0
        fi
        stop_server
    fi

    rm -f "$PIDFILE" "$MODELFILE" "$STARTFILE" "$SERVER_LOG"

    if [ ! -x "$CLI" ]; then
        echo "Pocket-TTS CLI missing: $CLI" >&2
        exit 2
    fi
    if [ ! -f "$STATE/de.ready" ]; then
        echo "German Pocket-TTS model is not prepared: $STATE/de.ready" >&2
        exit 3
    fi

    # The process is intentionally detached from the LoxBerry daemon runner.
    # Runtime logs live in tmpfs so continuous server output does not wear flash.
    nohup "$CLI" serve \
        --host "$HOST" \
        --port "$PORT" \
        --language "$MODEL" \
        --quantize \
        >"$SERVER_LOG" 2>&1 </dev/null &
    PID=$!
    printf '%s\n' "$PID" > "$PIDFILE"
    printf '%s\n' "$MODEL" > "$MODELFILE"
    date +%s > "$STARTFILE"

    # Validate that the process at least survived startup. Full model loading is
    # asynchronous; callers use /health before sending a request.
    sleep 0.2
    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$PIDFILE" "$MODELFILE" "$STARTFILE"
        echo "Pocket-TTS server terminated during startup" >&2
        [ -f "$SERVER_LOG" ] && tail -n 20 "$SERVER_LOG" >&2
        exit 4
    fi

    exit 0
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

case "${1:-status}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        exit 0
        ;;
    restart)
        stop_server
        start_server
        ;;
    status)
        if health; then
            echo "running"
            exit 0
        fi
        if pid_alive; then
            echo "starting"
            exit 3
        fi
        echo "stopped"
        exit 1
        ;;
    health)
        health
        exit $?
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|health}" >&2
        exit 64
        ;;
esac
