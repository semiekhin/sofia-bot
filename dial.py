#!/usr/bin/env python3
"""dial.py — outbound dialer for Sofia voice (RIZALTA).

V1: single call per invocation, CDR-based result tracking.

Usage:
    python3 dial.py 8XXXXXXXXXX
    python3 dial.py 7XXXXXXXXXX
    python3 dial.py +7XXXXXXXXXX
    python3 dial.py XXXXXXXXXX   (10 digits, +7 prepended)

Flow:
    1. Normalize phone number to E.164 (+7XXXXXXXXXX)
    2. Snapshot Master.csv size and active channel uniqueids
    3. Run `asterisk -rx 'channel originate PJSIP/<phone>@telphin-endpoint
       extension s@outbound-audiosocket'`
    4. Poll `core show channels concise` for the new telphin-endpoint channel
       → capture its uniqueid (primary CDR match key)
    5. Poll Master.csv until the matching uniqueid row appears
       (fallback: match by dcontext=outbound-audiosocket + phone in channel)
    6. Write one JSONL line to /var/log/sofia-voice/outbound_YYYY-MM-DD.jsonl
    7. Print summary + exit with code per disposition

Exit codes:
    0 = ANSWERED with billsec >= 5 seconds (real conversation)
    1 = NO ANSWER / BUSY / ANSWERED with billsec < 5 (hangup-after-hello)
    2 = invalid phone format / argparse error
    3 = FAILED / originate error / no CDR within timeout
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time

CDR_PATH = "/var/log/asterisk/cdr-csv/Master.csv"
DB_PATH = "/opt/sofia-voice/sofia_voice.db"
METRICS_DIR = "/var/log/sofia-voice"
TRANSCRIPTS_DIR = os.path.join(METRICS_DIR, "transcripts")
CALL_TIMEOUT_SEC = 600  # 10 min: allows 3-5 min RIZALTA conversations
POLL_INTERVAL_SEC = 2
STATE_POLL_INTERVAL_SEC = 1  # channel state poll is faster than CDR poll
CHANNEL_APPEAR_WAIT_SEC = 5
ORIGINATE_CMD_TIMEOUT = 10
MIN_BILLSEC_SUCCESS = 5  # ANSWERED with billsec < 5 => still a hangup

# Realtime transcript streaming to terminal (tail journalctl while call is Up)
STREAM_TRANSCRIPT = os.getenv("STREAM_TRANSCRIPT", "true").lower() != "false"
_LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+")
_LOG_USER_RE = re.compile(r"🎤 USER: (.*)$")
_LOG_SOFIA_RE = re.compile(r"🧠 SOFIA: (.*)$")
_LOG_AUTO_RE = re.compile(r"(AUTO_HANGUP (?:detect|exec|cancel)[^\r\n]*)$")
# Per-turn metrics: EOU (STT end-of-utterance wait) and TTS first audio chunk
# accumulate across log lines; '⏱️ Turn timings:' carries LLM and acts as the
# flush trigger (turn closed → print aggregated METRICS line). EOU regex
# requires text_len>=1 to skip the echo pair with eou_wait_ms=-1 text_len=0.
# No UUID filter — V1 assumption: one outbound call in flight (matches the
# USER/SOFIA matchers above and the concise-parser assumption at line 215).
_LOG_EOU_RE = re.compile(
    r"EOU_WAIT uuid=[\w-]+ turn=\d+ eou_wait_ms=(\d+) text_len=[1-9]\d*"
)
_LOG_TTS_FIRST_RE = re.compile(r"TTS first audio chunk: (\d+)ms")
_LOG_TURN_RE = re.compile(
    r"⏱️ Turn timings: STT=\d+ms, LLM=(\d+)ms, TTS=\d+ms, TOTAL=\d+ms"
)

# Post-call MixMonitor WAV hint. Dialplan writes with
# STRFTIME(${EPOCH},,%Y-%m-%d) in UTC (cdr.conf usegmtime=yes), so the
# YYYY-MM-DD directory matches CDR.start[:10] regardless of local TZ.
# SCP_HOST is the SSH alias on Sergey's Mac, not root@IP.
RECORDINGS_DIR = "/var/lib/asterisk/recordings"
SCP_HOST = "sofia-voice"

# NOTE: formula MUST match voice_asterisk.py:125 function call_id_to_user_id.
# Duplicated intentionally to keep dial.py a standalone script without an
# import dependency on the voice stack. If one changes — change the other.
VOICE_USER_ID_OFFSET = 9_500_000

CDR_FIELDS = [
    "accountcode",
    "src",
    "dst",
    "dcontext",
    "clid",
    "channel",
    "dstchannel",
    "lastapp",
    "lastdata",
    "start",
    "answer",
    "end",
    "duration",
    "billsec",
    "disposition",
    "amaflags",
    "uniqueid",
    "userfield",
]


def normalize_phone(raw: str) -> str | None:
    s = raw.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if s.startswith("+") and len(s) == 12 and s[1:].isdigit() and s[1] == "7":
        return s
    if s.startswith("8") and len(s) == 11 and s.isdigit():
        return "+7" + s[1:]
    if s.startswith("7") and len(s) == 11 and s.isdigit():
        return "+" + s
    if len(s) == 10 and s.isdigit():
        return "+7" + s
    return None


def run_asterisk_cli(cmd_str: str, timeout: int = 5) -> tuple[int, str, str]:
    """Run asterisk -rx and return (rc, stdout, stderr)."""
    result = subprocess.run(
        ["asterisk", "-rx", cmd_str],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def snapshot_channel_uniqueids() -> set[str]:
    """Return set of uniqueids of currently active channels."""
    try:
        rc, out, _ = run_asterisk_cli("core show channels concise")
    except subprocess.TimeoutExpired:
        return set()
    if rc != 0:
        return set()
    ids = set()
    for line in out.splitlines():
        # concise fields separated by '!', uniqueid is last field
        parts = line.strip().split("!")
        if len(parts) >= 13 and parts[0].startswith("PJSIP/"):
            ids.add(parts[12])
    return ids


def find_new_telphin_uniqueid(before: set[str]) -> str | None:
    """Poll core show channels concise for a new telphin-endpoint channel."""
    deadline = time.monotonic() + CHANNEL_APPEAR_WAIT_SEC
    while time.monotonic() < deadline:
        try:
            rc, out, _ = run_asterisk_cli("core show channels concise")
        except subprocess.TimeoutExpired:
            time.sleep(0.5)
            continue
        if rc == 0:
            for line in out.splitlines():
                parts = line.strip().split("!")
                if len(parts) >= 13 and "telphin-endpoint" in parts[0]:
                    uid = parts[12]
                    if uid and uid not in before:
                        return uid
        time.sleep(0.5)
    return None


def find_cdr_by_uniqueid(uniqueid: str) -> dict | None:
    try:
        with open(CDR_PATH, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reversed(list(reader)):
                if len(row) < len(CDR_FIELDS):
                    continue
                if row[16] == uniqueid:  # uniqueid is field #16
                    return dict(zip(CDR_FIELDS, row))
    except FileNotFoundError:
        return None
    return None


def find_cdr_fallback(initial_lines: int, ts_start: dt.datetime) -> dict | None:
    """Fallback match when uniqueid wasn't captured (ring longer than
    CHANNEL_APPEAR_WAIT_SEC). Newest row past initial_lines with
    dcontext=outbound-audiosocket and start >= ts_start - 5s tolerance.
    Works only for sequential single calls — concurrent outbounds can
    confuse this matcher.

    CDR timestamps are UTC (cdr.conf usegmtime=yes). Phone number is
    intentionally NOT used: Asterisk outbound originate does not populate
    CDR src/dst with the dialled number — channel name is just the endpoint
    (PJSIP/telphin-endpoint-XXXXX), phone digits never land in channel
    or dstchannel fields."""
    try:
        with open(CDR_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        return None
    tol = dt.timedelta(seconds=5)
    for row in reversed(rows[initial_lines:]):
        if len(row) < len(CDR_FIELDS):
            continue
        rec = dict(zip(CDR_FIELDS, row))
        if rec["dcontext"] != "outbound-audiosocket":
            continue
        try:
            rec_start = dt.datetime.strptime(rec["start"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError:
            continue
        if rec_start >= ts_start - tol:
            return rec
    return None


def cdr_line_count() -> int:
    """Number of CSV rows (not newline count — CDR rows may contain
    embedded newlines in quoted CallerID fields, which breaks byte-line
    counting. Observed 17.04: 256 newlines vs 254 csv rows — off-by-2
    made `rows[initial_lines:]` slice empty, fallback matcher saw nothing."""
    try:
        with open(CDR_PATH, newline="", encoding="utf-8") as f:
            return sum(1 for _ in csv.reader(f))
    except FileNotFoundError:
        return 0


def get_channel_state(channel_hint: str = "telphin-endpoint") -> str | None:
    """Return 'Ringing' | 'Up' | 'Other' | None (channel absent).
    Substring match on `core show channels concise` output, NOT field-index
    parsing — see P3 backlog `concise parser field index bug`. Safe as long
    as we have at most one outbound call in flight (V1 assumption)."""
    try:
        rc, out, _ = run_asterisk_cli("core show channels concise")
    except subprocess.TimeoutExpired:
        return None
    if rc != 0:
        return None
    for line in out.splitlines():
        if channel_hint not in line:
            continue
        if "!Up!" in line:
            return "Up"
        if "!Ring" in line:  # matches Ring and Ringing
            return "Ringing"
        return "Other"
    return None


def _print_state_transition(old: str | None, new: str | None) -> None:
    """Stdout status line on channel state change. UTC (VPS timezone)."""
    ts = time.strftime("%H:%M:%S")
    if new == "Ringing":
        print(f"[{ts}] Ringing...")
    elif new == "Up":
        print(f"[{ts}] Answered")
    elif new is None and old in ("Ringing", "Up"):
        print(f"[{ts}] Ended")


def _mmss_offset(log_ts_full: str, call_start: dt.datetime) -> str:
    """Render 'MM:SS' offset from call_start given 'YYYY-MM-DD HH:MM:SS'
    captured from a log line. Negative/parse-fail clamps to '00:00'."""
    try:
        log_ts = dt.datetime.strptime(log_ts_full, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError:
        return "00:00"
    offset_sec = max(int((log_ts - call_start).total_seconds()), 0)
    mm, ss = divmod(offset_sec, 60)
    return f"{mm:02d}:{ss:02d}"


def _log_tail_reader(stdout, call_start: dt.datetime) -> None:
    """Read journalctl -f lines, print matched USER / SOFIA / METRICS /
    AUTO_HANGUP events as [MM:SS]-prefixed lines (offset from call_start,
    which is main()'s ts_start — same origin used by post-call
    format_transcript for consistency).

    Metrics state machine: EOU_WAIT and TTS-first-chunk log lines arrive
    before the turn's '⏱️ Turn timings:' line, which closes the turn and
    triggers the aggregated METRICS print. Silent on exceptions — stream
    is best-effort, must not crash dial.py."""
    pending_eou: str | None = None
    pending_tts: str | None = None
    try:
        for raw in iter(stdout.readline, b""):
            try:
                line = raw.decode("utf-8", errors="replace").rstrip()
            except Exception:
                continue
            ts_m = _LOG_TS_RE.match(line)
            mmss = _mmss_offset(ts_m.group(1), call_start) if ts_m else "00:00"

            u = _LOG_USER_RE.search(line)
            if u:
                print(f"[{mmss}] USER: {u.group(1)}", flush=True)
                continue
            s = _LOG_SOFIA_RE.search(line)
            if s:
                print(f"[{mmss}] SOFIA: {s.group(1)}", flush=True)
                continue
            a = _LOG_AUTO_RE.search(line)
            if a:
                print(f"[{mmss}] {a.group(1)}", flush=True)
                continue

            e = _LOG_EOU_RE.search(line)
            if e:
                pending_eou = e.group(1)
                continue
            t = _LOG_TTS_FIRST_RE.search(line)
            if t:
                pending_tts = t.group(1)
                continue
            tr = _LOG_TURN_RE.search(line)
            if tr:
                eou = pending_eou if pending_eou is not None else "?"
                tts = pending_tts if pending_tts is not None else "?"
                llm = tr.group(1)
                print(
                    f"[{mmss}] METRICS: eou={eou}ms llm={llm}ms tts={tts}ms",
                    flush=True,
                )
                pending_eou = None
                pending_tts = None
    except Exception:
        pass


def start_log_tail(call_start: dt.datetime):
    """Spawn journalctl -u sofia-voice -f reader. Returns (proc, thread)
    tuple or None. Safe on env-disabled / spawn failure — prints a
    one-line warning and returns None.

    call_start is the UTC originate-time timestamp (main()'s ts_start);
    used by the reader to render [MM:SS] offsets on streamed events."""
    if not STREAM_TRANSCRIPT:
        return None
    try:
        proc = subprocess.Popen(
            ["journalctl", "-u", "sofia-voice", "-f", "-n", "0", "-o", "cat"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"(live stream unavailable: {e})", file=sys.stderr)
        return None
    thread = threading.Thread(
        target=_log_tail_reader, args=(proc.stdout, call_start), daemon=True
    )
    thread.start()
    return (proc, thread)


def stop_log_tail(handle) -> None:
    """Terminate journalctl subprocess and join reader thread.
    Idempotent — safe on None handle."""
    if handle is None:
        return
    proc, thread = handle
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        thread.join(timeout=2)
    except Exception:
        pass


def wait_for_cdr(
    uniqueid: str | None,
    initial_lines: int,
    ts_start: dt.datetime,
    timeout_sec: int,
    print_status: bool = True,
) -> dict | None:
    """Poll CDR + channel state. Primary CDR match: uniqueid (fast
    short-circuit when capture worked). Fallback: timestamp+dcontext —
    ALWAYS tried as safety net (concise parser can return wrong uniqueid
    on Asterisk 20, P3 backlog). State polling at 1s cadence, CDR at 2s.

    When print_status=True, emits [HH:MM:SS] status lines on state
    transitions (None→Ringing, *→Up, (Ringing|Up)→None). Also streams
    realtime USER/SOFIA/AUTO_HANGUP events from journalctl while the
    channel is Up (STREAM_TRANSCRIPT=true)."""
    deadline = time.monotonic() + timeout_sec
    # Silent originate failure (SIP reject / peer unreachable before channel
    # creation) leaves no CDR; without this early exit polling would run the
    # full timeout_sec. 30s covers normal SIP invite/ring-start latency.
    # Counter requires 3 consecutive Up/Ringing polls to confirm a real
    # channel — a single transient poll (state="Other", or a briefly-created-
    # then-hungup channel from an invalid dial) must not cancel the giveup.
    channel_giveup = time.monotonic() + 30
    channel_consecutive = 0
    channel_ever_seen = False
    last_state: str | None = None
    log_tail = None
    next_cdr_check = time.monotonic()
    try:
        while time.monotonic() < deadline:
            time.sleep(STATE_POLL_INTERVAL_SEC)
            if print_status:
                state = get_channel_state()
                if state in ("Up", "Ringing"):
                    channel_consecutive += 1
                    if channel_consecutive >= 3:
                        channel_ever_seen = True
                else:
                    channel_consecutive = 0
                if not channel_ever_seen and time.monotonic() >= channel_giveup:
                    return None
                if state != last_state:
                    _print_state_transition(last_state, state)
                    if state == "Up" and log_tail is None:
                        log_tail = start_log_tail(ts_start)
                    elif state is None and last_state in ("Ringing", "Up"):
                        stop_log_tail(log_tail)
                        log_tail = None
                    last_state = state
            if time.monotonic() >= next_cdr_check:
                next_cdr_check = time.monotonic() + POLL_INTERVAL_SEC
                if uniqueid:
                    rec = find_cdr_by_uniqueid(uniqueid)
                    if rec:
                        return rec
                rec = find_cdr_fallback(initial_lines, ts_start)
                if rec:
                    return rec
        return None
    finally:
        stop_log_tail(log_tail)


def audiosocket_uuid_to_chat_id(uuid_str: str) -> str:
    """Mirror of voice_asterisk.py:125 call_id_to_user_id. MUST stay in sync
    with the voice side — see NOTE near VOICE_USER_ID_OFFSET constant."""
    h = hashlib.md5(uuid_str.encode()).hexdigest()[:8]
    return str(VOICE_USER_ID_OFFSET + (int(h, 16) % 1_000_000))


def fetch_transcript(audiosocket_uuid: str) -> list[tuple[str, str, str]]:
    """Read messages table for this call. Returns [(timestamp, role,
    content), ...] ordered by id (insert order). Returns [] on SQLite
    error and logs to stderr — transcript is non-critical, must not
    crash the dialer."""
    chat_id = audiosocket_uuid_to_chat_id(audiosocket_uuid)
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        try:
            return conn.execute(
                "SELECT timestamp, role, content FROM messages "
                "WHERE chat_id = ? ORDER BY id",
                (chat_id,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:
        print(f"Transcript SQL error: {e}", file=sys.stderr)
        return []


def format_transcript(
    rows: list[tuple[str, str, str]], call_start_ts: dt.datetime
) -> str:
    """Render rows as '[MM:SS] ROLE: content'. Offset in seconds from
    call_start_ts (UTC-aware); values before call_start_ts clamp to 00:00."""
    if not rows:
        return ""
    lines = []
    for ts_str, role, content in rows:
        try:
            msg_ts = dt.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=dt.timezone.utc
            )
        except ValueError:
            msg_ts = call_start_ts
        offset_sec = max(int((msg_ts - call_start_ts).total_seconds()), 0)
        mm, ss = divmod(offset_sec, 60)
        role_label = "SOFIA" if role == "assistant" else "USER"
        lines.append(f"[{mm:02d}:{ss:02d}] {role_label}: {content}")
    return "\n".join(lines)


def write_transcript_file(uuid_str: str, content: str) -> str:
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)
    path = os.path.join(TRANSCRIPTS_DIR, f"transcript_{uuid_str}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content + "\n")
    return path


def write_jsonl(record: dict) -> str:
    os.makedirs(METRICS_DIR, exist_ok=True)
    day = dt.datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(METRICS_DIR, f"outbound_{day}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _print_recording_info(rec: dict) -> None:
    """Post-call hint: MixMonitor WAV path + scp one-liner for the Mac.
    Gated by caller on ANSWERED + billsec>=MIN_BILLSEC_SUCCESS; shorter
    calls either have no file or a meaningless stub. Date is CDR.start[:10]
    (UTC per cdr.conf usegmtime=yes → matches dialplan STRFTIME(${EPOCH},,
    %Y-%m-%d) used in the MixMonitor path).

    Filename is the AudioSocket CALL_UUID (kernel-random RFC-4122 UUID,
    not the Asterisk CDR uniqueid). Dialplan writes both MixMonitor and
    AudioSocket with the same ${CALL_UUID}, so CDR.lastdata (passed to
    AudioSocket) gives us the correct filename. See extensions.conf
    [outbound-audiosocket]:28-31 for the comment about why Asterisk's
    ${UNIQUEID} (epoch.counter) cannot be used — AudioSocket rejects it.

    scp uses the 'sofia-voice' SSH alias which lives on Sergey's Mac —
    explicitly labelled in the output since dial.py is run from ssh
    sofia-dev, not the Mac."""
    lastdata = rec.get("lastdata") or ""
    call_uuid = lastdata.split(",")[0] if lastdata else ""
    start = rec.get("start") or ""
    if not call_uuid or len(start) < 10:
        return
    date_dir = start[:10]
    path = f"{RECORDINGS_DIR}/{date_dir}/{call_uuid}.wav"
    if os.path.exists(path):
        print(f"Recording: {path}")
        print(f"Download (run from your Mac): scp {SCP_HOST}:{path} ~/Desktop/")
    else:
        print(f"Recording: {path} (not found — rotated or disabled?)")


def disposition_to_exit(disposition: str, billsec: int) -> int:
    if disposition == "ANSWERED":
        return 0 if billsec >= MIN_BILLSEC_SUCCESS else 1
    if disposition in ("NO ANSWER", "NOANSWER", "BUSY"):
        return 1
    return 3


def main() -> int:
    p = argparse.ArgumentParser(
        description="Outbound dialer for Sofia voice",
        epilog="Phone formats: 8XXXXXXXXXX, 7XXXXXXXXXX, +7XXXXXXXXXX, or 10-digit",
    )
    p.add_argument("phone_number", help="Phone number to call")
    args = p.parse_args()

    phone = normalize_phone(args.phone_number)
    if not phone:
        print(f"Error: invalid phone format {args.phone_number!r}", file=sys.stderr)
        print(
            "Expected 10 digits, 11 digits starting with 7 or 8, or +7XXXXXXXXXX",
            file=sys.stderr,
        )
        return 2

    ts_start = dt.datetime.now(dt.timezone.utc)
    initial_lines = cdr_line_count()
    channels_before = snapshot_channel_uniqueids()
    uniqueid: str | None = None  # what concise parser captured (may differ from CDR)

    print(f"[{time.strftime('%H:%M:%S')}] Originating call to {phone}")
    originate_cmd = (
        f"channel originate PJSIP/{phone}@telphin-endpoint "
        f"extension s@outbound-audiosocket"
    )
    try:
        rc, _stdout, stderr = run_asterisk_cli(
            originate_cmd, timeout=ORIGINATE_CMD_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        rec_err = {
            "ts_start": ts_start.isoformat(),
            "ts_end": dt.datetime.now(dt.timezone.utc).isoformat(),
            "phone": phone,
            "uuid": None,
            "captured_uniqueid": uniqueid,
            "disposition": "FAILED",
            "duration": 0,
            "billsec": 0,
            "exit_code": 3,
            "error": "originate_cli_timeout",
        }
        path = write_jsonl(rec_err)
        print(f"Call: {phone}\nUUID: -\nStatus: FAILED (CLI timeout)\nLog: {path}")
        return 3

    if rc != 0:
        rec_err = {
            "ts_start": ts_start.isoformat(),
            "ts_end": dt.datetime.now(dt.timezone.utc).isoformat(),
            "phone": phone,
            "uuid": None,
            "captured_uniqueid": uniqueid,
            "disposition": "FAILED",
            "duration": 0,
            "billsec": 0,
            "exit_code": 3,
            "error": f"originate_rc={rc}",
            "stderr": stderr[:200],
        }
        path = write_jsonl(rec_err)
        print(
            f"Call: {phone}\nUUID: -\nStatus: FAILED (originate rc={rc})\nLog: {path}"
        )
        return 3

    # Capture uniqueid of the newly created telphin-endpoint channel.
    # Known-unreliable on Asterisk 20 — value is persisted to JSONL as
    # "captured_uniqueid" for post-mortem comparison with CDR.uniqueid.
    uniqueid = find_new_telphin_uniqueid(channels_before)

    # Poll CDR until row appears
    rec = wait_for_cdr(uniqueid, initial_lines, ts_start, CALL_TIMEOUT_SEC)
    ts_end = dt.datetime.now(dt.timezone.utc)

    if not rec:
        rec_err = {
            "ts_start": ts_start.isoformat(),
            "ts_end": ts_end.isoformat(),
            "phone": phone,
            "uuid": None,
            "captured_uniqueid": uniqueid,
            "disposition": "FAILED",
            "duration": 0,
            "billsec": 0,
            "exit_code": 3,
            "error": f"no_cdr_after_{CALL_TIMEOUT_SEC}s",
        }
        path = write_jsonl(rec_err)
        print(
            f"Call: {phone}\nUUID: {uniqueid or '-'}\n"
            f"Status: FAILED (no CDR after {CALL_TIMEOUT_SEC}s)\nLog: {path}"
        )
        return 3

    disposition = rec["disposition"]
    duration = int(rec["duration"]) if rec["duration"].isdigit() else 0
    billsec = int(rec["billsec"]) if rec["billsec"].isdigit() else 0
    exit_code = disposition_to_exit(disposition, billsec)

    # AudioSocket UUID is the first CSV token of lastdata "UUID,host:port"
    audiosocket_uuid = rec["lastdata"].split(",")[0] if rec.get("lastdata") else ""
    transcript_rows = fetch_transcript(audiosocket_uuid) if audiosocket_uuid else []
    transcript_text = format_transcript(transcript_rows, ts_start)
    transcript_path: str | None = None
    if transcript_text:
        try:
            transcript_path = write_transcript_file(audiosocket_uuid, transcript_text)
        except OSError as e:
            print(f"Transcript file write error: {e}", file=sys.stderr)

    record = {
        "ts_start": ts_start.isoformat(),
        "ts_end": ts_end.isoformat(),
        "phone": phone,
        "uuid": rec["uniqueid"],
        "captured_uniqueid": uniqueid,
        "disposition": disposition,
        "duration": duration,
        "billsec": billsec,
        "exit_code": exit_code,
        "transcript_path": transcript_path,
        "message_count": len(transcript_rows),
    }
    path = write_jsonl(record)
    print(f"Call: {phone}")
    print(f"UUID: {rec['uniqueid']}")
    print(f"Status: {disposition}")
    print(f"Duration: {duration}s (billsec: {billsec}s)")
    print(f"Log: {path}")
    if disposition == "ANSWERED" and billsec >= MIN_BILLSEC_SUCCESS:
        _print_recording_info(rec)
    if transcript_path:
        print(f"Transcript: {transcript_path}")
        print()
        print("--- Transcript ---")
        print(transcript_text)
    else:
        print("Transcript: (no messages found)")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
