#!/bin/bash
# ic_cred.sh — Secure ingestion of remote_mqtt_config.json (Bash)
# - T2S_IP from [default] in Text2SIP.cfg may be IPv4 or hostname/FQDN (quotes ok)
# - Resolves hostname to IPv4 for diagnostics; CIFS/SMB uses the hostname directly
# - Verifies host looks like LoxBerry (SMB shares or HTTP banner) before mounting
# - Tries //HOST/plugindata/text2speech/mqtt/remote_mqtt_config.json, then …/text2speech/remote_mqtt_config.json
# - Encrypts locally (GPG loopback; passphrase in RAM), best-effort remote delete
# - Writes ONLY /opt/loxberry/config/plugins/text2sip/remote_mqtt_config.json
# - English logging when DEBUG_USE=on

set -euo pipefail

# ===== Static paths =====
CFG_FILE="/opt/loxberry/config/plugins/text2sip/Text2SIP.cfg"
REMOTE_MOUNT="/mnt/remote_text2speech"
ENCRYPTED_DIR="/opt/loxberry/webfrontend/htmlauth/plugins/text2sip/bin"
HASH_FILE="$ENCRYPTED_DIR/credentials.hash"
JSON_OUT="/opt/loxberry/config/plugins/text2sip/remote_mqtt_config.json"
LOG_FILE="/opt/loxberry/log/plugins/text2sip/mqtt_transfer_creds.log"
REMOTE_PATHS=("text2speech/mqtt/remote_mqtt_config.json" "text2speech/remote_mqtt_config.json")

# ===== LoxBerry user/group =====
LB_USER="${LB_USER:-loxberry}"
if id "$LB_USER" >/dev/null 2>&1; then
  LB_UID="$(id -u "$LB_USER")"
  LB_GID="$(id -g "$LB_USER")"
else
  LB_USER="$(id -un)"
  LB_UID="$(id -u)"
  LB_GID="$(id -g)"
fi

