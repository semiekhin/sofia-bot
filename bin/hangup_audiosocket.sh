#!/bin/bash
# hangup_audiosocket.sh — targeted hangup of AudioSocket channels only.
#
# Called from sofia-voice.service ExecStop to prevent orphan channels
# when the Python process is stopped while AudioSocket() is still running
# in dialplan. Without this hook, the PJSIP channel keeps retrying on a
# dead TCP socket (port 9090), driving Asterisk to 100%+ CPU and burning
# Telphin minutes — root-cause of the 20.04 incident.
#
# Format of `core show channels concise` (Asterisk 20):
#   channel!context!exten!prio!state!app!data!...!uniqueid
#      $1      $2     $3    $4   $5   $6  $7
# We match on $6 == "AudioSocket" and hangup each by $1 (channel name).
# Other PJSIP channels (bridged, playback, etc.) are left alone.
#
# Safe no-op when there are no AudioSocket channels (empty awk output).
# Runs in under 1 second, well within unit's TimeoutStopSec=10.

set -u

log() { logger -t sofia-voice-hangup "$*"; }

channels=$(asterisk -rx 'core show channels concise' 2>/dev/null \
           | awk -F'!' '$6 == "AudioSocket" { print $1 }')

if [ -z "$channels" ]; then
    log "no AudioSocket channels to hangup"
    exit 0
fi

while IFS= read -r ch; do
    [ -z "$ch" ] && continue
    log "hangup $ch"
    asterisk -rx "channel request hangup ${ch}" >/dev/null 2>&1 \
        || log "FAILED hangup $ch"
done <<< "$channels"

exit 0
