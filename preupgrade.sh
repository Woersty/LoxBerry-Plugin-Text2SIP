#!/bin/bash

BACKUP_DIR="/tmp/REPLACELBPPLUGINDIR"
CONFIG_DIR="REPLACELBPCONFIGDIR"

echo "<INFO> Creating temporary backup for Text2SIP configuration"
rm -rf "$BACKUP_DIR"
mkdir -p "$BACKUP_DIR"

if [ -d "$CONFIG_DIR" ]; then
    echo "<INFO> Backing up existing configuration"
    cp -a "$CONFIG_DIR"/. "$BACKUP_DIR"/
else
    echo "<INFO> No existing configuration directory found"
fi

exit 0
