#!/bin/bash

logfile="REPLACELBPLOGDIR/Text2SIP.log"

# Write important progress messages both to the LoxBerry installation log
# (stdout) and to the plugin logfile. Long-running Pocket-TTS commands use
# run_progress() to show heartbeats without flooding the installation log.
log_line() {
    local level="$1"
    shift
    local message="<${level}> $*"
    printf '%s\n' "$message"
    printf '%s %s\n' "$(date '+%F %T')" "$message" >> "$logfile"
}

log_info()    { log_line INFO "$@"; }
log_ok()      { log_line OK "$@"; }
log_warning() { log_line WARNING "$@"; }
log_error()   { log_line ERROR "$@"; }

run_logged() {
    "$@" 2>&1 | tee -a "$logfile"
    return ${PIPESTATUS[0]}
}

# Run a potentially long command without flooding the LoxBerry installation
# log. A heartbeat is printed every 15 seconds so the user sees progress.
# Command output is only shown (last lines) when the command fails.
run_progress() {
    local description="$1"
    shift
    local tmp rc pid
    tmp="$(mktemp /run/shm/text2sip-postroot.XXXXXX)"

    log_info "$description"
    "$@" >"$tmp" 2>&1 &
    pid=$!

    local elapsed=0
    while kill -0 "$pid" 2>/dev/null; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [ $((elapsed % 15)) -eq 0 ] && kill -0 "$pid" 2>/dev/null; then
            log_info "$description ... still working"
        fi
    done

    wait "$pid"
    rc=$?
    if [ "$rc" -ne 0 ]; then
        log_warning "$description failed (exit=$rc); last output follows"
        tail -n 20 "$tmp" | tee -a "$logfile"
    fi
    rm -f "$tmp"
    return "$rc"
}

wait_for_dpkg() {
    local log="$1"
    local tries="${2:-60}"   # 60 * 2s = 120s

    log_info "Waiting for dpkg/apt locks ..."
    while \
        fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
        fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
        fuser /var/cache/apt/archives/lock >/dev/null 2>&1 || \
        pgrep -x apt >/dev/null 2>&1 || \
        pgrep -x apt-get >/dev/null 2>&1 || \
        pgrep -x dpkg >/dev/null 2>&1
    do
        sleep 2
        tries=$((tries - 1))
        if [ "$tries" -le 0 ]; then
            log_warning "dpkg lock wait timed out; continuing"
            break
        fi
    done
}

# -----------------------------------------------------------------------------
# Logfile
# -----------------------------------------------------------------------------
mkdir -p "$(dirname "$logfile")" 2>/dev/null || true
touch "$logfile"
chown loxberry:loxberry "$logfile" 2>/dev/null || true
chmod 660 "$logfile" 2>/dev/null || true

log_info "Text2SIP POSTROOT started"

# -----------------------------------------------------------------------------
# Runtime dependencies
# -----------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
ARCH="$(dpkg --print-architecture 2>/dev/null || true)"
[ -n "$ARCH" ] || ARCH="$(uname -m)"

if [ -r /etc/os-release ]; then
    . /etc/os-release
    log_info "Detected ${PRETTY_NAME:-Linux}; architecture=$ARCH"
else
    log_info "Detected architecture=$ARCH"
fi

# Python, ffmpeg/ffprobe, wget and CA certificates are part of the LoxBerry
# standard image. Text2SIP therefore does not declare them as plugin APT
# dependencies. Use the distro default Python supplied by LoxBerry.
PYTHON_BIN="/usr/bin/python3"

# task-spooler is the only additional runtime package Text2SIP needs. Do not
# declare it through dpkg/apt12 or apt13, because LoxBerry would reinstall it
# on every plugin upgrade. Install it only once when the tsp binary is missing.
if command -v tsp >/dev/null 2>&1; then
    log_ok "task-spooler available: $(command -v tsp)"
