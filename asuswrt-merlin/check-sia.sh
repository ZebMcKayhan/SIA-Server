#!/bin/sh

SERVICE="/opt/etc/init.d/S99siaserver" 
LOCKFILE="/tmp/siaserver_watch.lock"

# Avoid overlapping runs
[ -f "$LOCKFILE" ] && exit 0 touch "$LOCKFILE"
# Check if SIA server is running

if ! ps | grep -E "[s]ia-server.py" >/dev/null; then 
    logger -p 4 -t $(basename $0) "SIA Server not running, restarting..." 
    $SERVICE start
#else 
#    logger -t $(basename $0) "SIA Server is running,  no action."
fi

rm -f "$LOCKFILE"
