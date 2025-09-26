SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
LOG_FILE=/opt/loxberry/log/plugins/text2sip/mqtt_transfer_creds.log
CFG_FILE=/opt/loxberry/config/plugins/text2sip/Text2SIP.cfg

set -euo pipefail
umask 077

# === T2S_IP gleich am Anfang prüfen (Quotes/Kommentare werden entfernt) ===
T2S_IP="$(
  awk '
    BEGIN { in_default=0 }
    /^[[:space:]]*[;#]/ { next }                    # volle Kommentarzeilen überspringen
    /^\[default\][[:space:]]*$/ { in_default=1; next }
    /^\[[^]]+\][[:space:]]*$/ { in_default=0; next }
    in_default && $0 ~ /^[[:space:]]*T2S_IP[[:space:]]*=/ {
      line=$0
      sub(/^[^=]*=/,"",line)                        # alles bis inkl. erstem "=" entfernen
      sub(/[;#].*$/,"",line)                        # Inline-Kommentare entfernen
      gsub(/"/,"",line)                             # Anführungszeichen entfernen
      gsub(/^[[:space:]]+|[[:space:]]+$/,"",line)   # trim
      print line
      exit
    }
  ' "$CFG_FILE"
)"

# Einfache IPv4-Form + Ausschluss
if [[ -z "${T2S_IP:-}" || ! "$T2S_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ || "$T2S_IP" == "127.0.0.1" || "$T2S_IP" == "0.0.0.0" ]]; then
  # stiller Exit, bevor Logging/Dateien angelegt werden
  exit 0
fi

# === Debug-Flag laden ===
DEBUG_USE="$(grep -E '^DEBUG_USE=' "$CFG_FILE" 2>/dev/null | cut -d '=' -f2 || true)"
LOGGING_ENABLED=0
[ "${DEBUG_USE:-off}" = "on" ] && LOGGING_ENABLED=1

# === Logging ===
log() {
    [ "$LOGGING_ENABLED" -eq 1 ] && echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}
error_exit() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ❌ ERROR: $1" | tee -a "$LOG_FILE"
    exit 1
}

# === sudo nur wenn nötig ===
run() {
    local CMD=("$@")
    if ! "${CMD[@]}" 2>/dev/null; then
        sudo "${CMD[@]}" || error_exit "Command failed: ${CMD[*]}"
    fi
}

# === Logfile vorbereiten ===
LOG_DIR=$(dirname "$LOG_FILE")
[ ! -d "$LOG_DIR" ] && run mkdir -p "$LOG_DIR"
[ ! -f "$LOG_FILE" ] && run touch "$LOG_FILE"
run chmod 664 "$LOG_FILE"

  # Reihenfolge: /dev/shm (RAM) → /run (RAM) → /tmp (Fallback)
  for CAND in /dev/shm /run /tmp; do
    if [ -d "$CAND" ]; then
	  log "🔄 PASS ROTATE executed"
      KEYFILE="$CAND/t2s_gpg.pass"
      # atomar schreiben, Rechte hart setzen
      TMPFILE="$(mktemp "$CAND/.t2s_gpg.pass.XXXXXX")"
      head -c 32 /dev/urandom | base64 > "$TMPFILE"
      chown loxberry:loxberry "$TMPFILE" || true
      chmod 600 "$TMPFILE"
      mv -f "$TMPFILE" "$KEYFILE"
      #echo "<OK> rotated $(date -Is) at $CAND" >> /opt/loxberry/log/plugins/text2sip/remote_mqtt.log
	  log "✅ rotated at $CAND"
      exit 0
    fi
  done
    log "⚠️ No candidate directory found"
  exit 1

