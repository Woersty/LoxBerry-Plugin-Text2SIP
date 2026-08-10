#!/bin/bash

BACKUP_DIR="/tmp/REPLACELBPPLUGINDIR"
CONFIG_DIR="REPLACELBPCONFIGDIR"

mkdir -p "$CONFIG_DIR"

if [ -d "$BACKUP_DIR" ]; then
    echo "<INFO> Restoring existing Text2SIP configuration"
    cp -a "$BACKUP_DIR"/. "$CONFIG_DIR"/
    rm -rf "$BACKUP_DIR"
else
    echo "<INFO> No temporary Text2SIP configuration backup found"
fi

# The daemon performs the small idempotent runtime-directory/permission setup.
echo "<INFO> Trigger Text2SIP post-upgrade setup"
touch "$CONFIG_DIR/modify.me"

exit 0
