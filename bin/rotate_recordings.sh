#!/bin/bash
# rotate_recordings.sh — MixMonitor recording lifecycle manager.
#
# Modes (arg):
#   convert    WAV older than 72h (4320 min) → Opus 32kbps, atomic, idempotent
#   retention  Opus older than 30 days → deleted; empty date dirs cleaned
#   all        convert then retention (default)
#
# Called from /etc/cron.d/sofia-voice-recordings. Logs to
# /var/log/sofia-voice/recordings_rotate.log. Safe to re-run — skips
# already-converted files; WAV deleted only after ffmpeg rc=0.

set -e

REC_DIR=/var/lib/asterisk/recordings
LOG=/var/log/sofia-voice/recordings_rotate.log

mkdir -p "$(dirname "$LOG")"

ts()  { date -u +'%Y-%m-%dT%H:%M:%SZ'; }
log() { echo "$(ts) $*" >> "$LOG"; }

convert_old_wavs() {
    log "convert start"
    if [[ ! -d "$REC_DIR" ]]; then
        log "convert skip: $REC_DIR not found"
        return
    fi
    local count=0
    while IFS= read -r -d '' wav; do
        local opus="${wav%.wav}.opus"
        if [[ -e "$opus" ]]; then
            log "skip (opus exists): $wav"
            rm -f "$wav"
            continue
        fi
        if ffmpeg -nostdin -loglevel error -y -i "$wav" \
                -c:a libopus -b:a 32k "$opus" 2>> "$LOG"; then
            rm -f "$wav"
            log "converted: $wav -> $opus"
            count=$((count + 1))
        else
            log "FAILED ffmpeg: $wav"
            rm -f "$opus" 2>/dev/null || true
        fi
    done < <(find "$REC_DIR" -type f -name "*.wav" -mmin +4320 -print0)
    log "convert done (converted=$count)"
}

retention_cleanup() {
    log "retention start"
    if [[ ! -d "$REC_DIR" ]]; then
        log "retention skip: $REC_DIR not found"
        return
    fi
    local deleted_opus
    deleted_opus=$(find "$REC_DIR" -type f -name "*.opus" -mtime +30 -print -delete 2>> "$LOG" | wc -l)
    local deleted_dirs
    deleted_dirs=$(find "$REC_DIR" -mindepth 1 -maxdepth 1 -type d -empty -print -delete 2>> "$LOG" | wc -l)
    log "retention done (opus_deleted=$deleted_opus empty_dirs_deleted=$deleted_dirs)"
}

mode="${1:-all}"
case "$mode" in
    convert)   convert_old_wavs ;;
    retention) retention_cleanup ;;
    all)       convert_old_wavs; retention_cleanup ;;
    *)
        log "ERROR: unknown mode '$mode' (expected: convert|retention|all)"
        echo "Usage: $0 [convert|retention|all]" >&2
        exit 1
        ;;
esac