else
    log_info "task-spooler is missing; installing it once"
    wait_for_dpkg "$logfile" 60
    # Refresh package lists only on a real first-install/missing-package case.
    run_logged apt-get update || log_warning "APT update failed; trying task-spooler install with existing package lists"
    wait_for_dpkg "$logfile" 60
    if run_logged apt-get install -y --no-install-recommends task-spooler && command -v tsp >/dev/null 2>&1; then
        log_ok "task-spooler installed successfully: $(command -v tsp)"
    else
        log_error "task-spooler installation failed; Text2SIP cannot queue calls"
        exit 1
    fi
fi

if command -v ffmpeg >/dev/null 2>&1; then
    log_ok "ffmpeg available: $(command -v ffmpeg)"
else
    log_warning "ffmpeg is unavailable"
fi

if command -v ffprobe >/dev/null 2>&1; then
    log_ok "ffprobe available: $(command -v ffprobe)"
else
    log_warning "ffprobe is unavailable; pjsua duration detection will use its fallback"
fi

# -----------------------------------------------------------------------------
# Pocket-TTS offline provider
# -----------------------------------------------------------------------------
# Plugin code stays in bin/. The generated Python runtime, model cache and
# installed-language markers live in data/ and are preserved across upgrades by
# preupgrade.sh/postupgrade.sh. This prevents repeated model downloads and huge
# recursive delete logs.
POCKET_CODE="REPLACELBHOMEDIR/bin/plugins/text2sip/pockettts"
POCKET_DATA="REPLACELBHOMEDIR/data/plugins/text2sip/pockettts"
POCKET_VENV="$POCKET_DATA/venv"
POCKET_CLI="$POCKET_VENV/bin/pocket-tts"
POCKET_HELPER="$POCKET_CODE/pockettts_language.sh"
POCKET_SERVER_CTL="$POCKET_CODE/pockettts_server.sh"
POCKET_WATCHDOG_CTL="$POCKET_CODE/pockettts_watchdog.sh"
POCKET_CACHE="$POCKET_DATA/cache"
POCKET_STATE="$POCKET_DATA/languages"

log_info "Preparing Pocket-TTS offline provider ..."
mkdir -p "$POCKET_CACHE" "$POCKET_STATE" /run/shm/text2sip-pockettts 2>/dev/null || true
chown -R loxberry:loxberry "$POCKET_DATA" /run/shm/text2sip-pockettts 2>/dev/null || true
chmod 775 "$POCKET_DATA" "$POCKET_CACHE" "$POCKET_STATE" /run/shm/text2sip-pockettts 2>/dev/null || true

for POCKET_SCRIPT in "$POCKET_HELPER" "$POCKET_SERVER_CTL" "$POCKET_WATCHDOG_CTL"; do
    if [ -f "$POCKET_SCRIPT" ]; then
        chown root:loxberry "$POCKET_SCRIPT" 2>/dev/null || true
        chmod 755 "$POCKET_SCRIPT" 2>/dev/null || true
    fi
done