# ===== Logging =====
DEBUG_USE="$(grep -E '^DEBUG_USE=' "$CFG_FILE" 2>/dev/null | cut -d '=' -f2 || true)"
LOGGING_ENABLED=0; [ "${DEBUG_USE:-off}" = "on" ] && LOGGING_ENABLED=1
log(){ [ "$LOGGING_ENABLED" -eq 1 ] && echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"; }
error_exit(){ echo "$(date '+%Y-%m-%d %H:%M:%S') - ❌ ERROR: $1" | tee -a "$LOG_FILE"; exit 1; }
run(){ local CMD=("$@"); if ! "${CMD[@]}" 2>/dev/null; then sudo "${CMD[@]}" || error_exit "Command failed: ${CMD[*]}"; fi; }

# Prepare dirs/files and ownership for loxberry
run mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$JSON_OUT")" "$ENCRYPTED_DIR"
[ ! -f "$LOG_FILE" ] && run install -o "$LB_USER" -g "$LB_USER" -m 664 /dev/null "$LOG_FILE"
run chown -R "$LB_USER:$LB_USER" "$(dirname "$LOG_FILE")" "$(dirname "$JSON_OUT")" "$ENCRYPTED_DIR" 2>/dev/null || true

# ===== Parse T2S_IP from [default] (strip quotes) =====
[ -f "$CFG_FILE" ] || error_exit "Config not found: $CFG_FILE"
T2S_IP="$(
  awk '
    /^\[/{ in_default = ($0=="[default]"); next }
    in_default && /^T2S_IP[ \t]*=/{ 
      sub(/^[^=]*=/,"");
      gsub(/^[ \t\r\n]+|[ \t\r\n]+$/,"");
      gsub(/^"+|"+$/,""); gsub(/^'\''+|'\''+$/,"");
      print; exit
    }
  ' "$CFG_FILE"
)"
[ -z "${T2S_IP:-}" ] && error_exit "Missing T2S_IP in [default] of $CFG_FILE"

# ===== Host/IPv4 resolution (relaxed) =====
is_ipv4(){ [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; }
resolve_host_ipv4(){
  local host="$1"
  if getent hosts "$host" >/dev/null 2>&1; then
    getent hosts "$host" | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/{print $1; exit}'; return 0
  fi
  if getent ahostsv4 "$host" >/dev/null 2>&1; then
    getent ahostsv4 "$host" | awk '/STREAM|RAW|DGRAM/ {print $1; exit}'; return 0
  fi
  if getent ahosts "$host" >/dev/null 2>&1; then
    getent ahosts "$host" | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/{print $1; exit}'; return 0
  fi
  return 1
}

REMOTE_HOST="$T2S_IP"
RESOLVED_IP=""

if is_ipv4 "$REMOTE_HOST"; then
  RESOLVED_IP="$REMOTE_HOST"; log "ℹ️ Using IPv4 from cfg: $REMOTE_HOST"
else
  if RESOLVED_IP="$(resolve_host_ipv4 "$REMOTE_HOST")"; then
    log "ℹ️ Hostname resolved: $REMOTE_HOST → $RESOLVED_IP"
  else
    log "ℹ️ Hostname '$REMOTE_HOST' did not resolve via getent — trying SMB probe…"
    if command -v smbclient >/dev/null 2>&1; then
      smbclient -N -L "//$REMOTE_HOST" >/dev/null 2>&1 \
        && log "ℹ️ SMB probe succeeded for //$REMOTE_HOST — continuing without DNS A record." \
        || error_exit "T2S_IP is neither IPv4 nor resolvable hostname, and SMB probe failed for '$REMOTE_HOST'"
    else
      error_exit "T2S_IP is neither IPv4 nor resolvable hostname, and smbclient is unavailable to probe '$REMOTE_HOST'"
    fi
  fi
fi

REMOTE_SHARE="//${REMOTE_HOST}/plugindata"

# ===== Verify host looks like a LoxBerry =====
verify_loxberry_host() {
  local host="$1"
  if command -v ping >/dev/null 2>&1; then
    local target="${RESOLVED_IP:-$host}"
    ping -c1 -W1 "$target" >/dev/null 2>&1 || log "⚠️ Host $host ($target) did not answer ping (continuing checks)."
  fi
  if command -v smbclient >/dev/null 2>&1; then
    local out; out="$(smbclient -N -L "//$host" 2>/dev/null || true)"
    if echo "$out" | grep -qE '^[[:space:]]*(plugindata|loxberry|XL)[[:space:]]+Disk'; then
      log "🟢 LoxBerry verified via SMB shares on //$host."; return 0
    else
      log "ℹ️ SMB share probe did not match expected names on //$host."
    fi
  fi
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --max-time 3 "http://$host/" | grep -qi 'LoxBerry' \
      && { log "🟢 LoxBerry verified via HTTP banner at http://$host/."; return 0; } \
      || log "ℹ️ HTTP banner at http://$host/ did not indicate a LoxBerry Installation"
  fi
  return 1
}
verify_loxberry_host "$REMOTE_HOST" || error_exit "Host $REMOTE_HOST does not look like a LoxBerry."

# ===== Passphrase file in RAM =====
pick_ram_dir(){ for d in /dev/shm /run /tmp; do [ -d "$d" ] && echo "$d" && return 0; done; return 1; }
ensure_passfile(){
  for f in /dev/shm/t2s_gpg.pass /run/t2s_gpg.pass /tmp/t2s_gpg.pass; do
    [ -r "$f" ] && { echo "$f"; return 0; }
  done
  local d; d="$(pick_ram_dir)" || return 1
  local tmp; tmp="$(mktemp "$d/.t2s_gpg.pass.XXXXXX")" || return 1
  umask 077; head -c32 /dev/urandom | base64 > "$tmp"; chmod 600 "$tmp"
  local final="$d/t2s_gpg.pass"; mv -f "$tmp" "$final"; echo "$final"
}
PASSPHRASE_FILE="$(ensure_passfile)" || error_exit "Could not create/find GPG passphrase file."

# ===== Cleanup / Unmount guard =====
MOUNTED=0; ENCRYPTED_FILE=""; DECRYPTED_FILE=""
cleanup(){
  if [ "$MOUNTED" -eq 1 ] && mountpoint -q "$REMOTE_MOUNT"; then
    log "📤 Unmounting remote share (cleanup)…"; run umount "$REMOTE_MOUNT" || true
  fi
  [ -n "${DECRYPTED_FILE:-}" ] && rm -f "$DECRYPTED_FILE" 2>/dev/null || true
  [ -n "${ENCRYPTED_FILE:-}" ] && rm -f "$ENCRYPTED_FILE" 2>/dev/null || true
}
trap cleanup EXIT

# ===== Mount (guest) mapped to loxberry uid/gid =====
mountpoint -q "$REMOTE_MOUNT" && { log "🔁 Remote share already mounted. Unmounting…"; run umount "$REMOTE_MOUNT"; }
log "🔄 Mounting remote share…"; run mkdir -p "$REMOTE_MOUNT"

SMB_VERSIONS=("3.0" "2.1" "2.0" "1.0"); MOUNT_SUCCESS=0
for VER in "${SMB_VERSIONS[@]}"; do
  log "🔍 Trying SMB version: $VER"
  if sudo mount -t cifs "$REMOTE_SHARE" "$REMOTE_MOUNT" \
       -o "username=guest,password=,rw,noperm,nounix,noserverino,vers=$VER,uid=$LB_UID,gid=$LB_GID,file_mode=0664,dir_mode=0775"; then
    log "✅ Mount successful (SMB $VER)"; MOUNT_SUCCESS=1; MOUNTED=1; break
  else
    log "⚠️ Mount failed (SMB $VER)"; mountpoint -q "$REMOTE_MOUNT" && run umount "$REMOTE_MOUNT"
  fi
done
[ "$MOUNT_SUCCESS" -ne 1 ] && error_exit "Mount failed for all tested SMB versions."

# ===== Locate file (check /mqtt first, then without) =====
FOUND_FILE=""
for rel in "${REMOTE_PATHS[@]}"; do
  p="$REMOTE_MOUNT/$rel"
  if [ -f "$p" ] && head -c1 "$p" >/dev/null 2>&1; then FOUND_FILE="$p"; log "📦 Found file: $FOUND_FILE"; break
  else log "ℹ️ Not found or not readable: $rel"
  fi
done
[ -z "$FOUND_FILE" ] && { log "ℹ️ No credentials file found. Nothing to do."; exit 0; }

# ===== Sanity checks =====
[ -d "$ENCRYPTED_DIR" ] || error_exit "Target directory does not exist: $ENCRYPTED_DIR"
[ -w "$ENCRYPTED_DIR" ] || error_exit "No write permission in target directory: $ENCRYPTED_DIR"

FOUND_BASENAME="$(basename "$FOUND_FILE")"
ENCRYPTED_FILE="$ENCRYPTED_DIR/${FOUND_BASENAME}.gpg"
DECRYPTED_FILE="$ENCRYPTED_DIR/${FOUND_BASENAME}"

# ===== Change detection =====
NEW_HASH="$(md5sum "$FOUND_FILE" | awk '{print $1}')"
OLD_HASH="$( [ -f "$HASH_FILE" ] && cat "$HASH_FILE" || true )"
if [ "${NEW_HASH:-}" = "${OLD_HASH:-}" ]; then
  log "⚠️ No changes detected (hash unchanged). Skipping."
  exit 0
fi

# ===== Encrypt =====
log "🔐 Change detected. Encrypting file…"
gpg --batch --yes --pinentry-mode loopback --passphrase-file "$PASSPHRASE_FILE" \
    -o "$ENCRYPTED_FILE" -c "$FOUND_FILE" 2>>"$LOG_FILE" || error_exit "GPG encryption failed."

# ===== Best-effort delete (do not abort on failure) =====
log "🗑️  Removing remote file after successful import…"
if ! rm -f "$FOUND_FILE" 2>>"$LOG_FILE"; then
  log "⚠️ Remote delete denied (permission). Continuing without deletion."
fi

# ===== Unmount ASAP =====
log "📤 Unmounting remote share…"; run umount "$REMOTE_MOUNT" || true; MOUNTED=0

# ===== Decrypt locally to process =====
log "🔓 Decrypting file…"
gpg --batch --yes --pinentry-mode loopback --passphrase-file "$PASSPHRASE_FILE" \
    -o "$DECRYPTED_FILE" -d "$ENCRYPTED_FILE" 2>>"$LOG_FILE" || error_exit "GPG decryption failed."
log "✅ File successfully transferred, encrypted and decrypted."

# ===== Install JSON (atomic) =====
TMPJSON="$(mktemp)"
cp -f "$DECRYPTED_FILE" "$TMPJSON"

# ---- inject host info into JSON (best-effort) ----
REMOTE_HOST_JSON="$REMOTE_HOST"
RESOLVED_IP_JSON="${RESOLVED_IP:-$REMOTE_HOST}"
if command -v jq >/dev/null 2>&1; then
  if jq --arg rh "$REMOTE_HOST_JSON" --arg rip "$RESOLVED_IP_JSON" \
        '. + {Remotehost:$rh, ResolvedIP:$rip}' "$TMPJSON" > "${TMPJSON}.new" 2>>"$LOG_FILE"; then
    mv -f "${TMPJSON}.new" "$TMPJSON"
    log "ℹ️ Augmented JSON with remote_host/resolved_ip."
  else
    log "⚠️ Could not augment JSON with jq; keeping original."
  fi
else
  log "ℹ️ jq not available; skipping JSON augmentation."
fi

# optional JSON validation (non-fatal)
if command -v jq >/dev/null 2>&1; then
  jq empty "$TMPJSON" 2>/dev/null || log "⚠️ JSON validation failed (jq). Keeping raw file."
fi

run mv -f "$TMPJSON" "$JSON_OUT"
run chown "$LB_USER:$LB_USER" "$JSON_OUT" 2>/dev/null || true
run chmod 640 "$JSON_OUT"
log "🧾 remote_mqtt_config.json updated: $JSON_OUT (owner $LB_USER:$LB_USER, mode 0640)"

# ===== Hash update AFTER success =====
echo "$NEW_HASH" > "$HASH_FILE"
run chown "$LB_USER:$LB_USER" "$HASH_FILE" 2>/dev/null || true

# ===== Cleanup =====
log "🧹 Cleaning up…"
rm -f "$DECRYPTED_FILE" "$ENCRYPTED_FILE" 2>/dev/null || true
log "✅ Done."
