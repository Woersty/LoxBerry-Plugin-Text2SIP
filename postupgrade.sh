#!/bin/sh

# Text2SIP postupgrade.sh
# Restores the persistent upgrade backup created by preupgrade.sh.
# No plugin-created /tmp backup directory is used.
# Runs as user "loxberry".
# Exit code 0: success
# Exit code 1: warning, installation continues
# Exit code 2: cancel installation

COMMAND=$0
PTEMPDIR=$1
PSHNAME=$2
PDIR=$3
PVERSION=$4
LBHOMEDIR=$5

log_info()    { echo "<INFO> $1"; }
log_ok()      { echo "<OK> $1"; }
log_warning() { echo "<WARNING> $1"; }
log_error()   { echo "<ERROR> $1"; }

abort_install_keep_backup() {
    log_error "$1"
    [ -n "$PERSISTENT_UPGRADE_DIR" ] && log_error "Persistent upgrade backup kept for recovery: $PERSISTENT_UPGRADE_DIR"
    exit 2
}

if [ -z "$PTEMPDIR" ] || [ -z "$PDIR" ] || [ -z "$LBHOMEDIR" ]; then
    log_error "Missing required upgrade arguments. PTEMPDIR='$PTEMPDIR' PDIR='$PDIR' LBHOMEDIR='$LBHOMEDIR'"
    exit 2
fi

CONFIG_DIR="$LBHOMEDIR/config/plugins/$PDIR"
POCKET_DATA="$LBHOMEDIR/data/plugins/$PDIR/pockettts"
PERSISTENT_UPGRADE_DIR="$LBHOMEDIR/data/plugins/${PDIR}_upgrade_${PTEMPDIR}"
CONFIG_BACKUP="$PERSISTENT_UPGRADE_DIR/config"
POCKET_BACKUP="$PERSISTENT_UPGRADE_DIR/pockettts"

if [ ! -d "$PERSISTENT_UPGRADE_DIR" ]; then
    abort_install_keep_backup "Persistent upgrade backup folder is missing: $PERSISTENT_UPGRADE_DIR"
fi

if [ ! -f "$PERSISTENT_UPGRADE_DIR/PREUPGRADE_OK" ]; then
    log_warning "Preupgrade marker is missing; attempting restore anyway"
fi

# Restore the previous user configuration over the freshly installed defaults.
if [ -d "$CONFIG_BACKUP" ]; then
    log_info "Restoring existing Text2SIP configuration"
    mkdir -p "$CONFIG_DIR" || abort_install_keep_backup "Could not create config destination: $CONFIG_DIR"
    cp -p -r "$CONFIG_BACKUP/." "$CONFIG_DIR/" || abort_install_keep_backup "Could not restore Text2SIP configuration"
    log_ok "Text2SIP configuration restored"
else
    log_info "No previous Text2SIP configuration backup found"
fi

# Restore venv + model cache + installed-language markers before POSTROOT. The
# absolute venv path is unchanged, so Stage 5+ runtimes can be reused without
# reinstalling PyTorch/Pocket-TTS.
if [ -d "$POCKET_BACKUP" ]; then
    log_info "Restoring Pocket-TTS runtime and language models"
    mkdir -p "$(dirname "$POCKET_DATA")" || abort_install_keep_backup "Could not create Pocket-TTS data parent"

    if [ -e "$POCKET_DATA" ]; then
        rm -rf "$POCKET_DATA" || abort_install_keep_backup "Could not remove newly installed Pocket-TTS data folder"
    fi

    if mv "$POCKET_BACKUP" "$POCKET_DATA"; then
        log_ok "Pocket-TTS runtime and models restored"
    else
        abort_install_keep_backup "Could not restore Pocket-TTS runtime and models"
    fi
else
    log_info "No previous Pocket-TTS runtime/model backup found"
fi

# mqtt_subscriptions.cfg belonged to the retired MQTT bridge/gateway setup.
LEGACY_MQTT_SUBSCRIPTIONS="$CONFIG_DIR/mqtt_subscriptions.cfg"
if [ -e "$LEGACY_MQTT_SUBSCRIPTIONS" ]; then
    if rm -f "$LEGACY_MQTT_SUBSCRIPTIONS"; then
        log_info "Removed legacy MQTT subscription config: $LEGACY_MQTT_SUBSCRIPTIONS"
    else
        log_warning "Could not remove legacy MQTT subscription config: $LEGACY_MQTT_SUBSCRIPTIONS"
    fi
fi

# The daemon performs the small idempotent runtime-directory/permission setup.
log_info "Trigger Text2SIP post-upgrade setup"
touch "$CONFIG_DIR/modify.me" || log_warning "Could not touch Text2SIP modify marker"

# At this point every required restore step succeeded. Remove the complete
# per-upgrade holding folder, including hidden/unknown leftovers, then verify.
# On any earlier restore error abort_install_keep_backup() exits before this
# block so recovery data is intentionally preserved.
log_info "Removing persistent Text2SIP upgrade backup"
rm -rf "$PERSISTENT_UPGRADE_DIR" || abort_install_keep_backup "Could not remove persistent upgrade backup: $PERSISTENT_UPGRADE_DIR"

if [ -e "$PERSISTENT_UPGRADE_DIR" ]; then
    log_error "Persistent upgrade backup still exists after cleanup: $PERSISTENT_UPGRADE_DIR"
    exit 2
fi

log_ok "Persistent Text2SIP upgrade backup removed"
exit 0