if [ -x "$PYTHON_BIN" ]; then
    SYS_PY_VER="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    log_info "Pocket-TTS Python: $($PYTHON_BIN --version 2>&1)"

    # A preserved venv can only be reused with the same Python major/minor.
    # This automatically rebuilds the runtime after e.g. Bookworm -> Trixie.
    VENV_PY_VER=""
    if [ -x "$POCKET_VENV/bin/python" ]; then
        VENV_PY_VER="$($POCKET_VENV/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    fi
    if [ -n "$VENV_PY_VER" ] && [ "$VENV_PY_VER" != "$SYS_PY_VER" ]; then
        log_info "Python changed from $VENV_PY_VER to $SYS_PY_VER; rebuilding Pocket-TTS runtime"
        rm -rf "$POCKET_VENV" >/dev/null 2>&1 || true
    fi

    if [ ! -x "$POCKET_VENV/bin/python" ]; then
        if run_progress "Creating Pocket-TTS virtual environment" "$PYTHON_BIN" -m venv "$POCKET_VENV"; then
            log_ok "Pocket-TTS virtual environment created"
        else
            log_warning "Could not create Pocket-TTS virtual environment"
        fi
    else
        log_ok "Existing Pocket-TTS virtual environment reused"
    fi

    if [ -x "$POCKET_VENV/bin/python" ]; then
        POCKET_INSTALLED="$($POCKET_VENV/bin/python -c 'import importlib.metadata; print(importlib.metadata.version("pocket-tts"))' 2>/dev/null || true)"
        TORCH_OK=0
        "$POCKET_VENV/bin/python" -c 'import torch' >/dev/null 2>&1 && TORCH_OK=1

        if [ "$POCKET_INSTALLED" = "2.1.0" ] && [ "$TORCH_OK" -eq 1 ]; then
            log_ok "Pocket-TTS 2.1.0 runtime already installed - no package download required"
        else
            if run_progress "Updating Python packaging tools" \
                "$POCKET_VENV/bin/python" -m pip install --upgrade --disable-pip-version-check pip setuptools wheel; then
                log_ok "Python packaging tools are ready"
            else
                log_warning "Python packaging tools could not be updated; continuing"
            fi

            # Install the CPU build first so x86 installations do not pull CUDA
            # runtime packages from the default PyPI index. If this step fails,
            # do NOT continue with Pocket-TTS: its normal dependency resolution
            # could otherwise pull a regular/GPU PyTorch build and NVIDIA/CUDA
            # packages from PyPI.
            CPU_TORCH_READY=0
            if run_progress "Installing CPU PyTorch for Pocket-TTS" \
                "$POCKET_VENV/bin/python" -m pip install --disable-pip-version-check \
                --index-url https://download.pytorch.org/whl/cpu 'torch>=2.5.0'; then
                if "$POCKET_VENV/bin/python" -c 'import torch' >/dev/null 2>&1; then
                    CPU_TORCH_READY=1
                    log_ok "CPU PyTorch is ready"
                else
                    log_error "CPU PyTorch was installed but cannot be imported; Pocket-TTS package installation skipped"
                fi
            else
                log_error "CPU PyTorch installation failed; Pocket-TTS package installation skipped"
            fi

            if [ "$CPU_TORCH_READY" -eq 1 ]; then
                if run_progress "Installing Pocket-TTS 2.1.0 and dependencies" \
                    "$POCKET_VENV/bin/python" -m pip install --disable-pip-version-check 'pocket-tts==2.1.0'; then
                    log_ok "Pocket-TTS 2.1.0 is installed"
                else
                    log_warning "Pocket-TTS package installation failed"
                fi
            fi
        fi
    fi
else
    log_error "Pocket-TTS Python interpreter not available: $PYTHON_BIN"
fi

# German is mandatory. The model cache and marker are persistent, so after the
# first successful installation this becomes a fast status check. Other
# languages are still downloaded only when selected in the plugin UI.
if [ -x "$POCKET_CLI" ] && [ -x "$POCKET_HELPER" ]; then
    chown -R loxberry:loxberry "$POCKET_DATA" 2>/dev/null || true
    if [ -f "$POCKET_STATE/de.ready" ]; then
        log_ok "German Pocket-TTS model already available - no download required"
    else
        if run_progress "Downloading/preparing German Pocket-TTS model (juergen)" \
            runuser -u loxberry -- env POCKETTTS_STDOUT=1 "$POCKET_HELPER" install de; then
            log_ok "Pocket-TTS German model is ready"
        else
            log_error "Pocket-TTS German model could not be prepared; offline TTS is unavailable"
        fi
    fi
else
    log_error "Pocket-TTS installation incomplete; offline TTS is unavailable"
fi

# Keep generated data writable by the CGI user and movable by PREUPGRADE.
if [ -d "$POCKET_DATA" ]; then
    chown -R loxberry:loxberry "$POCKET_DATA" 2>/dev/null || true
fi

