#!/usr/bin/env bash

# Text2SIP pre-install hook.
# Executed by LoxBerry as user "loxberry" before the plugin files are installed.
#
# A fresh Pocket-TTS runtime (Python venv + CPU PyTorch + Pocket-TTS + German
# model) needs meaningful persistent disk headroom. Refuse a new/incomplete
# runtime installation when less than 2 GiB is free on the LoxBerry data
# filesystem. During a normal upgrade, a complete compatible runtime is moved
# aside by preupgrade.sh and reused, so the 2 GiB first-install reserve is not
# required in that case.
#
# LoxBerry passes:
#   $1 temp id, $2 plugin name, $3 plugin folder, $4 version,
#   $5 LoxBerry home, $6 extracted plugin folder

PTEMPDIR="${1:-}"
PDIR="${3:-text2sip}"
LBHOMEDIR="${5:-REPLACELBHOMEDIR}"

MIN_FREE_MIB=2048
MIN_FREE_GIB="2.00"
DATA_FS_PATH="$LBHOMEDIR/data"
LIVE_RUNTIME="$LBHOMEDIR/data/plugins/$PDIR/pockettts"
UPGRADE_RUNTIME=""

log_info()  { echo "<INFO> $1"; }
log_ok()    { echo "<OK> $1"; }
log_error() { echo "<ERROR> $1"; }

# On upgrade, preupgrade.sh moves the complete generated runtime out of the
# plugin tree before LoxBerry purges the old installation. Detect that exact
# holding path so a healthy runtime is not needlessly blocked by the first-
# install free-space requirement.
if [ -n "$PTEMPDIR" ]; then
    UPGRADE_RUNTIME="$LBHOMEDIR/data/plugins/${PDIR}_upgrade_${PTEMPDIR}/pockettts"
fi

runtime_is_reusable() {
    local runtime="$1"
    local py="$runtime/venv/bin/python"
    local installed_ver runtime_py sys_py

    [ -x "$py" ] || return 1
    [ -f "$runtime/languages/de.ready" ] || return 1

    installed_ver="$($py -c 'import importlib.metadata; print(importlib.metadata.version("pocket-tts"))' 2>/dev/null || true)"
    [ "$installed_ver" = "2.1.0" ] || return 1

    "$py" -c 'import torch' >/dev/null 2>&1 || return 1

    runtime_py="$($py -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    sys_py="$(/usr/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    [ -n "$runtime_py" ] && [ -n "$sys_py" ] && [ "$runtime_py" = "$sys_py" ] || return 1

    return 0
}

# Prefer the upgrade holding folder because the live plugin data tree has
# normally already been moved by PREUPGRADE when PREINSTALL runs.
REUSABLE_RUNTIME=""
if [ -n "$UPGRADE_RUNTIME" ] && runtime_is_reusable "$UPGRADE_RUNTIME"; then
    REUSABLE_RUNTIME="$UPGRADE_RUNTIME"
elif runtime_is_reusable "$LIVE_RUNTIME"; then
    REUSABLE_RUNTIME="$LIVE_RUNTIME"
fi

FREE_MIB="$(df -Pm "$DATA_FS_PATH" 2>/dev/null | awk 'NR==2 {print $4}')"
if ! [[ "$FREE_MIB" =~ ^[0-9]+$ ]]; then
    log_error "Could not determine free persistent disk space on the LoxBerry data filesystem ($DATA_FS_PATH)."
    log_error "Text2SIP installation aborted for safety."
    exit 2
fi

FREE_GIB="$(awk -v mib="$FREE_MIB" 'BEGIN { printf "%.2f", mib / 1024 }')"

if [ -n "$REUSABLE_RUNTIME" ]; then
    log_info "Persistent disk space: ${FREE_GIB} GiB free on the LoxBerry data filesystem."
    log_ok "Existing compatible Pocket-TTS 2.1.0 runtime including the German model will be reused; the 2 GiB first-install reserve is not required."
    exit 0
fi

log_info "Persistent disk space check: ${FREE_GIB} GiB free; at least ${MIN_FREE_GIB} GiB are required for a new Pocket-TTS runtime."

if [ "$FREE_MIB" -lt "$MIN_FREE_MIB" ]; then
    log_error "Insufficient persistent disk space for Text2SIP / Pocket-TTS."
    log_error "At least ${MIN_FREE_GIB} GiB of free disk space are required before installation."
    log_error "Please free disk space or enlarge the system disk, then start the installation again."
    exit 2
fi

log_ok "Sufficient persistent disk space available for Text2SIP / Pocket-TTS."
exit 0
