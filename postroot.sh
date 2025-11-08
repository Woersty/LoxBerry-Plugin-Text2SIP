#!/bin/bash

logfile="REPLACELBPLOGDIR/Text2SIP.log"

# --- Hilfsfunktion: auf apt/dpkg-Locks warten (max ~2 Min) ---
wait_for_dpkg() {
  local LOG="$1"; shift || true
  local tries=${1:-60}   # 60 * 2s = 120s
  echo "$(date '+%F %T') Waiting for dpkg/apt locks ..." >> "$LOG"
  while \
    fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
    fuser /var/lib/apt/lists/lock   >/dev/null 2>&1 || \
    fuser /var/cache/apt/archives/lock >/dev/null 2>&1 || \
    pgrep -x apt >/dev/null || pgrep -x apt-get >/dev/null || pgrep -x dpkg >/dev/null
  do
    sleep 2
    tries=$((tries-1))
    if [ "$tries" -le 0 ]; then
      echo "$(date '+%F %T') dpkg lock wait timed out, continue anyway" >> "$LOG"
      break
    fi
  done
  echo "$(date '+%F %T') dpkg/apt locks are free" >> "$LOG"
}

# --- Logfile vorbereiten ---
date                                  >> "$logfile" 2>&1
echo "### Postroot: deps & locale" >> "$logfile" 2>&1
touch "$logfile"
chown loxberry:loxberry "$logfile"    >> "$logfile" 2>&1 || true
chmod 660 "$logfile"                  >> "$logfile" 2>&1 || true

# --- Pico/Locales: handled entirely in postroot (daemon does nothing) ---
export DEBIAN_FRONTEND=noninteractive

# Optionale Pfade zu euren Bullseye-Bundle-DEBs (nur genutzt auf Bullseye)
PICO_DEB_DIR="REPLACELBHOMEDIR/data/plugins/text2sip/debs"
PICO_DATA_DEB="$PICO_DEB_DIR/libttspico-data_1.0+git20130326-11_all.deb"
PICO_LIB_DEB="$PICO_DEB_DIR/libttspico0_1.0+git20130326-11_amd64.deb"
PICO_UTIL_DEB="$PICO_DEB_DIR/libttspico-utils_1.0+git20130326-11_amd64.deb"

# OS erkennen
. /etc/os-release
echo "<INFO> postroot: detected ${PRETTY_NAME} (${VERSION_CODENAME})" >> "$logfile" 2>&1

# APT vorbereiten
wait_for_dpkg "$logfile" 60
apt-get update -y                                  >> "$logfile" 2>&1 || true
wait_for_dpkg "$logfile" 60
apt-get install -y --no-install-recommends \
  ffmpeg locales libttspico-utils libttspico-data libttspico0 \
                                                   >> "$logfile" 2>&1 || true

# Bookworm: sicherstellen, dass die Repo-Versionen (-13) aktiv sind (keine lokalen Downgrades!)
if [ "${VERSION_CODENAME}" = "bookworm" ]; then
  echo "<DEB> postroot: bookworm → enforce pico -13 from repo (no downgrade)" >> "$logfile" 2>&1
  wait_for_dpkg "$logfile" 60
  apt-get install -y --reinstall \
    libttspico-utils libttspico-data libttspico0   >> "$logfile" 2>&1 || true
else
  # Bullseye: falls gewünscht, gebündelte -11-DEBs installieren
  if [ -r "$PICO_DATA_DEB" ] && [ -r "$PICO_LIB_DEB" ] && [ -r "$PICO_UTIL_DEB" ]; then
    echo "<DEB> postroot: bullseye → install bundled pico -11 debs" >> "$logfile" 2>&1
    wait_for_dpkg "$logfile" 60
    dpkg -i "$PICO_DATA_DEB" "$PICO_LIB_DEB" "$PICO_UTIL_DEB"  >> "$logfile" 2>&1 || true
  else
    echo "<DEB> postroot: bullseye → bundled debs not found, keeping repo versions" >> "$logfile" 2>&1
  fi
fi

# Locales: UTF-8 generieren + Default setzen (non-interactive)
if ! locale | grep -qi 'UTF-8'; then
  echo "<DEB> postroot: generating locales de_DE.UTF-8 en_US.UTF-8 and setting default" >> "$logfile" 2>&1
  locale-gen de_DE.UTF-8 en_US.UTF-8              >> "$logfile" 2>&1 || true
  update-locale LANG=de_DE.UTF-8                  >> "$logfile" 2>&1 || true
fi

# Marker: Postroot hat Pico erledigt (nur zu Debugzwecken)
mkdir -p /var/lib/text2sip 2>/dev/null
echo "<DEB> pico-done:${VERSION_CODENAME}" > /var/lib/text2sip/pico-state
echo "<DEB> postroot: pico finalized (${VERSION_CODENAME})" >> "$logfile" 2>&1

# (Optional) Kurzprüfung ins Log
dpkg -l | awk '/libttspico/{print "postroot: " $1,$2,$3}' >> "$logfile" 2>&1 || true

echo "<INFO>  Postroot: deps & locale done" >> "$logfile" 2>&1

# --- Copy uninstall helper ---
cp -p -v $5/webfrontend/htmlauth/plugins/$3/bin/uninstall_sip_client_bridge.pl /etc/mosquitto/sip-uninstall.pl
echo "<OK> sip-uninstall.pl has been copied to /etc/mosquitto"

# --- Dein bisheriger Teil: Daemon starten ---
echo "<INFO> Start Text2SIP installation, for further infos see Plugin logfile" >> "$logfile" 2>&1
bash $5/system/daemons/plugins/Text2SIP >> "$logfile" 2>&1 &

# ===== Verify MQTT Gateway process status =====
echo "<INFO> Checking MQTT Gateway runtime state …"
MQTT_PROC="REPLACELBHOMEDIR/sbin/mqttgateway.pl"

# Prüfen, ob der Prozess läuft
if pgrep -f "$MQTT_PROC" >/dev/null 2>&1; then
    PID=$(pgrep -f "$MQTT_PROC" | head -n1)
    echo "<OK> MQTT Gateway is active (PID $PID)"
else
    echo "<WARNING> MQTT Gateway not running – attempting to start manually ..."
    REPLACELBHOMEDIR/sbin/mqtt-handler.pl action=startgateway >/dev/null 2>&1
    sleep 2
    if pgrep -f "$MQTT_PROC" >/dev/null 2>&1; then
        PID=$(pgrep -f "$MQTT_PROC" | head -n1)
        echo "<OK> MQTT Gateway started successfully (PID $PID)"
    else
        echo "<ERROR> Could not start MQTT Gateway – please check REPLACELBHOMEDIR/log/system_tmpfs/mqttgateway.log"
    fi
fi

exit 0