# -----------------------------------------------------------------------------
# Architecture-specific PJSUA binaries
# -----------------------------------------------------------------------------
PJSUA_BASE="REPLACELBHOMEDIR/data/plugins/text2sip"
for PJSUA_ARCH in amd64 arm64 armhf; do
    PJSUA_BIN="$PJSUA_BASE/$PJSUA_ARCH/pjsua-$PJSUA_ARCH"
    if [ -f "$PJSUA_BIN" ]; then
        chown loxberry:loxberry "$PJSUA_BIN" >> "$logfile" 2>&1 || true
        chmod 755 "$PJSUA_BIN" >> "$logfile" 2>&1 || true
        log_ok "PJSUA binary prepared: $PJSUA_BIN"
    else
        log_warning "PJSUA binary not found: $PJSUA_BIN"
    fi
done

# -----------------------------------------------------------------------------
# One-time cleanup of legacy Text2SIP Mosquitto bridge artifacts.
log_info "Checking legacy Text2SIP bridge artifacts ..."
# The current plugin talks directly to either the internal or external broker.
# -----------------------------------------------------------------------------
legacy_mosquitto_changed=0
legacy_bridge_detected=0
legacy_bridge_host=""
legacy_bridge_conf="/etc/mosquitto/conf.d/30-bridge-t2s.conf"

# Older bridge versions could add the bridge target hostname to /etc/hosts.
# Capture that hostname BEFORE 30-bridge-t2s.conf is removed.
if [ -r "$legacy_bridge_conf" ]; then
    legacy_bridge_detected=1
    legacy_bridge_host="$(awk '
        $1 == "address" {
            host = $2
            sub(/:[0-9]+$/, "", host)
            print host
            exit
        }
    ' "$legacy_bridge_conf" 2>/dev/null)"
fi

