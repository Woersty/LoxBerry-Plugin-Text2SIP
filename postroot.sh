#!/bin/bash

logfile="REPLACELBPLOGDIR/Text2SIP.log"

wait_for_dpkg() {
    local log="$1"
    local tries="${2:-60}"   # 60 * 2s = 120s

    echo "$(date '+%F %T') Waiting for dpkg/apt locks ..." >> "$log"
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
            echo "$(date '+%F %T') dpkg lock wait timed out; continuing" >> "$log"
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

echo "$(date '+%F %T') <INFO> Text2SIP postroot started" >> "$logfile"

# -----------------------------------------------------------------------------
# Runtime dependencies / Pico fallback
# -----------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
ARCH="$(dpkg --print-architecture 2>/dev/null || true)"
[ -n "$ARCH" ] || ARCH="$(uname -m)"

if [ -r /etc/os-release ]; then
    . /etc/os-release
    echo "<INFO> Detected ${PRETTY_NAME:-Linux}; architecture=$ARCH" >> "$logfile"
else
    echo "<INFO> Detected architecture=$ARCH" >> "$logfile"
fi

wait_for_dpkg "$logfile" 60
apt-get update -y >> "$logfile" 2>&1 || true
wait_for_dpkg "$logfile" 60
apt-get install -y --no-install-recommends \
    ffmpeg locales sox wget libttspico-utils libttspico-data libttspico0 \
    >> "$logfile" 2>&1 || true

# Some Debian releases/architectures do not provide Pico in the active repo.
# If pico2wave is still missing, use the architecture-specific DEBs shipped
# below data/<arch>/ (when present in the full release archive).
if ! command -v pico2wave >/dev/null 2>&1; then
    PICO_DEB_DIR="REPLACELBHOMEDIR/data/plugins/text2sip/$ARCH"
    PICO_DATA_DEB="$(find "$PICO_DEB_DIR" -maxdepth 1 -type f -name 'libttspico-data_*_all.deb' -print -quit 2>/dev/null)"
    PICO_LIB_DEB="$(find "$PICO_DEB_DIR" -maxdepth 1 -type f -name "libttspico0_*_${ARCH}.deb" -print -quit 2>/dev/null)"
    PICO_UTIL_DEB="$(find "$PICO_DEB_DIR" -maxdepth 1 -type f -name "libttspico-utils_*_${ARCH}.deb" -print -quit 2>/dev/null)"

    if [ -n "$PICO_DATA_DEB" ] && [ -n "$PICO_LIB_DEB" ] && [ -n "$PICO_UTIL_DEB" ]; then
        echo "<INFO> Installing bundled Pico packages from $PICO_DEB_DIR" >> "$logfile"
        wait_for_dpkg "$logfile" 60
        dpkg -i "$PICO_DATA_DEB" "$PICO_LIB_DEB" "$PICO_UTIL_DEB" >> "$logfile" 2>&1 || true
        wait_for_dpkg "$logfile" 60
        apt-get -f install -y >> "$logfile" 2>&1 || true
    else
        echo "<WARNING> No complete bundled Pico package set found in $PICO_DEB_DIR" >> "$logfile"
    fi
fi

if command -v pico2wave >/dev/null 2>&1; then
    echo "<OK> pico2wave available: $(command -v pico2wave)" >> "$logfile"
else
    echo "<WARNING> pico2wave is unavailable; Pico fallback cannot be used" >> "$logfile"
fi

if command -v ffmpeg >/dev/null 2>&1; then
    echo "<OK> ffmpeg available: $(command -v ffmpeg)" >> "$logfile"
else
    echo "<WARNING> ffmpeg is unavailable" >> "$logfile"
fi

if command -v sox >/dev/null 2>&1; then
    echo "<OK> sox available: $(command -v sox)" >> "$logfile"
else
    echo "<WARNING> sox is unavailable; pjsua duration detection will use its fallback" >> "$logfile"
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
        echo "<OK> PJSUA binary prepared: $PJSUA_BIN" >> "$logfile"
    else
        echo "<WARNING> PJSUA binary not found: $PJSUA_BIN" >> "$logfile"
    fi
done

# -----------------------------------------------------------------------------
# One-time cleanup of legacy Text2SIP Mosquitto bridge artifacts.
# The current plugin talks directly to either the internal or external broker.
# -----------------------------------------------------------------------------
legacy_mosquitto_changed=0
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

if [ "$legacy_mosquitto_changed" -eq 1 ]; then
    systemctl restart mosquitto >> "$logfile" 2>&1 || true
fi

# -----------------------------------------------------------------------------
# Idempotent Text2SIP runtime setup via installed daemon script
# -----------------------------------------------------------------------------
daemon_script="REPLACELBHOMEDIR/system/daemons/plugins/Text2SIP"
if [ -f "$daemon_script" ]; then
    echo "<INFO> Running Text2SIP runtime setup" >> "$logfile"
    /bin/bash "$daemon_script" >> "$logfile" 2>&1 || true
else
    echo "<WARNING> Text2SIP daemon script not found: $daemon_script" >> "$logfile"
fi

echo "$(date '+%F %T') <OK> Text2SIP postroot completed" >> "$logfile"
exit 0
