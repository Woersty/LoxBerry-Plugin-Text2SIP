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

# mqtt_subscriptions.cfg belonged to the retired MQTT bridge/gateway setup.
# An upgrade backup may restore it even though it is no longer shipped, so
# explicitly remove the legacy config after restoring the user's settings.
LEGACY_MQTT_SUBSCRIPTIONS="$CONFIG_DIR/mqtt_subscriptions.cfg"
if [ -e "$LEGACY_MQTT_SUBSCRIPTIONS" ]; then
    if rm -f "$LEGACY_MQTT_SUBSCRIPTIONS"; then
        echo "<INFO> Removed legacy MQTT subscription config: $LEGACY_MQTT_SUBSCRIPTIONS"
    else
        echo "<WARNING> Could not remove legacy MQTT subscription config: $LEGACY_MQTT_SUBSCRIPTIONS"
    fi
fi

# The daemon performs the small idempotent runtime-directory/permission setup.
echo "<INFO> Trigger Text2SIP post-upgrade setup"
touch "$CONFIG_DIR/modify.me"

exit 0