# If the bridge config is already gone, try to recover the former host from an
# old Text2SIP certificate bundle. Search both the live config and the temporary
# pre-upgrade backup so this works independently of upgrade-script ordering.
find_legacy_bridge_host_from_bundle() {
    local bridge_dir bundle member info host
    for bridge_dir in \
        "REPLACELBPCONFIGDIR/bridge" \
        "/tmp/REPLACELBPPLUGINDIR/bridge"
    do
        [ -d "$bridge_dir" ] || continue
        for bundle in "$bridge_dir"/t2s_bundle*.tar.gz; do
            [ -r "$bundle" ] || continue
            member="$(tar -tzf "$bundle" 2>/dev/null | awk '/(^|\/)master\.info$/ { print; exit }')"
            [ -n "$member" ] || continue
            info="$(tar -xOf "$bundle" "$member" 2>/dev/null || true)"
            [ -n "$info" ] || continue

            # master.info historically existed as KEY=VALUE or JSON.
            host="$(printf '%s\n' "$info" | sed -nE \
                's/^[[:space:]]*(HOST|MASTER_HOST)[[:space:]]*[:=][[:space:]]*([^[:space:]"]+).*/\2/p' | head -n 1)"
            if [ -z "$host" ]; then
                host="$(printf '%s' "$info" | tr '\n' ' ' | sed -nE \
                    's/.*"(HOST|MASTER_HOST)"[[:space:]]*:[[:space:]]*"([^"]+)".*/\2/p')"
            fi
            if [ -n "$host" ]; then
                printf '%s\n' "$host"
                return 0
            fi
        done
    done
    return 1
}

if [ -z "$legacy_bridge_host" ]; then
    legacy_bridge_host="$(find_legacy_bridge_host_from_bundle || true)"
fi

# Remember whether any old bridge installation is present before deleting it.
for legacy_probe in \
    /etc/mosquitto/conf.d/30-bridge-t2s.conf \
    /etc/mosquitto/role/sip-bridge \
    /etc/mosquitto/sip-uninstall.pl \
    /etc/mosquitto/certs/sip-bridge \
    /etc/mosquitto/conf.d/mosq_mqttgateway.conf.disabled \
    /etc/mosquitto/conf.d/mosq_passwd.disabled \
    /etc/mosquitto/conf.d/disabled/mosq_mqttgateway.conf \
    /etc/mosquitto/conf.d/disabled/mosq_passwd
do
    if [ -e "$legacy_probe" ]; then
        legacy_bridge_detected=1
        break
    fi
done

for legacy_file in \
    /etc/mosquitto/conf.d/30-bridge-t2s.conf \
    /etc/mosquitto/role/sip-bridge \
    /etc/mosquitto/sip-uninstall.pl
do
    if [ -e "$legacy_file" ]; then
        rm -f "$legacy_file" && legacy_mosquitto_changed=1
        echo "<INFO> Removed legacy Text2SIP bridge artifact: $legacy_file" >> "$logfile"
    fi
done

if [ -d /etc/mosquitto/certs/sip-bridge ]; then
    rm -rf /etc/mosquitto/certs/sip-bridge
    legacy_mosquitto_changed=1
    echo "<INFO> Removed legacy Text2SIP bridge certificate directory" >> "$logfile"
fi

# Restore Mosquitto files which older Text2SIP bridge versions disabled.
# Never remove /etc/mosquitto/ca or the shared mosq-ca.crt here.
restore_mosquitto_file() {
    src="$1"
    dst="$2"
    if [ -e "$src" ]; then
        if [ ! -e "$dst" ]; then
            mv -f "$src" "$dst"
            echo "<INFO> Restored Mosquitto config: $dst" >> "$logfile"
        else
            rm -f "$src"
            echo "<INFO> Removed obsolete disabled duplicate: $src" >> "$logfile"
        fi
        legacy_mosquitto_changed=1
    fi
}

restore_mosquitto_file /etc/mosquitto/conf.d/mosq_mqttgateway.conf.disabled /etc/mosquitto/conf.d/mosq_mqttgateway.conf
restore_mosquitto_file /etc/mosquitto/conf.d/mosq_passwd.disabled /etc/mosquitto/conf.d/mosq_passwd
restore_mosquitto_file /etc/mosquitto/conf.d/disabled/mosq_mqttgateway.conf /etc/mosquitto/conf.d/mosq_mqttgateway.conf
restore_mosquitto_file /etc/mosquitto/conf.d/disabled/mosq_passwd /etc/mosquitto/conf.d/mosq_passwd
rmdir /etc/mosquitto/conf.d/disabled 2>/dev/null || true

# Remove only the hostname previously used by the Text2SIP bridge from
# /etc/hosts. Do not touch unrelated host entries. Historical bridge installs
# used t2s.local as their default when no explicit HOST/MASTER_HOST was set.
remove_legacy_hosts_entry() {
    local host="$1"
    local hosts_file="/etc/hosts"
    local tmp_file

    [ -n "$host" ] || return 0
    [ -f "$hosts_file" ] || return 0

    # The old installer did not create /etc/hosts entries when the bridge host
    # itself was an IPv4 address.
    if printf '%s' "$host" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$'; then
        return 0
    fi

    # Accept only a normal hostname token before using it as a lookup value.
    if ! printf '%s' "$host" | grep -Eq '^[A-Za-z0-9._-]+$'; then
        echo "<WARNING> Refusing unsafe legacy bridge hostname for /etc/hosts cleanup: $host" >> "$logfile"
        return 0
    fi

    if ! awk -v host="$host" '
        /^[[:space:]]*#/ { next }
        {
            for (i = 2; i <= NF; i++) {
                if ($i == host) { found = 1; exit }
            }
        }
        END { exit(found ? 0 : 1) }
    ' "$hosts_file"; then
        return 0
    fi

    tmp_file="$(mktemp /run/shm/text2sip-hosts.XXXXXX)" || {
        echo "<WARNING> Could not create temporary file for /etc/hosts cleanup" >> "$logfile"
        return 0
    }

    if awk -v host="$host" '
        /^[[:space:]]*#/ { print; next }
        {
            remove = 0
            for (i = 2; i <= NF; i++) {
                if ($i == host) { remove = 1; break }
            }
            if (!remove) print
        }
    ' "$hosts_file" > "$tmp_file" && cat "$tmp_file" > "$hosts_file"; then
        echo "<INFO> Removed legacy Text2SIP bridge host from /etc/hosts: $host" >> "$logfile"
    else
        echo "<WARNING> Could not remove legacy Text2SIP bridge host from /etc/hosts: $host" >> "$logfile"
    fi
    rm -f "$tmp_file"
}

if [ -n "$legacy_bridge_host" ]; then
    remove_legacy_hosts_entry "$legacy_bridge_host"
elif [ "$legacy_bridge_detected" -eq 1 ]; then
    # Safe fallback for bridge remnants where 30-bridge-t2s.conf/bundle has
    # already disappeared: t2s.local was the historical default bridge host.
    remove_legacy_hosts_entry "t2s.local"
fi

if [ "$legacy_mosquitto_changed" -eq 1 ]; then
    systemctl restart mosquitto >> "$logfile" 2>&1 || true
fi

# -----------------------------------------------------------------------------
# Idempotent Text2SIP runtime setup via installed daemon script
# -----------------------------------------------------------------------------
daemon_script="REPLACELBHOMEDIR/system/daemons/plugins/Text2SIP"
if [ -f "$daemon_script" ]; then
    log_info "Running Text2SIP runtime setup ..."
    run_logged /bin/bash "$daemon_script" || true
else
    log_warning "Text2SIP daemon script not found: $daemon_script"
fi

# Keep installation deterministic: German is the mandatory base model and is
# always made resident after install/upgrade. Runtime/UI language selections can
# switch the single resident compact model later. This also avoids warming the
# German voice against a different model that happened to be resident before an
# upgrade.
if [ -x "$POCKET_SERVER_CTL" ] && [ -f "$POCKET_STATE/de.ready" ]; then
    runuser -u loxberry -- "$POCKET_SERVER_CTL" ensure german >/dev/null 2>&1 || true
    log_info "Waiting for resident German Pocket-TTS server ..."
    POCKET_SERVER_READY=0
    POCKET_WAIT=0
    while [ "$POCKET_WAIT" -lt 45 ]; do
        if runuser -u loxberry -- "$POCKET_SERVER_CTL" health >/dev/null 2>&1; then
            POCKET_SERVER_READY=1
            break
        fi
        sleep 1
        POCKET_WAIT=$((POCKET_WAIT + 1))
        if [ $((POCKET_WAIT % 10)) -eq 0 ]; then
            log_info "Pocket-TTS server is still loading ... (${POCKET_WAIT}s)"
        fi
    done

    if [ "$POCKET_SERVER_READY" -eq 1 ]; then
        log_ok "Resident German Pocket-TTS server is ready"
        if run_progress "Warming resident Pocket-TTS voice 'juergen'" \
            runuser -u loxberry -- /usr/bin/wget -q -T 120 -O /dev/null \
            --header='Content-Type: application/x-www-form-urlencoded' \
            --post-data='text=Test&voice_url=juergen' \
            'http://127.0.0.1:8765/tts'; then
            log_ok "Resident Pocket-TTS voice 'juergen' is warm"
        else
            log_warning "Pocket-TTS voice warm-up failed; normal server/CLI fallback remains available"
        fi

        # Refresh the RAM status once after installation/warm-up so the UI can
        # show a current green state immediately instead of waiting for the next
        # two-minute watchdog interval.
        if [ -x "$POCKET_WATCHDOG_CTL" ]; then
            runuser -u loxberry -- "$POCKET_WATCHDOG_CTL" check >/dev/null 2>&1 || true
        fi
    else
        log_warning "Resident Pocket-TTS server did not become ready within 45 seconds; CLI fallback remains available"
    fi
fi

log_ok "Text2SIP POSTROOT completed"
exit 0
