#!/bin/bash

# Grenzwerte
MAXSIZE_KB=100
MAXAGE_DAYS=2
LOGDIR="REPLACELBHOMEDIR/log/plugins/text2sip"

# Lösche alle .log-Dateien, die entweder zu groß oder zu alt sind
find "$LOGDIR" -type f -name "*.log" \( -size +"${MAXSIZE_KB}k" -o -mtime +${MAXAGE_DAYS} \) -exec rm -f {} \;
