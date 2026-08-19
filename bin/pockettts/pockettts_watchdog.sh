#!/usr/bin/env bash
set -u

# Text2SIP Pocket-TTS watchdog.
# Runs as loxberry, checks the resident server immediately and every 120s,
# stores only transient state/logs in /run/shm, and tries to recover the
# resident server automatically when /health is unavailable.

BASE="REPLACELBHOMEDIR/bin/plugins/text2sip/pockettts"
SERVER_CTL="$BASE/pockettts_server.sh"
RUNDIR="/run/shm/text2sip-pockettts"
PIDFILE="$RUNDIR/watchdog.pid"
STATUSFILE="$RUNDIR/watchdog.status"
WATCHDOG_LOG="$RUNDIR/watchdog.log"
INTERVAL=120
RECOVERY_WAIT=45
LOG_LIMIT=51200
SLEEP_PID=""

mkdir -p "$RUNDIR" 2>/dev/null || true

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
    [ -r "/proc/$PID/cmdline" ] || return 1
    CMDLINE="$(tr '\000' ' ' < "/proc/$PID/cmdline" 2>/dev/null || true)"
    case "$CMDLINE" in
        *pockettts_watchdog.sh*run*) return 0 ;;
    esac
    return 1
}

write_status() {
    local state="$1"
    local detail="${2:-}"
    local now tmp
    now="$(date +%s)"
    detail="$(printf '%s' "$detail" | tr '\r\n' '  ' | tr '|' '/')"
    tmp="$STATUSFILE.tmp.$$"
    {
        printf 'state=%s\n' "$state"
        printf 'checked=%s\n' "$now"
        printf 'detail=%s\n' "$detail"
    } > "$tmp"
    mv -f "$tmp" "$STATUSFILE"
}

trim_watchdog_log() {
    local size=0
    [ -f "$WATCHDOG_LOG" ] || return 0
    size="$(wc -c < "$WATCHDOG_LOG" 2>/dev/null || echo 0)"
    case "$size" in ''|*[!0-9]*) size=0 ;; esac
    if [ "$size" -gt "$LOG_LIMIT" ]; then
        rm -f "$WATCHDOG_LOG"
    fi
}

log_error() {
    trim_watchdog_log
    printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$WATCHDOG_LOG" 2>/dev/null || true
    # If the latest line pushed the file over 50 KiB, delete it immediately.
    # A later error recreates it; successful checks do not write to this log.
    trim_watchdog_log
}

health() {
    [ -x "$SERVER_CTL" ] || return 1
    "$SERVER_CTL" health >/dev/null 2>&1
}

check_once() {
    if health; then
        write_status online healthy
        return 0
    fi

    write_status offline health_failed
    log_error "Pocket-TTS /health failed; automatic recovery requested"

    if [ ! -x "$SERVER_CTL" ]; then
        log_error "Pocket-TTS server controller missing: $SERVER_CTL"
        write_status offline controller_missing
        return 1
    fi

    # Use 'start' rather than an unconditional restart. The server controller
    # deliberately leaves a model that is still loading (<90s) alone and only
    # replaces a genuinely stuck process. This avoids restart loops after boot.
    "$SERVER_CTL" start >/dev/null 2>&1 || true

    local waited=0
    while [ "$waited" -lt "$RECOVERY_WAIT" ]; do
        if health; then
            write_status online recovered
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done

    write_status offline recovery_failed
    log_error "Pocket-TTS automatic recovery failed after ${RECOVERY_WAIT}s"
    return 1
}

cleanup_loop() {
    if [ -n "${SLEEP_PID:-}" ]; then
        kill "$SLEEP_PID" 2>/dev/null || true
        wait "$SLEEP_PID" 2>/dev/null || true
        SLEEP_PID=""
    fi
    rm -f "$PIDFILE"
}

run_loop() {
    trap 'cleanup_loop; exit 0' TERM INT HUP
    trap 'cleanup_loop' EXIT
    while :; do
        check_once || true
        sleep "$INTERVAL" &
        SLEEP_PID=$!
        wait "$SLEEP_PID" || true
        SLEEP_PID=""
    done
}

start_watchdog() {
    if pid_alive; then
        exit 0
    fi

    rm -f "$PIDFILE"
    nohup "$0" run >/dev/null 2>&1 </dev/null &
    PID=$!
    printf '%s\n' "$PID" > "$PIDFILE"

    sleep 0.1
    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$PIDFILE"
        echo "Pocket-TTS watchdog terminated during startup" >&2
        exit 2
    fi
    exit 0
}

stop_watchdog() {
    if pid_alive; then
        kill "$PID" 2>/dev/null || true
        local i=0
        while kill -0 "$PID" 2>/dev/null && [ "$i" -lt 20 ]; do
            sleep 0.1
            i=$((i + 1))
        done
        kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f "$PIDFILE" "$STATUSFILE" "$STATUSFILE.tmp."*
    return 0
}

case "${1:-status}" in
    start)
        start_watchdog
        ;;
    stop)
        stop_watchdog
        exit 0
        ;;
    restart)
        stop_watchdog
        start_watchdog
        ;;
    status)
        if pid_alive; then
            echo "running"
            exit 0
        fi
        echo "stopped"
        exit 1
        ;;
    check)
        check_once
        exit $?
        ;;
    run)
        run_loop
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|check}" >&2
        exit 64
        ;;
esac
