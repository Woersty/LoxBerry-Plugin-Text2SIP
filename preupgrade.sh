#!/bin/sh

# Text2SIP preupgrade.sh
# Persistent upgrade backup - no plugin-created /tmp backup directory.
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

abort_install() {
    log_error "$1"
    [ -n "$PERSISTENT_UPGRADE_DIR" ] && log_error "Persistent upgrade backup kept for recovery: $PERSISTENT_UPGRADE_DIR"
    exit 2
}

cleanup_stale_upgrade_dirs() {
    LIVE_HEALTHY=0
    if [ -f "$CONFIG_DIR/Text2SIP.cfg" ] \
        && [ -x "$POCKET_DATA/venv/bin/pocket-tts" ] \
        && [ -f "$POCKET_DATA/languages/de.ready" ]; then
        LIVE_HEALTHY=1
    fi

    for STALE_DIR in "$LBHOMEDIR/data/plugins/${PDIR}_upgrade_"*; do
        [ -d "$STALE_DIR" ] || continue
        [ "$STALE_DIR" = "$PERSISTENT_UPGRADE_DIR" ] && continue

        if [ -z "$(find "$STALE_DIR" -mindepth 1 -print -quit 2>/dev/null)" ]; then
            rm -rf "$STALE_DIR" 2>/dev/null || true
            [ ! -e "$STALE_DIR" ] && log_info "Removed stale empty upgrade folder: $STALE_DIR"
            continue
        fi

        # A non-empty stale folder from an older completed test can be removed
        # once the live installation is demonstrably healthy. If the live
        # runtime is incomplete, keep it as recovery data.
        if [ "$LIVE_HEALTHY" -eq 1 ]; then
            if rm -rf "$STALE_DIR" 2>/dev/null; then
                log_info "Removed stale previous upgrade backup: $STALE_DIR"
            else
                log_warning "Could not remove stale previous upgrade backup: $STALE_DIR"
            fi
        else
            log_warning "Keeping non-empty previous upgrade folder for recovery: $STALE_DIR"
        fi
    done
}

if [ -z "$PTEMPDIR" ] || [ -z "$PDIR" ] || [ -z "$LBHOMEDIR" ]; then
    log_error "Missing required upgrade arguments. PTEMPDIR='$PTEMPDIR' PDIR='$PDIR' LBHOMEDIR='$LBHOMEDIR'"
    exit 2
fi

CONFIG_DIR="$LBHOMEDIR/config/plugins/$PDIR"
POCKET_DATA="$LBHOMEDIR/data/plugins/$PDIR/pockettts"
POCKET_OLD="$LBHOMEDIR/bin/plugins/$PDIR/pockettts"
POCKET_SERVER_CTL="$LBHOMEDIR/bin/plugins/$PDIR/pockettts/pockettts_server.sh"
POCKET_WATCHDOG_CTL="$LBHOMEDIR/bin/plugins/$PDIR/pockettts/pockettts_watchdog.sh"

# Same persistent sibling strategy as Sonos4Lox: the large/generated payload
# is moved outside data/plugins/$PDIR while LoxBerry replaces the plugin tree.
PERSISTENT_UPGRADE_DIR="$LBHOMEDIR/data/plugins/${PDIR}_upgrade_${PTEMPDIR}"
CONFIG_BACKUP="$PERSISTENT_UPGRADE_DIR/config"
POCKET_BACKUP="$PERSISTENT_UPGRADE_DIR/pockettts"

cleanup_stale_upgrade_dirs

# Stop watchdog first so it cannot restart the resident server while the venv/model
# tree is being moved. Then stop the server itself. POSTROOT starts both again.
if [ -x "$POCKET_WATCHDOG_CTL" ]; then
    log_info "Stopping Pocket-TTS watchdog for upgrade"
    "$POCKET_WATCHDOG_CTL" stop >/dev/null 2>&1 || log_warning "Pocket-TTS watchdog stop returned an error; continuing upgrade"
fi
if [ -x "$POCKET_SERVER_CTL" ]; then
    log_info "Stopping resident Pocket-TTS server for upgrade"
    "$POCKET_SERVER_CTL" stop >/dev/null 2>&1 || log_warning "Pocket-TTS server stop returned an error; continuing upgrade"
fi

log_info "Preparing persistent Text2SIP upgrade backup"
rm -rf "$PERSISTENT_UPGRADE_DIR" || abort_install "Could not remove stale current upgrade backup: $PERSISTENT_UPGRADE_DIR"
mkdir -p "$PERSISTENT_UPGRADE_DIR" || abort_install "Could not create persistent upgrade backup: $PERSISTENT_UPGRADE_DIR"

# Preserve the small plugin configuration without using /tmp.
if [ -d "$CONFIG_DIR" ]; then
    log_info "Backing up existing Text2SIP configuration"
    mkdir -p "$CONFIG_BACKUP" || abort_install "Could not create config backup folder: $CONFIG_BACKUP"
    cp -p -r "$CONFIG_DIR/." "$CONFIG_BACKUP/" || abort_install "Could not back up Text2SIP configuration"
    log_ok "Text2SIP configuration preserved"
else
    log_info "No existing Text2SIP configuration found"
fi

# Stage 5+ layout: move the complete generated Pocket-TTS runtime out of the
# plugin-owned data tree. On the same filesystem this is a rename and avoids
# copying the venv/model cache through /tmp.
if [ -d "$POCKET_DATA" ]; then
    log_info "Preserving Pocket-TTS runtime and language models"
    if mv "$POCKET_DATA" "$POCKET_BACKUP"; then
        log_ok "Pocket-TTS runtime and models moved to persistent upgrade backup"
    else
        abort_install "Could not preserve Pocket-TTS runtime and models"
    fi
else
    # Migration from Stage 1-4: model cache/language markers lived below bin/.
    # Preserve the downloaded data. The old venv contains the old absolute path
    # and therefore has to be rebuilt once at the persistent data location.
    if [ -d "$POCKET_OLD/cache" ] || [ -d "$POCKET_OLD/languages" ]; then
        log_info "Migrating existing Pocket-TTS language data to persistent storage"
        mkdir -p "$POCKET_BACKUP" || abort_install "Could not create Pocket-TTS migration backup"

        if [ -d "$POCKET_OLD/cache" ]; then
            mv "$POCKET_OLD/cache" "$POCKET_BACKUP/cache" || abort_install "Could not preserve Pocket-TTS model cache"
        fi
        if [ -d "$POCKET_OLD/languages" ]; then
            mv "$POCKET_OLD/languages" "$POCKET_BACKUP/languages" || abort_install "Could not preserve Pocket-TTS language markers"
        fi
        log_ok "Existing Pocket-TTS language data preserved"
    fi

    # Avoid thousands of verbose removal lines while migrating from the old
    # bin-based runtime. It is intentionally rebuilt once in POSTROOT.
    if [ -d "$POCKET_OLD/venv" ]; then
        log_info "Removing obsolete bin-based Pocket-TTS runtime"
        rm -rf "$POCKET_OLD/venv" >/dev/null 2>&1 || log_warning "Could not fully remove obsolete bin-based Pocket-TTS runtime"
    fi
fi

touch "$PERSISTENT_UPGRADE_DIR/PREUPGRADE_OK" || abort_install "Could not write preupgrade marker"
log_ok "Persistent Text2SIP preupgrade backup finished"
exit 0
