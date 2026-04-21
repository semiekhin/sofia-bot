#!/bin/bash
# listen_live.sh — live MixMonitor WAV streamer for pilot calls.
#
# Streams the currently-growing WAV (or waits for the next one) to stdout
# so it can be piped into ffplay on the operator's Mac:
#
#   ssh sofia-voice '/opt/sofia-voice/bin/listen_live.sh' | \
#       ffplay -nodisp -autoexit -f wav -
#
# Multi-call session — wrap with a while-loop on the Mac side:
#
#   while true; do
#     ssh sofia-voice '/opt/sofia-voice/bin/listen_live.sh' | \
#         ffplay -nodisp -autoexit -f wav -
#   done
#
# A single invocation streams exactly one call: exits when the WAV stops
# growing for IDLE_THRESHOLD seconds, ffplay closes on EOF, the Mac-side
# loop restarts for the next call. Expected latency end-to-end: 2-5s.
#
# IDLE_THRESHOLD=20 is tuned to tolerate client silence up to ~18s in mid-
# conversation without false cutoff; raise only if clients are observed
# going silent longer than that on a regular basis.

set -u
set -o pipefail

REC_DIR="/var/lib/asterisk/recordings/$(date -u +%Y-%m-%d)"
IDLE_THRESHOLD=20   # seconds of no file growth = call ended

log() { echo "[listen_live] $*" >&2; }

if ! command -v inotifywait >/dev/null 2>&1; then
    log "ERROR: inotifywait not found (apt install inotify-tools)"
    exit 2
fi

mkdir -p "$REC_DIR"

# Pick the currently-growing WAV (modified within the last 3s) — covers
# the case where the operator starts the listener during an active call.
# Otherwise wait for the next CREATE event via inotifywait.
current=$(find "$REC_DIR" -maxdepth 1 -type f -name '*.wav' \
          -newermt '3 seconds ago' -printf '%f\n' 2>/dev/null | head -1)

if [ -n "$current" ]; then
    log "Streaming current call: $current"
    wav="$REC_DIR/$current"
else
    log "Waiting for new call..."
    new_file=$(inotifywait -q -e create --format '%f' "$REC_DIR" 2>/dev/null \
               | head -1)
    if [ -z "$new_file" ]; then
        log "ERROR: inotifywait returned no event"
        exit 3
    fi
    wav="$REC_DIR/$new_file"
    log "New call: $new_file"
fi

# Give MixMonitor a moment to write the RIFF/WAV header.
sleep 0.5

tail -c +0 -F "$wav" 2>/dev/null &
tail_pid=$!

cleanup() {
    kill "$tail_pid" 2>/dev/null || true
    wait "$tail_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Exit when file has not grown for IDLE_THRESHOLD seconds.
last_size=0
idle=0
while :; do
    sleep 2
    current_size=$(stat -c%s "$wav" 2>/dev/null || echo 0)
    if [ "$current_size" = "$last_size" ]; then
        idle=$((idle + 2))
        if [ "$idle" -ge "$IDLE_THRESHOLD" ]; then
            log "Call ended (file idle for ${idle}s)"
            break
        fi
    else
        idle=0
        last_size="$current_size"
    fi
done
